#!/usr/bin/env python3
import argparse
import logging
import sys
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Optional

from huggingface_hub import hf_hub_download


def _hash_file(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_file_info(target: Path, destination: Path, skip_hash: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    stat = target.stat()
    lines = [
        f"path: {target}",
        f"size_bytes: {stat.st_size}",
        f"last_modified: {datetime.fromtimestamp(stat.st_mtime).isoformat()}",
    ]

    if not skip_hash:
        lines.append(f"sha256: {_hash_file(target)}")
    else:
        lines.append("sha256: skipped")

    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a single file from Hugging Face without PowerShell encoding issues.",
    )
    parser.add_argument(
        "--repo-id",
        default="openai/gpt-oss-20b",
        help="Repository id on Hugging Face (default: %(default)s)",
    )
    parser.add_argument(
        "--filename",
        default="original/model.safetensors",
        help="Path to the file inside the repo (default: %(default)s)",
    )
    parser.add_argument(
        "--out-dir",
        default="models/gpt-oss-20b-redownload",
        help="Where to place the downloaded file (default: %(default)s)",
    )
    parser.add_argument(
        "--log-file",
        default="reports/hf_redownload.log",
        help="Log file to write progress/errors (default: %(default)s)",
    )
    parser.add_argument(
        "--file-info",
        default="reports/redownload_file_info.txt",
        help="Where to write the downloaded file details (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Optional Hugging Face token; defaults to env/CLI login if omitted.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force redownload even if the file already exists in cache.",
    )
    parser.add_argument(
        "--skip-hash",
        action="store_true",
        help="Skip computing sha256 (faster for large files).",
    )
    return parser.parse_args()


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def download_file(
    repo_id: str,
    filename: str,
    out_dir: Path,
    token: Optional[str],
    force: bool,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.info("Downloading %s from %s -> %s", filename, repo_id, out_dir)

    downloaded_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        repo_type="model",
        local_dir=out_dir,
        local_dir_use_symlinks=False,
        resume_download=True,
        force_download=force,
        token=token,
    )
    resolved = Path(downloaded_path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Expected downloaded file at {resolved}")

    logging.info("Download complete: %s", resolved)
    return resolved


def main() -> int:
    args = parse_args()

    log_path = Path(args.log_file).resolve()
    setup_logging(log_path)

    try:
        target = download_file(
            repo_id=args.repo_id,
            filename=args.filename,
            out_dir=Path(args.out_dir).resolve(),
            token=args.token,
            force=args.force,
        )
        info_path = Path(args.file_info).resolve()
        _write_file_info(target, info_path, skip_hash=args.skip_hash)
        logging.info("Wrote file info to %s", info_path)
    except Exception:
        logging.exception("Redownload failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
