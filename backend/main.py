"""Local FastAPI entry point.

Run from ``backend/`` with:
    uv run uvicorn main:app --reload
"""

from app.api import create_app

app = create_app()
