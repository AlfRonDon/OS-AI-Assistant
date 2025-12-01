import json
from pathlib import Path

from retrieval.index import build_index
from retrieval.index_persist import persist_index_to_pgvector


def test_persist_index_fallback_creates_file():
    repo_root = Path(__file__).resolve().parents[1]
    fallback_path = repo_root / "replays" / "pgvector_fallback.json"
    if fallback_path.exists():
        fallback_path.unlink()

    index, docs = build_index()
    metadata = [{"id": str(i), "text": doc} for i, doc in enumerate(docs)]

    result_path = persist_index_to_pgvector(index, metadata, None, "test-snapshot")

    assert fallback_path.exists()
    assert result_path == fallback_path

    with open(fallback_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["version"] == "test-snapshot"
    assert len(data["records"]) == len(metadata)
    for rec in data["records"]:
        assert isinstance(rec.get("embedding"), list)
        assert rec["embedding"]
        assert "payload" in rec
