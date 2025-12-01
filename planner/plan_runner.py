from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from planner.validate_schema import load_plan, validate_plan


def run_plan(input_path: Path, dry_run: bool = False) -> dict[str, Any]:
    plan = load_plan(input_path)
    validate_plan(plan)
    if dry_run:
        # Dry-run implies validation only; no execution side effects.
        return plan
    return plan


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load and validate a planner plan JSON.")
    parser.add_argument("--input", required=True, help="Path to the plan JSON to load.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; no execution (plan still printed).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output instead of a single line.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input)
    try:
        plan = run_plan(input_path, dry_run=args.dry_run)
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"plan validation failed: {exc}", file=sys.stderr)
        return 1

    indent = 2 if args.pretty or args.dry_run else None
    print(json.dumps(plan, indent=indent))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
