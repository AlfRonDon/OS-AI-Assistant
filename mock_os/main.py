import json
from pathlib import Path

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover
    class FastAPI:  # minimal fallback to keep imports working
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def post(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

from mock_os import state
from mock_os.executor import dry_run, run, undo
from planner.schema import Plan

app = FastAPI(title="Mock OS Runtime", version="0.1.0")

ELEMENTS_PATH = Path(__file__).resolve().parent / "elements.json"


def load_elements():
    with open(ELEMENTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/state")
def get_state():
    return state.snapshot()


@app.get("/elements")
def get_elements():
    return load_elements()


@app.post("/exec/dry-run")
def exec_dry_run(plan: Plan):
    return dry_run(plan)


@app.post("/exec/run")
def exec_run(plan: Plan):
    return run(plan)


@app.post("/undo")
def exec_undo():
    return undo()


__all__ = ["app"]
