"""LiteParse-backed PDF parser boundary with explicit page-level quality signals."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from liteparse import LiteParse
from liteparse.types import ParseError

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _liteparse_cli_path() -> str:
    """Resolve the build-installed CLI without allowing a runtime npx download."""

    installed_cli = BACKEND_ROOT / "node_modules" / ".bin" / "liteparse"
    if installed_cli.is_file():
        return str(installed_cli)
    path_cli = shutil.which("liteparse")
    if path_cli:
        return path_cli
    raise PdfParseError("The LiteParse CLI is not installed in the API runtime.")


class PdfParseError(ValueError):
    """Raised when a submitted PDF cannot safely yield native text."""


@dataclass(frozen=True)
class ParsedPdfPage:
    page_number: int
    text: str
    native_text_characters: int
    quality: str
    width: float | None = None
    height: float | None = None
    raw_representation: dict[str, object] | None = None
    text_items: tuple[dict[str, float | str | None], ...] = ()


@dataclass(frozen=True)
class ParsedPdf:
    pages: tuple[ParsedPdfPage, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    @property
    def needs_ocr_pages(self) -> tuple[int, ...]:
        return tuple(page.page_number for page in self.pages if page.quality == "poor")


def _quality(text: str) -> str:
    """Keep the OCR escalation decision explainable and deliberately conservative."""

    return "good" if len(text.strip()) >= 80 else "poor"


def parse_native_pdf(data: bytes) -> ParsedPdf:
    """Recover native reading order and table layout with the PRD-mandated LiteParse adapter."""

    if not data.startswith(b"%PDF-"):
        raise PdfParseError("The uploaded content does not have a PDF signature.")
    cli_path = _liteparse_cli_path()
    try:
        result = LiteParse(cli_path=cli_path, install_if_not_available=False).parse(data, ocr_enabled=False, timeout=60)
        pages = tuple(
            ParsedPdfPage(
                page_number=page.pageNum,
                text=page.text.strip(),
                native_text_characters=len(page.text),
                quality=_quality(page.text),
                width=page.width,
                height=page.height,
                raw_representation=page_data,
                text_items=tuple(
                    {
                        "text": item.text,
                        "x": item.x,
                        "y": item.y,
                        "width": item.width,
                        "height": item.height,
                        "confidence": item.confidence,
                    }
                    for item in page.textItems
                ),
            )
            for page, page_data in zip(result.pages, (result.json or {}).get("pages", []), strict=False)
        )
    except (ParseError, TimeoutError, OSError, ValueError) as error:
        raise PdfParseError("LiteParse could not read the uploaded PDF.") from error
    if not pages:
        raise PdfParseError("The uploaded PDF has no pages.")
    return ParsedPdf(pages=pages)
