import json
from pathlib import Path
from typing import Any, List, Tuple

from retrieval.embed import embed_texts
from telemetry.logger import log_event

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover
    faiss = None

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class _InMemoryIndex:
    def __init__(self, dim: int):
        self.dim = dim
        self.vectors: List[List[float]] = []

    def add(self, vectors: List[List[float]]):
        for v in vectors:
            self.vectors.append(list(v))

    def search(self, queries: List[List[float]], k: int):
        results = []
        for q in queries:
            q_vec = list(q)
            scored = []
            for idx, v in enumerate(self.vectors):
                score = sum((qi - vi) ** 2 for qi, vi in zip(q_vec, v))
                scored.append((score, idx))
            scored.sort(key=lambda x: x[0])
            scores = [s for s, _ in scored[:k]]
            ids = [i for _, i in scored[:k]]
            results.append((scores, ids))
        # mimic faiss return shape
        scores = [r[0] for r in results]
        ids = [r[1] for r in results]
        return scores, ids


def _load_documents(corpus_dir: Path) -> List[str]:
    docs: List[str] = []
    for path in sorted(corpus_dir.glob("*.jsonl")):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                snippet = data.get("text") or json.dumps(data, ensure_ascii=True)
                docs.append(snippet)
    return docs


def build_index(corpus_dir: Path | None = None) -> Tuple[Any, List[str]]:
    corpus_dir = corpus_dir or Path(__file__).resolve().parent / "corpus"
    docs = _load_documents(Path(corpus_dir))
    vectors = embed_texts(docs if docs else ["empty"])
    dim = len(vectors[0])

    use_faiss = faiss is not None and np is not None
    index = faiss.IndexFlatL2(dim) if use_faiss else _InMemoryIndex(dim)

    if use_faiss:
        index.add(np.asarray(vectors, dtype="float32"))
    else:
        index.add(vectors.tolist() if hasattr(vectors, "tolist") else vectors)
    return index, docs


def query_index(index: Any, docs: List[str], text: str, top_k: int = 3) -> List[Tuple[float, str]]:
    queries = embed_texts([text])
    if faiss is not None and np is not None:
        prepared_queries = np.asarray(queries, dtype="float32")
    else:
        prepared_queries = queries.tolist() if hasattr(queries, "tolist") else queries
    distances, ids = index.search(prepared_queries, top_k)
    if hasattr(distances, "tolist"):
        distances = distances.tolist()
    if hasattr(ids, "tolist"):
        ids = ids.tolist()
    results: List[Tuple[float, str]] = []
    for score, idx in zip(distances[0], ids[0]):
        if idx < 0 or idx >= len(docs):
            continue
        results.append((float(score), docs[idx]))
    retrieval_ids = ids[0] if ids else []
    try:
        log_event({"event": "retrieval", "retrieval_ids": retrieval_ids, "query": text})
    except Exception:
        pass
    return results
