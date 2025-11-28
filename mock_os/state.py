import copy
from typing import Dict, Any, List

STATE: Dict[str, Any] = {
    "windows": [{"id": "desktop", "title": "Desktop", "active": True}],
    "settings": {"volume": 50, "wifi": "on"},
    "logs": [],
    "clipboard": "",
}

HISTORY: List[Dict[str, Any]] = []


def snapshot() -> Dict[str, Any]:
    return copy.deepcopy(STATE)


def save_checkpoint() -> None:
    HISTORY.append(snapshot())


def restore_last() -> Dict[str, Any]:
    if not HISTORY:
        return snapshot()
    previous = HISTORY.pop()
    set_state(previous)
    return snapshot()


def set_state(new_state: Dict[str, Any]) -> None:
    STATE.clear()
    STATE.update(copy.deepcopy(new_state))


def append_log(message: str) -> None:
    STATE.setdefault("logs", []).append(message)


def set_clipboard(text: str) -> None:
    STATE["clipboard"] = text


def add_window(window: Dict[str, Any]) -> None:
    STATE.setdefault("windows", []).append(copy.deepcopy(window))


def update_setting(key: str, value: Any) -> None:
    STATE.setdefault("settings", {})[key] = value


def validate(expected_state: Dict[str, Any]) -> bool:
    if not expected_state:
        return True
    current = snapshot()
    for key, value in expected_state.items():
        if current.get(key) != value:
            return False
    return True
