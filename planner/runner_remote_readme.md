Remote planner wiring

- Enable the runner path: set `USE_REMOTE_MODEL=1` so `planner/runner.py` prefers the remote adapter.
- Point the adapter: set `REMOTE_PROVIDER=openai` or `REMOTE_PROVIDER=google` plus the matching API key.
- OpenAI example env:
  - `OPENAI_API_KEY=<key>` (required)
  - `REMOTE_OPENAI_MODEL=gpt-4.1` (or your preferred model)
  - Optional: `OPENAI_BASE_URL=https://api.openai.com/v1`, `OPENAI_ORG`, `OPENAI_PROJECT`
- Google example env:
  - `GOOGLE_API_KEY=<key>` (required)
  - `REMOTE_GOOGLE_MODEL=gemini-1.5-pro-latest`
  - Optional: `GOOGLE_API_BASE=https://generativelanguage.googleapis.com`
- Smoke test the adapter:
  - `python scripts/run_planner_remote_once.py "Summarize the current workspace layout"`
  - Writes `reports/remote_planner_test.json` and reports validation in stdout.
- Full remote obedience pack (optional):
  - `python scripts/run_obedience_pack_remote.py`
  - Writes `reports/obedience_report_remote.json` using the same adapter.
- Planner output is validated against `contracts/planner_output.schema.json` before returning; only the plan dict is returned, no secrets are logged.
- Example curl (OpenAI) for a one-off JSON response (replace the API key env var):
  ```bash
  curl -X POST https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4.1","messages":[{"role":"system","content":"Return only PlannerOutput JSON (contracts/planner_output.schema.json)."},{"role":"user","content":"{\"user_query\":\"Check remote planning\",\"retrieval_snippets\":[],\"state_snapshot\":{}}"}],"response_format":{"type":"json_object"}}'
  ```
