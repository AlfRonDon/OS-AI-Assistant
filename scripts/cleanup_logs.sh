#!/usr/bin/env bash
set -euo pipefail

LOGS_ROOT="${1:-logs}"
ARCHIVE_AFTER_DAYS="${ARCHIVE_AFTER_DAYS:-7}"
DELETE_AFTER_DAYS="${DELETE_AFTER_DAYS:-90}"

if [[ ! -d "$LOGS_ROOT" ]]; then
  echo "Logs directory '$LOGS_ROOT' not found; nothing to do."
  exit 0
fi

ARCHIVE_DIR="$LOGS_ROOT/archive"
mkdir -p "$ARCHIVE_DIR"

archive_name="$(date +%Y%m%d)_logs.tar.gz"
archive_path="$ARCHIVE_DIR/$archive_name"

archive_mtime=$((ARCHIVE_AFTER_DAYS - 1))
delete_mtime=$((DELETE_AFTER_DAYS - 1))

mapfile -d '' files_to_archive < <(find "$LOGS_ROOT" -type f ! -path "$ARCHIVE_DIR/*" -mtime "+${archive_mtime}" -print0)

if (( ${#files_to_archive[@]} > 0 )); then
  rel_paths=()
  for file in "${files_to_archive[@]}"; do
    rel_paths+=( "${file#$LOGS_ROOT/}" )
  done
  tar -czf "$archive_path" -C "$LOGS_ROOT" -- "${rel_paths[@]}"
  echo "Archived ${#files_to_archive[@]} log file(s) to $archive_path"
else
  echo "No logs older than ${ARCHIVE_AFTER_DAYS} day(s) to archive."
fi

mapfile -d '' old_logs < <(find "$LOGS_ROOT" -type f ! -path "$ARCHIVE_DIR/*" -mtime "+${delete_mtime}" -print0)

if (( ${#old_logs[@]} > 0 )); then
  for file in "${old_logs[@]}"; do
    echo "Deleting $file"
    rm -f -- "$file"
  done
  echo "Deleted ${#old_logs[@]} log file(s) older than ${DELETE_AFTER_DAYS} day(s)."
else
  echo "No logs older than ${DELETE_AFTER_DAYS} day(s) to delete."
fi
