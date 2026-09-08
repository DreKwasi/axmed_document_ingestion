"""Signature-based image validation for the OCR intake boundary."""

from dataclasses import dataclass

# --- Section 1: Domain Exceptions & Data Transfer Objects ---


class ImageParseError(ValueError):
    """Raised for image bytes that cannot safely be routed to OCR."""


@dataclass(frozen=True)
class ParsedImage:
    """Basic image format and dimension metadata."""

    media_type: str
    width: int
    height: int


# --- Section 2: Pure-Python Magic Byte & Dimension Parsing ---


def parse_image(data: bytes) -> ParsedImage:
    """Inspect binary image headers to verify format and extract dimensions.

    Supports:
    - PNG: Magic header `\\x89PNG\\r\\n\\x1a\\n`, reads IHDR width and height.
    - JPEG: Magic marker `\\xff\\xd8`, walks SOF markers to extract width and height.

    Args:
        data: Raw binary byte content of the image.

    Returns:
        ParsedImage with media_type ('image/png' or 'image/jpeg') and dimensions.

    Raises:
        ImageParseError: If the binary data does not match supported image formats.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        if width > 0 and height > 0:
            return ParsedImage("image/png", width, height)
    if data.startswith(b"\xff\xd8"):
        position = 2
        while position + 9 < len(data):
            if data[position] != 0xFF:
                position += 1
                continue
            marker = data[position + 1]
            position += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if position + 2 > len(data):
                break
            length = int.from_bytes(data[position : position + 2], "big")
            if length < 2 or position + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[position + 3 : position + 5], "big")
                width = int.from_bytes(data[position + 5 : position + 7], "big")
                if width > 0 and height > 0:
                    return ParsedImage("image/jpeg", width, height)
                break
            position += length
    raise ImageParseError("The uploaded content does not have a supported PNG or JPEG signature.")
