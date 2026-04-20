"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    FIREBASE_CREDENTIALS: str | None = os.getenv("FIREBASE_CREDENTIALS")
    FIREBASE_CREDENTIALS_JSON: str | None = os.getenv("FIREBASE_CREDENTIALS_JSON")
    FIREBASE_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")

    FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
    # Cloud Run injects a PORT env var that the container must bind to.
    FLASK_PORT: int = int(os.getenv("PORT") or os.getenv("FLASK_PORT") or "5000")
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "0") in {"1", "true", "True"}

    DEFAULT_FROM_INSTITUTION: str = os.getenv(
        "DEFAULT_FROM_INSTITUTION", "College of San Mateo"
    )


config = Config()
