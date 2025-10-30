#!/usr/bin/env bash
# Summarise and sanity-check /srv/rpi-server/logs contents for the weekly review.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

LOG_ROOT="${LOG_ROOT:-/srv/rpi-server/logs}"
DAYS="${DAYS:-7}"
TAIL_LINES="${TAIL_LINES:-50}"
FILTER_REGEX="${FILTER_REGEX:-ERROR|WARN|CRITICAL|Traceback}"
RECENT_LIMIT="${RECENT_LIMIT:-20}"
LARGEST_LIMIT="${LARGEST_LIMIT:-20}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d "${LOG_ROOT}" ]]; then
  echo "ERROR: log root '${LOG_ROOT}' not found." >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "ERROR: python3 is required for metadata summary." >&2
  exit 1
fi

echo "[INFO] Log root: ${LOG_ROOT}"
echo "[INFO] Retention window: last ${DAYS} day(s)"

if du_output=$(du -sh "${LOG_ROOT}" 2>/dev/null); then
  size=$(printf '%s\n' "${du_output}" | awk '{print $1}')
  echo "[INFO] Total size: ${size}"
else
  echo "[WARN] Unable to read directory size for ${LOG_ROOT}"
fi

LOG_ROOT="${LOG_ROOT}" \
  DAYS="${DAYS}" \
  RECENT_LIMIT="${RECENT_LIMIT}" \
  LARGEST_LIMIT="${LARGEST_LIMIT}" \
  "${PYTHON_BIN}" <<'PY'
import os
import sys
import time
from datetime import datetime

log_root = os.environ["LOG_ROOT"]
days = int(os.environ.get("DAYS", "7"))
recent_limit = max(1, int(os.environ.get("RECENT_LIMIT", "20")))
largest_limit = max(1, int(os.environ.get("LARGEST_LIMIT", "20")))

threshold = time.time() - days * 86400
recent_entries = []
all_entries = []

def human(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"

for root, _dirs, files in os.walk(log_root):
    for name in files:
        path = os.path.join(root, name)
        try:
            stat = os.stat(path, follow_symlinks=False)
        except (FileNotFoundError, PermissionError):
            continue
        entry = (stat.st_mtime, stat.st_size, path)
        all_entries.append(entry)
        if stat.st_mtime >= threshold:
            recent_entries.append(entry)

recent_entries.sort(key=lambda item: item[0], reverse=True)
all_entries.sort(key=lambda item: item[1], reverse=True)

if recent_entries:
    print("[INFO] Files updated within window (newest first):")
    for mtime, size, path in recent_entries[:recent_limit]:
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  - {path} (updated {ts}, size {human(size)})")
else:
    print("[INFO] No files updated in the last {} day(s).".format(days))

if all_entries:
    print("[INFO] Largest files:")
    for mtime, size, path in all_entries[:largest_limit]:
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  - {path} (size {human(size)}, updated {ts})")
else:
    print("[INFO] No files found under {}".format(log_root))
PY

matches=""
while IFS= read -r -d '' logfile; do
  # tail prints file headers automatically when multiple inputs are provided
  section=$(tail -n "${TAIL_LINES}" "${logfile}" 2>/dev/null | grep -E "${FILTER_REGEX}" || true)
  if [[ -n "${section}" ]]; then
    matches+=$'\n'"### ${logfile}"$'\n'"${section}"
  fi
done < <(find "${LOG_ROOT}" -type f -name "*.log" -mtime -"${DAYS}" -print0 2>/dev/null)

if [[ -z "${matches}" ]]; then
  echo "[OK] No WARN/ERROR patterns detected in *.log files (last ${TAIL_LINES} lines, ${DAYS} day window)."
else
  echo "[WARN] Potential issues found:"
  printf '%s\n' "${matches#"$'\n'"}"
  exit 2
fi
