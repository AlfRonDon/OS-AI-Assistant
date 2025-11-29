"""Remote planner adapter.

Usage:
- Set environment variables:
  - USE_REMOTE_MODEL=1
  - REMOTE_PROVIDER="openai"  (or "google" in the future)
  - OPENAI_API_KEY (if using openai)
- Call call_remote_planner(retrieval_snippets, state_snapshot, user_query)
"""

import os, json, time, typing, requests

# Only implement OpenAI provider here. No keys stored.
def _call_openai_chat(messages, functions=None, timeout=10):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    try:
        resp = client.chat.create(model=os.environ.get("REMOTE_OPENAI_MODEL","gpt-5.1"), messages=messages, functions=functions or [], timeout=timeout)
        return resp
    except Exception as e:
        raise

def call_remote_planner(retrieval_snippets: list, state_snapshot: dict, user_query: str, timeout_seconds: int = 10) -> dict:
    """
    Calls remote provider and returns a PlannerOutput-like dict.
    Must validate JSON shape minimally (keys present). Caller must still validate fully.
    """
    provider = os.environ.get("REMOTE_PROVIDER","openai").lower()
    start = time.time()
    if provider == "openai":
        # build a compact prompt: system + user + retrieval + state
        system = {
            "role":"system",
            "content":"You are a deterministic planner. Return ONLY JSON matching the PlannerOutput schema. If you cannot, return {\"intent\":\"<user_intent>\",\"slots\":{},\"steps\":[],\"sources\":[],\"confidence\":0.0,\"error\":\"NO_GROUNDING\"}."
        }
        user = {
            "role":"user",
            "content": json.dumps({
                "retrieval_snippets": retrieval_snippets,
                "state_snapshot": state_snapshot,
                "user_query": user_query
            })
        }
        messages = [system, user]
        try:
            resp = _call_openai_chat(messages, timeout=timeout_seconds)
            # Attempt to extract content
            content = None
            # compatible with OpenAI python client: resp.choices[0].message.content
            try:
                content = resp.choices[0].message["content"]
            except Exception:
                content = getattr(resp.choices[0].message, "content", None)
            if not content:
                raise RuntimeError("no content from remote")
            # Try parse JSON
            parsed = json.loads(content)
            return parsed
        except Exception as e:
            return {"intent": user_query, "slots": {}, "steps": [], "sources": [], "confidence": 0.0, "error": f"REMOTE_CALL_FAIL: {str(e)}"}
    else:
        return {"intent": user_query, "slots": {}, "steps": [], "sources": [], "confidence": 0.0, "error": "UNSUPPORTED_REMOTE_PROVIDER"}

# minimal JSON sanity helper (not full schema validation)
def minimal_sanity_check(planner_output: dict) -> bool:
    if not isinstance(planner_output, dict):
        return False
    required = ["intent","steps","sources","confidence"]
    for k in required:
        if k not in planner_output:
            return False
    return True

if __name__ == "__main__":
    print("planner.remote_adapter loaded. This module does NOT run by itself.")
