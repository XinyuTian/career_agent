from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "career.db"
RESUME_DIR = ROOT / "generated_resumes"
DEFAULT_BASE_URL = "https://space.ai-builders.com/backend"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    chat_model: str = "deepseek"
    embedding_model: str = "text-embedding-3-small"

    @property
    def v1_base_url(self) -> str:
        return self.base_url.rstrip("/") + "/v1"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_settings() -> Settings:
    load_dotenv()
    api_key = (
        os.environ.get("AI_BUILDER_TOKEN", "").strip()
        or os.environ.get("AI_BUILDER_API_KEY", "").strip()
    )
    if not api_key:
        raise RuntimeError(
            "Missing AI_BUILDER_TOKEN (or AI_BUILDER_API_KEY). Add it to .env first."
        )
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("AI_BUILDER_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        chat_model=os.environ.get("AI_BUILDER_CHAT_MODEL", "deepseek").strip() or "deepseek",
        embedding_model=os.environ.get("AI_BUILDER_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        or "text-embedding-3-small",
    )
