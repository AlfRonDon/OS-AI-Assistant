import json
from pathlib import Path

from tools.emb.embeddings_stub import DEFAULT_DIMENSION
from tools.train import generate_dataset


def test_generated_dataset_has_required_fields(tmp_path: Path) -> None:
    out_path = tmp_path / "dataset.jsonl"
    log_path = tmp_path / "dataset.log"
    dataset_path, rows, skip_log, stats = generate_dataset.build_dataset(out_path=out_path, log_path=log_path, min_examples=1)

    assert dataset_path.exists()
    assert rows >= 1
    assert skip_log.exists()
    assert stats["rows"] == rows

    required = {"id", "instruction", "plan", "executor", "response", "metadata"}
    with dataset_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            assert required.issubset(record.keys())
            assert isinstance(record["metadata"], dict)
            if "instruction_embedding" in record:
                assert len(record["instruction_embedding"]) == DEFAULT_DIMENSION
