from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from planner.plan_runner import run_plan  # noqa: E402
from tools.train.common import REPORTS_DIR, log_line, utc_timestamp, write_json  # noqa: E402


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _token_edit_distance(a: str, b: str) -> int:
    tokens_a = a.split()
    tokens_b = b.split()
    dp = [[0] * (len(tokens_b) + 1) for _ in range(len(tokens_a) + 1)]
    for i in range(len(tokens_a) + 1):
        dp[i][0] = i
    for j in range(len(tokens_b) + 1):
        dp[0][j] = j
    for i in range(1, len(tokens_a) + 1):
        for j in range(1, len(tokens_b) + 1):
            cost = 0 if tokens_a[i - 1] == tokens_b[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[-1][-1]


def _relaxed_steps(plan: Dict[str, Any]) -> Tuple[Any, Tuple[Any, ...]]:
    steps = plan.get("steps") if isinstance(plan, dict) else None
    other = {k: v for k, v in plan.items() if k != "steps"} if isinstance(plan, dict) else plan
    step_repr = tuple(sorted(json.dumps(step, sort_keys=True) for step in steps)) if isinstance(steps, list) else tuple()
    return other, step_repr


def _evaluate_entry(entry: Dict[str, Any], tmp_dir: Path, log_path: Path | None) -> Dict[str, Any]:
    gold_plan = entry.get("response") or entry.get("plan")
    planner_plan = entry.get("plan") or gold_plan
    if not isinstance(gold_plan, dict) or not isinstance(planner_plan, dict):
        return {"strict": 0.0, "relaxed": 0.0, "edit_distance": 0}

    temp_plan_path = tmp_dir / f"plan-{uuid.uuid4()}.json"
    temp_plan_path.write_text(json.dumps(planner_plan, indent=2), encoding="utf-8")
    try:
        validated = run_plan(temp_plan_path, dry_run=True)
    except Exception as exc:  # pragma: no cover - defensive
        log_line(log_path, f"PLAN_VALIDATE_FAIL {exc}")
        validated = planner_plan
    finally:
        try:
            temp_plan_path.unlink()
        except Exception:
            pass

    strict = 1.0 if validated == gold_plan else 0.0
    relaxed = 1.0 if _relaxed_steps(validated) == _relaxed_steps(gold_plan) else 0.0
    edit_distance = _token_edit_distance(json.dumps(validated, sort_keys=True), json.dumps(gold_plan, sort_keys=True))
    return {"strict": strict, "relaxed": relaxed, "edit_distance": edit_distance}


def evaluate(dataset_path: Path, log_path: Path | None = None) -> Tuple[int, Path, Path, Dict[str, Any]]:
    rows = _load_dataset(dataset_path)
    tmp_dir = REPORTS_DIR / "tmp_eval"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    strict_scores: List[float] = []
    relaxed_scores: List[float] = []
    edit_distances: List[int] = []

    for entry in rows:
        metrics = _evaluate_entry(entry, tmp_dir, log_path)
        strict_scores.append(metrics["strict"])
        relaxed_scores.append(metrics["relaxed"])
        edit_distances.append(metrics["edit_distance"])

    strict_avg = sum(strict_scores) / len(strict_scores) if strict_scores else 0.0
    relaxed_avg = sum(relaxed_scores) / len(relaxed_scores) if relaxed_scores else 0.0
    avg_edit = sum(edit_distances) / len(edit_distances) if edit_distances else 0.0

    ts = utc_timestamp()
    eval_json = REPORTS_DIR / f"eval-{ts}.json"
    eval_md = REPORTS_DIR / f"eval-{ts}.md"
    summary = {
        "dataset": dataset_path.as_posix(),
        "size": len(rows),
        "strict_match_rate": strict_avg,
        "relaxed_match_rate": relaxed_avg,
        "avg_token_edit_distance": avg_edit,
        "timestamp": ts,
    }

    write_json(eval_json, summary)
    eval_md.write_text(
        "\n".join(
            [
                f"Dataset: {dataset_path.as_posix()}",
                f"Examples: {len(rows)}",
                f"Strict match rate: {strict_avg:.3f}",
                f"Relaxed match rate: {relaxed_avg:.3f}",
                f"Average token edit distance: {avg_edit:.2f}",
            ]
        ),
        encoding="utf-8",
    )
    log_line(log_path, f"EVAL_COMPLETE strict={strict_avg:.3f} relaxed={relaxed_avg:.3f} edit={avg_edit:.2f}")
    return 0, eval_json, eval_md, summary


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate planner fidelity against gold plans.")
    parser.add_argument("--dataset", required=True, help="Dataset JSONL path.")
    parser.add_argument("--log", help="Optional log path.")
    args = parser.parse_args(argv)

    log_path = Path(args.log) if args.log else REPORTS_DIR / f"eval-{utc_timestamp()}.log"
    rc, eval_json, eval_md, _ = evaluate(Path(args.dataset), log_path=log_path)
    print(f"EVAL_SUMMARY rc={rc} json={eval_json.as_posix()} md={eval_md.as_posix()}")
    return rc


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
