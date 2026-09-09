"""Application version shared by Streamlit and FastAPI (not profile schema)."""

from pathlib import Path

APP_VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
