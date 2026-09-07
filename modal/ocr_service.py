"""Axmed's authenticated PaddleOCR service, deployed independently from the API."""

import base64
import hmac
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import modal

APP_NAME = "axmed-paddle-ocr"
SCHEMA_VERSION = "1.0"
MAX_INPUT_BYTES = 12 * 1024 * 1024
MAX_SELECTED_PAGES = 12
MAX_RENDERED_PIXELS = 24_000_000
SUPPORTED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png"}
CACHE_ROOT = "/tmp/paddle-cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0", "libgomp1", "libsm6", "libxext6", "libxrender1")
    .run_commands(
        "python -m pip install --upgrade pip",
        "python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/",
    )
    .uv_pip_install(
        "fastapi[standard]==0.115.12",
        "numpy==1.26.4",
        "Pillow==10.4.0",
        "PyMuPDF==1.26.0",
        "paddleocr==3.5.0",
    )
    .env({"PADDLE_HOME": f"{CACHE_ROOT}/paddle", "XDG_CACHE_HOME": CACHE_ROOT, "PADDLE_OCR_LANG": "en"})
)

app = modal.App(APP_NAME)
_ocr_engine: Any | None = None


def _authenticate(authorization: str | None) -> None:
    expected = os.environ.get("OCR_SERVICE_TOKEN")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise PermissionError("unauthorized")


def _validate_request(media_type: str, content: bytes, selected_pages: list[int]) -> None:
    if media_type not in {"application/pdf", *SUPPORTED_IMAGE_MEDIA_TYPES}:
        raise ValueError("unsupported_media_type")
    if not content or len(content) > MAX_INPUT_BYTES:
        raise ValueError("invalid_input_size")
    if not selected_pages or len(selected_pages) > MAX_SELECTED_PAGES or any(page < 1 for page in selected_pages):
        raise ValueError("invalid_selected_pages")
    if media_type != "application/pdf" and selected_pages != [1]:
        raise ValueError("invalid_image_page_selection")


def _get_ocr_engine() -> Any:
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
            device="gpu",
            lang="en",
        )
    return _ocr_engine


def _line_records(prediction: Any) -> list[dict[str, Any]]:
    payload = getattr(prediction, "res", prediction)
    if isinstance(payload, dict) and "res" in payload:
        payload = payload["res"]
    if not isinstance(payload, dict):
        return []
    texts = payload.get("rec_texts") or payload.get("texts") or []
    scores = payload.get("rec_scores") or payload.get("scores") or []
    polygons = payload.get("rec_polys") or payload.get("dt_polys") or []
    lines: list[dict[str, Any]] = []
    for index, raw_text in enumerate(texts):
        text = str(raw_text).strip()
        polygon = polygons[index] if index < len(polygons) else None
        if not text or polygon is None or len(polygon) != 4:
            continue
        bounds = [[float(point[0]), float(point[1])] for point in polygon]
        if any(len(point) != 2 for point in bounds):
            continue
        confidence = float(scores[index]) if index < len(scores) else 0.0
        lines.append({"text": text, "confidence": min(1.0, max(0.0, confidence)), "bounds": bounds})
    return lines


def _ocr_page(path: Path, page_number: int, dpi: int) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as source:
        width, height = source.size
    predictions = _get_ocr_engine().predict(str(path))
    lines = [line for prediction in predictions for line in _line_records(prediction)]
    return {"original_page_number": page_number, "width": width, "height": height, "dpi": dpi, "lines": lines}


def _render_pdf_pages(content: bytes, selected_pages: list[int], directory: Path) -> list[tuple[Path, int, int]]:
    import fitz

    document = fitz.open(stream=content, filetype="pdf")
    try:
        if document.is_encrypted:
            raise ValueError("encrypted_pdf")
        if max(selected_pages) > document.page_count:
            raise ValueError("page_not_found")
        rendered: list[tuple[Path, int, int]] = []
        for page_number in selected_pages:
            pixmap = document.load_page(page_number - 1).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            if pixmap.width * pixmap.height > MAX_RENDERED_PIXELS:
                raise ValueError("render_limit_exceeded")
            path = directory / f"page-{page_number}.png"
            pixmap.save(str(path))
            rendered.append((path, page_number, 144))
        return rendered
    finally:
        document.close()


def run_ocr(content: bytes, media_type: str, selected_pages: list[int]) -> dict[str, Any]:
    _validate_request(media_type, content, selected_pages)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="axmed-ocr-") as temp_dir:
        directory = Path(temp_dir)
        if media_type == "application/pdf":
            rendered = _render_pdf_pages(content, selected_pages, directory)
        else:
            suffix = ".png" if media_type == "image/png" else ".jpg"
            path = directory / f"input{suffix}"
            path.write_bytes(content)
            rendered = [(path, 1, 72)]
        pages = [_ocr_page(path, page_number, dpi) for path, page_number, dpi in rendered]
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "axmed-modal",
        "model": "paddleocr-3.5.0",
        "configuration_version": "2026-09-06",
        "duration_ms": round((time.monotonic() - started) * 1000),
        "pages": pages,
    }


@app.function(
    image=image,
    gpu="T4",
    cpu=4.0,
    memory=8192,
    timeout=120,
    secrets=[modal.Secret.from_name("axmed-ocr-service")],
)
@modal.asgi_app(label=APP_NAME)
def fastapi_app():
    from fastapi import FastAPI, Header, HTTPException
    from pydantic import BaseModel, Field

    class OcrRequest(BaseModel):
        schema_version: str
        media_type: str
        content_base64: str
        selected_original_pages: list[int] = Field(min_length=1)
        idempotency_key: str = Field(min_length=1, max_length=200)
        deadline_ms: int = Field(ge=1, le=120_000)

    web_app = FastAPI(title="Axmed OCR", version=SCHEMA_VERSION, docs_url=None, redoc_url=None)

    @web_app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": APP_NAME, "schema_version": SCHEMA_VERSION}

    @web_app.post("/ocr")
    async def ocr(request: OcrRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        try:
            _authenticate(authorization)
            if request.schema_version != SCHEMA_VERSION:
                raise ValueError("unsupported_schema_version")
            content = base64.b64decode(request.content_base64, validate=True)
            return run_ocr(content, request.media_type, request.selected_original_pages)
        except PermissionError as error:
            raise HTTPException(status_code=401, detail="unauthorized") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="ocr_provider_error") from error

    return web_app
