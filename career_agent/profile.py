from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR

PROFILE_PATH = DATA_DIR / "profile.json"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def save_profile(profile: dict[str, Any], path: Path = PROFILE_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")


def load_profile(path: Path = PROFILE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
