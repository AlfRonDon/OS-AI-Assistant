"""
Deterministic embedding stub for tests and offline pipelines.

The goal is to provide a predictable vector for any input text without
requiring GPU/runtime dependencies. Output vectors are normalized to
make distance computations stable across runs.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List, Sequence

DEFAULT_DIMENSION = 256


def _hash_to_vector(text: str, dim: int = DEFAULT_DIMENSION) -> List[float]:
    """
    Convert text into a deterministic pseudo-embedding of length ``dim``.

    The implementation hashes the input and maps bytes to a bounded float vector.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    bytes_needed = dim * 2  # two bytes per slot for stable scaling
    buf = (digest * ((bytes_needed // len(digest)) + 1))[:bytes_needed]
    raw_vals = [int.from_bytes(buf[i : i + 2], "big") % 1000 for i in range(0, bytes_needed, 2)]
    total = float(sum(raw_vals) or 1)
    return [v / total for v in raw_vals]


def embed_texts(texts: Sequence[str], dim: int = DEFAULT_DIMENSION) -> List[List[float]]:
    """
    Embed a sequence of texts into deterministic vectors.

    Args:
        texts: Iterable of input strings.
        dim: Output vector length. Defaults to ``DEFAULT_DIMENSION`` (256).
    """
    if not isinstance(texts, Iterable):
        raise TypeError("texts must be iterable")
    return [_hash_to_vector(str(t), dim=dim) for t in texts]


__all__ = ["embed_texts", "DEFAULT_DIMENSION"]
