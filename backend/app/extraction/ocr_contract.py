"""Versioned OCR evidence contract at the Axmed provider boundary."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Section 1: Line & Bounding Polygon Models ---


class OcrLine(BaseModel):
    """One recognized line of text with spatial polygon coordinates and confidence.

    Attributes:
        text: Transcribed line content.
        confidence: Line recognition certainty (0.00 to 1.00).
        bounds: Four [x, y] coordinates defining the oriented bounding box polygon.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float = Field(ge=0, le=1)
    bounds: list[list[float]] = Field(min_length=4, max_length=4)

    @field_validator("bounds")
    @classmethod
    def bounds_must_be_xy_pairs(cls, value: list[list[float]]) -> list[list[float]]:
        """Ensure boundary list contains precisely four 2D point coordinates."""
        if any(len(point) != 2 for point in value):
            raise ValueError("OCR bounds must contain four [x, y] points.")
        return value


# --- Section 2: Page-Level OCR Containers ---


class OcrPage(BaseModel):
    """Page-level OCR container with resolution and line collection."""

    model_config = ConfigDict(extra="forbid")

    original_page_number: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    dpi: int = Field(gt=0)
    lines: list[OcrLine]


# --- Section 3: Aggregate OCR Result & Client Protocols ---


class OcrResult(BaseModel):
    """Top-level result returned from the remote OCR microservice."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    provider: str
    model: str
    configuration_version: str
    duration_ms: int = Field(ge=0)
    pages: list[OcrPage]


class OcrClient(Protocol):
    """Protocol for remote or mock OCR service providers."""

    def ocr(
        self,
        data: bytes,
        *,
        media_type: str,
        selected_original_pages: tuple[int, ...],
        idempotency_key: str,
        deadline_ms: int,
    ) -> OcrResult:
        """Submit document binary data to the OCR service."""
        ...
