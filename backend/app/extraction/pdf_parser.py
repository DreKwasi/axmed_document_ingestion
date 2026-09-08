"""LiteParse-backed PDF parser boundary with explicit page-level quality signals."""

import dataclasses
from dataclasses import dataclass

from liteparse import LiteParse
from liteparse.types import ParseError


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
    try:
        parser = LiteParse(ocr_enabled=False, quiet=True)
        result = parser.parse(data)
        pages = tuple(
            ParsedPdfPage(
                page_number=page.page_num,
                text=page.text.strip(),
                native_text_characters=len(page.text),
                quality=_quality(page.text),
                width=page.width,
                height=page.height,
                raw_representation={"page": page.page_num, **dataclasses.asdict(page)},
                text_items=tuple(
                    {
                        "text": item.text,
                        "x": item.x,
                        "y": item.y,
                        "width": item.width,
                        "height": item.height,
                        "confidence": item.confidence,
                    }
                    for item in page.text_items
                ),
            )
            for page in result.pages
        )
    except (ParseError, TimeoutError, OSError, ValueError, RuntimeError) as error:
        raise PdfParseError("LiteParse could not read the uploaded PDF.") from error
    if not pages:
        raise PdfParseError("The uploaded PDF has no pages.")
    return ParsedPdf(pages=pages)
