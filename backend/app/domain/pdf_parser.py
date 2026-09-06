"""Native-PDF parser boundary with explicit page-level quality signals."""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfParseError(ValueError):
    """Raised when a submitted PDF cannot safely yield native text."""


@dataclass(frozen=True)
class ParsedPdfPage:
    page_number: int
    text: str
    native_text_characters: int
    quality: str


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
    if not data.startswith(b"%PDF-"):
        raise PdfParseError("The uploaded content does not have a PDF signature.")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise PdfParseError("Encrypted PDFs are not supported.")
        extracted_pages: list[ParsedPdfPage] = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text(extraction_mode="layout") or ""
            extracted_pages.append(
                ParsedPdfPage(
                    page_number=index + 1,
                    text=text.strip(),
                    native_text_characters=len(text),
                    quality=_quality(text),
                )
            )
        pages = tuple(extracted_pages)
    except (PdfReadError, OSError, ValueError) as error:
        if isinstance(error, PdfParseError):
            raise
        raise PdfParseError("The uploaded PDF could not be read.") from error
    if not pages:
        raise PdfParseError("The uploaded PDF has no pages.")
    return ParsedPdf(pages=pages)
