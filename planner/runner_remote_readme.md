Short instructions:

- To run remote pack, set env:
  - USE_REMOTE_MODEL=1
  - REMOTE_PROVIDER=openai
  - OPENAI_API_KEY=<your_key>
  - REMOTE_OPENAI_MODEL=gpt-5.1 (or preferred)
- Then run:
  python scripts/run_obedience_pack_remote.py
- This uses planner/remote_adapter.call_remote_planner and writes reports/obedience_report_remote.json
- The remote adapter returns planner-like JSON but you must not execute actions automatically from it.
