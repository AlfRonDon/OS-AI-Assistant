import hashlib
import os
from pathlib import Path
from typing import Any, List

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    from llama_cpp import Llama  # type: ignore
except ImportError:  # pragma: no cover
    Llama = None  # type: ignore


_LLAMA = None


def _hash_vector(text: str, dim: int = 16) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vals = [int.from_bytes(digest[i : i + 2], "big") % 1000 for i in range(0, dim * 2, 2)]
    norm = float(sum(vals) or 1)
    return [v / norm for v in vals]


def _load_llama() -> Any:
    global _LLAMA
    if _LLAMA is not None or Llama is None:
        return _LLAMA
    model_path = (
        os.getenv("GPT_OSS_MODEL_PATH")
        or os.getenv("LLAMA_EMBED_MODEL")
        or os.getenv("LLAMA_MODEL_PATH")
        or os.path.join("models", "gpt-oss-20b.gguf")
        or "gpt-oss-20b.gguf"
    )
    candidate = Path(model_path)
    if not candidate.exists():
        return None
    try:
        _LLAMA = Llama(model_path=str(candidate), embedding=True, seed=0)
    except Exception:
        _LLAMA = None
    return _LLAMA


def _embed_with_llama(llm: Any, text: str) -> List[float] | None:
    if hasattr(llm, "embed"):
        return llm.embed(text)  # type: ignore[attr-defined]
    if hasattr(llm, "create_embedding"):
        response = llm.create_embedding(inputs=[text])  # type: ignore[attr-defined]
        data = response.get("data") or []
        if data and isinstance(data[0], dict):
            embedding = data[0].get("embedding")
            if embedding is not None:
                return embedding
    return None


def embed_texts(texts: List[str]):
    llm = _load_llama()
    if llm is not None:
        llama_vectors: List[List[float]] = []
        for text in texts:
            vec = _embed_with_llama(llm, text)
            if vec is None:
                llama_vectors = []
                break
            llama_vectors.append(vec)
        if llama_vectors:
            return np.asarray(llama_vectors, dtype="float32") if np is not None else llama_vectors

    hashed_vectors = [_hash_vector(t) for t in texts]
    return np.asarray(hashed_vectors, dtype="float32") if np is not None else hashed_vectors
