"""Windows-safe atomic JSON persistence for concurrently viewed session files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4


def atomic_write_json(path: str | Path, value: Any, *, attempts: int = 8) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    try:
        for attempt in range(attempts):
            try:
                os.replace(temporary, target)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        if temporary.exists():
            temporary.unlink()
