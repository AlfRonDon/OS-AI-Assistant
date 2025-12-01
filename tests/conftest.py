import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Avoid loading the large local LLM during tests; use deterministic fallback unless explicitly overridden.
os.environ.setdefault("DISABLE_LOCAL_LLM", "1")
