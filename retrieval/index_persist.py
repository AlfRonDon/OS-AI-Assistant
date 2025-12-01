import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence


def _extract_embeddings(faiss_index: Any) -> List[List[float]]:
    if hasattr(faiss_index, "vectors"):
        return [list(v) for v in getattr(faiss_index, "vectors")]
    if hasattr(faiss_index, "reconstruct_n"):
        try:
            total = getattr(faiss_index, "ntotal", 0)
            if total > 0:
                reconstructed = faiss_index.reconstruct_n(0, total)
                return [list(vec) for vec in reconstructed]
        except Exception:
            pass
    if hasattr(faiss_index, "reconstruct"):
        try:
            total = getattr(faiss_index, "ntotal", 0)
            return [list(faiss_index.reconstruct(i)) for i in range(total)]
        except Exception:
            pass
    return []


def _connect_pg(pg_conn_str: str):
    try:
        import psycopg  # type: ignore

        return psycopg.connect(pg_conn_str)
    except ImportError:
        try:
            import psycopg2  # type: ignore

            return psycopg2.connect(pg_conn_str)
        except ImportError as exc:  # pragma: no cover
            raise ImportError("psycopg or psycopg2 required for Postgres persistence") from exc


def _write_fallback(embeddings: List[List[float]], metadata_list: Sequence[Dict[str, Any]], version: str) -> Path:
    root = Path(__file__).resolve().parents[1]
    fallback_path = root / "replays" / "pgvector_fallback.json"
    fallback_path.parent.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    for idx, embedding in enumerate(embeddings):
        payload = metadata_list[idx] if idx < len(metadata_list) else {}
        record_id = str(payload.get("id", idx))
        records.append(
            {
                "id": record_id,
                "embedding": list(embedding),
                "payload": payload,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "version": version,
            }
        )

    with open(fallback_path, "w", encoding="utf-8") as f:
        json.dump({"records": records, "version": version}, f, indent=2)
    return fallback_path


def persist_index_to_pgvector(
    faiss_index: Any, metadata_list: Sequence[Dict[str, Any]], pg_conn_str: str | None, version: str
) -> Path | None:
    embeddings = _extract_embeddings(faiss_index)
    if not embeddings:
        return _write_fallback(embeddings, metadata_list, version)

    if not pg_conn_str:
        return _write_fallback(embeddings, metadata_list, version)

    try:
        conn = _connect_pg(pg_conn_str)
    except ImportError:
        return _write_fallback(embeddings, metadata_list, version)

    with conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS retrieval;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS retrieval.index_snapshots(
                    id TEXT PRIMARY KEY,
                    embedding REAL[],
                    payload JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    version TEXT
                );
                """
            )
            for idx, embedding in enumerate(embeddings):
                payload = metadata_list[idx] if idx < len(metadata_list) else {}
                record_id = str(payload.get("id", idx))
                cur.execute(
                    """
                    INSERT INTO retrieval.index_snapshots (id, embedding, payload, created_at, version)
                    VALUES (%s, %s, %s, NOW(), %s)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        payload = EXCLUDED.payload,
                        created_at = EXCLUDED.created_at,
                        version = EXCLUDED.version;
                    """,
                    (record_id, embedding, json.dumps(payload), version),
                )
    return None
