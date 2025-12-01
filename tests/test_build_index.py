from pathlib import Path

from tools.emb.embeddings_stub import DEFAULT_DIMENSION
from tools.indexer.build_index import build_index


def test_build_index_creates_jsonl_with_schema_and_embeddings(tmp_path: Path):
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    doc = input_dir / "doc.md"
    doc.write_text(" ".join(str(i) for i in range(300)), encoding="utf-8")

    out_path = tmp_path / "indexes" / "index.jsonl"
    log_path = tmp_path / "reports" / "index.log"
    records, written_path, written_log = build_index(
        input_dir=input_dir,
        out_path=out_path,
        chunk_tokens=32,
        overlap_tokens=8,
        use_embeddings=True,
        log_path=log_path,
    )

    assert written_path == out_path
    assert written_log == log_path
    assert out_path.exists()
    assert log_path.exists()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records)
    assert len(lines) > 0

    for rec in records:
        assert set(rec.keys()) >= {"id", "chunk", "meta", "vector"}
        assert isinstance(rec["chunk"], str)
        meta = rec["meta"]
        assert set(meta.keys()) >= {"path", "start", "end", "lang", "sha256"}
        assert meta["path"] == doc.name
        assert isinstance(meta["start"], int)
        assert isinstance(meta["end"], int)
        assert isinstance(meta["lang"], str)
        assert isinstance(meta["sha256"], str) and len(meta["sha256"]) == 64
        assert len(rec["vector"]) == DEFAULT_DIMENSION
