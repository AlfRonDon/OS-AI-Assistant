#!/usr/bin/env python3
"""
Remote obedience pack runner.
Reads tests/obedience_prompts.json and for each prompt:
- retrieves top-k snippets using retrieval/index.py (use existing retrieval.index.query_topk or implement a local call)
- calls planner/remote_adapter.call_remote_planner(...)
- validates minimal shape and writes per-prompt results
- produces reports/obedience_report_remote.json with same schema as local runner
"""
import os, sys, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from planner import remote_adapter
# Try to import existing retrieval API; fallback to simple corpus search if missing
try:
    from retrieval.index import query_topk
except Exception:
    query_topk = None

OUT = Path("reports/obedience_report_remote.json")
PROMPTS = Path("tests/obedience_prompts.json")
CORPUS_DIR = Path("retrieval/corpus")
K = int(os.environ.get("REMOTE_TOPK","3"))

def local_fallback_search(query, k=3):
    # naive substring search over corpus jsonl files
    snippets = []
    for p in CORPUS_DIR.glob("*.jsonl"):
        with p.open("r", encoding="utf8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except:
                    continue
                text = (obj.get("description","") + " " + " ".join([s.get("snippet","") if isinstance(s,dict) else "" for s in [obj]]))
                if query.lower() in text.lower():
                    snippets.append({"id": obj.get("id","unknown"), "cursor_score": 0.9, "snippet": obj.get("description","")})
    return snippets[:k]

def run_once(prompt, idx):
    # retrieval
    if query_topk:
        snippets = query_topk(prompt, k=K)
    else:
        snippets = local_fallback_search(prompt, k=K)
    # state snapshot stub (use existing mock_os state if available)
    try:
        from mock_os.state import current_state_snapshot
        state = current_state_snapshot()
    except Exception:
        state = {"windows": [], "permissions": [], "clipboard": None}
    # call remote adapter
    out = remote_adapter.call_remote_planner(snippets, state, prompt, timeout_seconds=15)
    # minimal sanity
    valid = remote_adapter.minimal_sanity_check(out)
    result = {
        "id": idx,
        "prompt": prompt,
        "result": out,
        "valid": bool(valid),
        "time_s": None
    }
    return result

def main():
    prompts = json.loads(PROMPTS.read_text(encoding="utf8"))
    results = []
    t0 = time.time()
    for i,p in enumerate(prompts):
        try:
            r = run_once(p, i)
        except Exception as e:
            r = {"id": i, "prompt": p, "result": {"error": str(e)}, "valid": False}
        results.append(r)
    report = {
        "total": len(results),
        "valid_count": sum(1 for r in results if r["valid"]),
        "extra_field_count": 0,
        "avg_confidence": sum((r["result"].get("confidence") or 0) for r in results)/max(1,len(results)),
        "per_prompt": results
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf8")
    print("WROTE:", OUT)

if __name__ == "__main__":
    main()
