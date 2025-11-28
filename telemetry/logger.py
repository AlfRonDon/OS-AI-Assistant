import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def log_event(event: Dict[str, Any]) -> None:
    base = Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    path = base / "events.log"
    payload = {"timestamp": datetime.utcnow().isoformat() + "Z"}
    payload.update(event)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
