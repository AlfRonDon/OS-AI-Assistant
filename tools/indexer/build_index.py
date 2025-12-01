"""
Indexer for the OS AI Assistant.

Reads Markdown/JSON/text/PDF files from an input directory, chunks them into
~1024-token windows with overlap, and emits deterministic JSONL ready for
retrieval or embedding pipelines.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.emb.embeddings_stub import DEFAULT_DIMENSION, embed_texts as _stub_embed

ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".pdf"}
TOKEN_TO_CHAR_RATIO = 6
DEFAULT_CHUNK_TOKENS = 1024
DEFAULT_OVERLAP_TOKENS = 128


def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"indexer-{log_path}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def _compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compute_chunk_id(rel_path: str, start: int, length: int) -> str:
    payload = f"{rel_path}:{start}:{length}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_pdf(path: Path, logger: logging.Logger) -> str:
    try:
        import PyPDF2  # type: ignore
    except Exception:
        logger.info("SKIP_PDF path=%s reason=no_pdf_parser", path)
        return ""

    try:
        reader = PyPDF2.PdfReader(str(path))
        pages: List[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(pages).strip()
    except Exception as exc:
        logger.warning("SKIP_PDF path=%s reason=%s", path, exc)
        return ""


def _load_text(path: Path, logger: logging.Logger) -> str:
    suffix = path.suffix.lower()
    text = ""
    if suffix in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
    elif suffix == ".json":
        raw = path.read_text(encoding="utf-8", errors="ignore") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            text = raw
        else:
            if isinstance(data, dict):
                if "text" in data and isinstance(data["text"], str):
                    text = data["text"]
                else:
                    text = json.dumps(data, ensure_ascii=True)
            elif isinstance(data, list):
                text = "\n".join(json.dumps(item, ensure_ascii=True) for item in data)
            else:
                text = str(data)
    elif suffix == ".pdf":
        text = _load_pdf(path, logger)

    return text.lstrip("\ufeff")


def _approx_chars(tokens: int) -> int:
    return max(1, tokens * TOKEN_TO_CHAR_RATIO)


def _chunk_text(text: str, chunk_tokens: int, overlap_tokens: int) -> List[Tuple[int, int, str]]:
    chunk_chars = _approx_chars(chunk_tokens)
    overlap_chars = _approx_chars(overlap_tokens)
    if overlap_chars >= chunk_chars:
        raise ValueError("overlap must be smaller than chunk size to avoid infinite loop")

    n = len(text)
    if n == 0:
        return []

    chunks: List[Tuple[int, int, str]] = []
    start = 0
    while start < n:
        end = min(start + chunk_chars, n)
        chunk = text[start:end]
        chunks.append((start, end, chunk))
        if end >= n:
            break
        start = max(0, end - overlap_chars)
    return chunks


def _iter_input_files(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES:
            yield path


def _detect_language(text: str) -> str:
    # Minimal heuristic: assume English for ASCII-dominant text.
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / float(len(text) or 1)
    return "en" if ascii_ratio >= 0.5 else "unknown"


def _validate_records(records: Sequence[dict], require_embeddings: bool) -> None:
    required_meta_keys = {"path", "start", "end", "lang", "sha256"}
    for idx, rec in enumerate(records):
        for key in ("id", "chunk", "meta"):
            if key not in rec:
                raise ValueError(f"record {idx} missing key {key}")
        meta = rec["meta"]
        missing_meta = required_meta_keys - set(meta.keys())
        if missing_meta:
            raise ValueError(f"record {idx} missing meta fields {sorted(missing_meta)}")
        if not isinstance(rec["chunk"], str):
            raise ValueError(f"record {idx} chunk must be string")
        if not isinstance(meta.get("path"), str):
            raise ValueError(f"record {idx} meta.path must be string")
        if not isinstance(meta.get("start"), int) or not isinstance(meta.get("end"), int):
            raise ValueError(f"record {idx} meta.start/meta.end must be ints")
        if meta["end"] < meta["start"]:
            raise ValueError(f"record {idx} has invalid offsets")
        if (meta["end"] - meta["start"]) != len(rec["chunk"]):
            raise ValueError(f"record {idx} offsets do not match chunk length")
        if not isinstance(meta.get("lang"), str):
            raise ValueError(f"record {idx} meta.lang must be string")
        sha = meta.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError(f"record {idx} meta.sha256 must be hex digest")
        if require_embeddings:
            vec = rec.get("vector")
            if not isinstance(vec, Sequence):
                raise ValueError(f"record {idx} missing vector")
            if len(vec) != DEFAULT_DIMENSION:
                raise ValueError(f"record {idx} vector length {len(vec)} != {DEFAULT_DIMENSION}")


def _write_jsonl(records: Sequence[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")


def build_index(
    input_dir: Path,
    out_path: Path | None = None,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    use_embeddings: bool = False,
    log_path: Path | None = None,
) -> tuple[List[dict], Path, Path]:
    resolved_out = out_path or Path("indexes") / f"index-{_dt.date.today():%Y%m%d}.jsonl"
    resolved_log = log_path or Path("reports") / f"index-build-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    logger = _setup_logger(resolved_log)

    logger.info(
        "INDEX_START input=%s out=%s embeddings=%s chunk_tokens=%s overlap_tokens=%s",
        input_dir,
        resolved_out,
        use_embeddings,
        chunk_tokens,
        overlap_tokens,
    )

    if not input_dir.exists():
        logger.error("input directory not found: %s", input_dir)
        raise FileNotFoundError(f"input directory not found: {input_dir}")

    files = list(_iter_input_files(input_dir))
    if not files:
        logger.error("no input files found under %s", input_dir)
        raise ValueError(f"no input files found under {input_dir}")

    records: List[dict] = []
    for source in files:
        rel_path = source.relative_to(input_dir).as_posix()
        file_hash = _compute_file_sha256(source)
        text = _load_text(source, logger)
        if not text:
            logger.warning("SKIP_EMPTY path=%s", source)
            continue

        before_count = len(records)
        for start, end, chunk in _chunk_text(text, chunk_tokens, overlap_tokens):
            if not chunk:
                continue
            rec = {
                "id": _compute_chunk_id(rel_path, start, end - start),
                "chunk": chunk,
                "meta": {
                    "path": rel_path,
                    "start": start,
                    "end": end,
                    "lang": _detect_language(chunk),
                    "sha256": file_hash,
                },
            }
            records.append(rec)
        logger.info("LOADED path=%s chunks=%s", rel_path, len(records) - before_count)

    if not records:
        logger.error("no chunks produced from input files")
        raise ValueError("no chunks produced from input files")

    if use_embeddings:
        vectors = _stub_embed([r["chunk"] for r in records], dim=DEFAULT_DIMENSION)
        for rec, vec in zip(records, vectors):
            rec["vector"] = vec
        logger.info("EMBEDDINGS vector_len=%s", DEFAULT_DIMENSION)

    _validate_records(records, require_embeddings=use_embeddings)
    _write_jsonl(records, resolved_out)

    logger.info(
        "INDEX_COMPLETE out=%s rows=%s embeddings=%s",
        resolved_out,
        len(records),
        use_embeddings,
    )
    return records, resolved_out, resolved_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a JSONL retrieval index for OS AI Assistant.")
    parser.add_argument("--input", type=Path, default=Path("data") / "raw", help="Directory with input documents.")
    parser.add_argument("--out", type=Path, default=None, help="Output JSONL path (default: indexes/index-YYYYMMDD.jsonl).")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_TOKENS, help="Chunk size in approx tokens.")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_TOKENS, help="Overlap in approx tokens.")
    parser.add_argument("--embeddings", action="store_true", help="Attach deterministic stub embeddings to each chunk.")
    parser.add_argument("--log-path", type=Path, default=None, help="Optional path for the build log.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = uuid.uuid4()
    target_out = args.out or Path("indexes") / f"index-{_dt.date.today():%Y%m%d}.jsonl"
    target_log = args.log_path or Path("reports") / f"index-build-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    rc = 0
    try:
        records, resolved_out, resolved_log = build_index(
            input_dir=args.input,
            out_path=target_out,
            chunk_tokens=args.chunk_size,
            overlap_tokens=args.overlap,
            use_embeddings=args.embeddings,
            log_path=target_log,
        )
        print(
            f"INDEX_WRITTEN id={run_id} path={resolved_out.as_posix()} rows={len(records)} log={resolved_log.as_posix()}"
        )
    except Exception as exc:  # pragma: no cover - runtime failure path
        rc = 1
        print(f"INDEX_ERROR id={run_id} err={exc}")
        resolved_out = target_out
    print(f"MASTER_DONE id={run_id} rc={rc} out={resolved_out.as_posix()}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
