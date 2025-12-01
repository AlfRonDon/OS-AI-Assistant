import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover
    faiss = None

from retrieval.index import build_index
from retrieval.index_persist import persist_index_to_pgvector


def _load_index(index_path: str | None):
    if index_path and faiss is not None:
        path = Path(index_path)
        if path.exists():
            try:
                return faiss.read_index(str(path))
            except Exception:
                pass
    index, docs = build_index()
    metadata = [{"id": str(i), "text": doc} for i, doc in enumerate(docs)]
    return index, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist FAISS index snapshots to pgvector or fallback.")
    parser.add_argument("--pg", dest="pg_conn", help="Postgres connection string", default=None)
    parser.add_argument("--index_path", help="Path to existing FAISS index file", default=None)
    parser.add_argument("--version", help="Snapshot version label", default="dev")
    args = parser.parse_args()

    loaded = _load_index(args.index_path)
    if isinstance(loaded, tuple):
        index, metadata = loaded
    else:
        index, metadata = loaded, []

    persist_index_to_pgvector(index, metadata, args.pg_conn, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
