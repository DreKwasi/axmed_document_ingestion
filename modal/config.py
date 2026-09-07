"""Modal OCR client and service configuration.

Loads environment variables once and provides simple, direct configuration access.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

MODAL_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODAL_ROOT.parent

for env_candidate in (WORKSPACE_ROOT / "backend" / ".env", WORKSPACE_ROOT / ".env", Path(".env")):
    if env_candidate.is_file():
        load_dotenv(env_candidate, override=False)

OCR_SERVICE_URL: str = os.environ.get("OCR_SERVICE_URL", "https://andrewsboateng137--axmed-paddle-ocr.modal.run/ocr")
OCR_SERVICE_TOKEN: str = os.environ.get("OCR_SERVICE_TOKEN", "")
