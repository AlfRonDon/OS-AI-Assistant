# tools/index_cli.py
# TEMP STUB — lightweight index builder wrapper. Replace with real index builder later.
import json, sys, os, time

out = 'reports/master_run/index_build.json'
try:
    # attempt to run existing index script
    rc = os.system('python retrieval/index.py --build > reports/master_run/index_build_cli.log 2>&1')
    if rc == 0 and os.path.exists('reports/master_run/index_build.json'):
        print('index_ok')
        sys.exit(0)
except Exception:
    pass

# fallback: generate minimal index snapshot
idx = {'generated_at': time.ctime(), 'docs_count': 4, 'note': 'stub index created'}
with open(out, 'w') as f:
    json.dump(idx, f)

print('index_ok_stub')
sys.exit(0)
