from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv


# Load environment from a local .env if present
load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    # External APIs
    BIBLE_API_KEY: str | None = os.getenv("BIBLE_API_KEY")
    BIBLE_API_BIBLE_ID: str = os.getenv("BIBLE_API_BIBLE_ID", "06125adad2d5898a-01")

    # Defaults and behavior
    DEFAULT_TRANSLATION: str = os.getenv("DEFAULT_TRANSLATION", "kjv")
    DEFAULT_CONTEXT_VERSES: int = int(os.getenv("BIBLEFIGHT_DEFAULT_CONTEXT_VERSES", "7"))
    DEFAULT_SNIPPET_CHARS: int = int(os.getenv("BIBLEFIGHT_DEFAULT_SNIPPET_CHARS", "180"))
    DEFAULT_INCLUDE_SNIPPETS: bool = _get_bool("BIBLEFIGHT_INCLUDE_SNIPPETS", True)
    DEFAULT_MAX_RESULTS: int = int(os.getenv("BIBLEFIGHT_DEFAULT_MAX_RESULTS", "5"))
    DEFAULT_INCLUDE_SUPPORTING: bool = _get_bool("BIBLEFIGHT_INCLUDE_SUPPORTING", True)
    DEFAULT_INCLUDE_CHALLENGERS: bool = _get_bool("BIBLEFIGHT_INCLUDE_CHALLENGERS", True)
    LOG_LEVEL: str = os.getenv("BIBLEFIGHT_LOG_LEVEL", "INFO")


