from __future__ import annotations

import hashlib
import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Shared deterministic seed for training utilities.
SEED = 1337
random.seed(SEED)

REPORTS_DIR = Path("reports")
ARCHIVES_DIR = REPORTS_DIR / "archives"


def utc_timestamp() -> str:
    """Return a compact UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def iso_timestamp() -> str:
    """Return an ISO-8601 timestamp with timezone."""
    return datetime.now(timezone.utc).isoformat()


def log_line(log_path: Optional[Path], message: str) -> None:
    """Append a timestamped line to the provided log file."""
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{iso_timestamp()}] {message}\n")


def backup_file(path: Path, log_path: Optional[Path] = None) -> Optional[Path]:
    """
    If ``path`` exists, copy it into the archives directory before overwriting.

    Returns the backup path when created.
    """
    if not path.exists():
        return None
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = ARCHIVES_DIR / f"{path.name}.{utc_timestamp()}.bak"
    shutil.copy2(path, backup_path)
    log_line(log_path, f"BACKUP {path.as_posix()} -> {backup_path.as_posix()}")
    return backup_path


def deterministic_hash(parts: Iterable[Any]) -> str:
    """Build a SHA256 hex digest from an iterable of components."""
    hasher = hashlib.sha256()
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (bytes, bytearray)):
            hasher.update(part)
        else:
            hasher.update(str(part).encode("utf-8"))
    return hasher.hexdigest()


def write_json(path: Path, data: Any) -> None:
    """Write JSON to disk with stable ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


__all__ = [
    "ARCHIVES_DIR",
    "REPORTS_DIR",
    "SEED",
    "backup_file",
    "deterministic_hash",
    "iso_timestamp",
    "log_line",
    "utc_timestamp",
    "write_json",
]
