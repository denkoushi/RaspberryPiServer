#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${REPO_ROOT}/lib/toolmaster-usb.sh"

USB_LOG_FILE="snapshot.log"
USB_LOG_TAG="tool-snapshot"

SERVER_ROOT="${SERVER_ROOT:-/srv/rpi-server}"
SERVER_MASTER_DIR="${SERVER_MASTER_DIR:-${SERVER_ROOT}/master}"
SERVER_DOC_DIR="${SERVER_DOC_DIR:-${SERVER_ROOT}/docviewer}"

SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-/srv/rpi-server/snapshots}"
RETENTION_DAYS="${SNAPSHOT_RETENTION_DAYS:-7}"
PG_URI="${PG_URI:-}"
PG_OPTIONS=()
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dest PATH] [--pg-uri URI] [--retention-days N] [--dry-run]

Options:
  --dest PATH          Snapshot root directory (default: ${SNAPSHOT_ROOT})
  --pg-uri URI         libpq URI or connection string for pg_dump
  --pg-option OPT      Additional pg_dump option (repeatable)
  --retention-days N   Number of days to keep snapshots (default: ${RETENTION_DAYS})
  --dry-run            Show planned operations without writing
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)
      SNAPSHOT_ROOT="$2"
      shift 2
      ;;
    --pg-uri)
      PG_URI="$2"
      shift 2
      ;;
    --pg-option)
      PG_OPTIONS+=("$2")
      shift 2
      ;;
    --retention-days)
      RETENTION_DAYS="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 64
      ;;
  esac
done

timestamp="$(date +%Y-%m-%d_%H%M%S)"
snapshot_dir="${SNAPSHOT_ROOT}/${timestamp}"

if [[ ${DRY_RUN} -eq 1 ]]; then
  usb_log "notice" "would create snapshot at ${snapshot_dir}"
else
  mkdir -p "${snapshot_dir}"
fi

ensure_copy() {
  local src="$1"
  local dest="$2"
  if [[ ! -d "${src}" ]]; then
    usb_log "warning" "source directory missing: ${src}"
    return 0
  fi
  if [[ ${DRY_RUN} -eq 1 ]]; then
    usb_log "notice" "would rsync ${src} -> ${dest}"
    return 0
  fi
  mkdir -p "${dest}"
  rsync -a --delete --human-readable "${src}/" "${dest}/"
}

ensure_copy "${SERVER_MASTER_DIR}" "${snapshot_dir}/master"
ensure_copy "${SERVER_DOC_DIR}" "${snapshot_dir}/docviewer"

if [[ ${DRY_RUN} -eq 0 ]]; then
  mkdir -p "${snapshot_dir}/db"
  dump_args=("${PG_OPTIONS[@]}")
  if [[ -n "${PG_URI}" ]]; then
    dump_args+=("--dbname=${PG_URI}")
  fi
  dump_file="${snapshot_dir}/db/pg_dump.sql"
  usb_log "info" "running pg_dump into ${dump_file}"
  if ! pg_dump "${dump_args[@]}" > "${dump_file}"; then
    usb_log "err" "pg_dump failed"
    exit 2
  fi
else
  usb_log "notice" "would run pg_dump into ${snapshot_dir}/db/pg_dump.sql"
fi

if [[ ${DRY_RUN} -eq 0 ]]; then
  find "${SNAPSHOT_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -print0 | while IFS= read -r -d '' dir; do
    usb_log "info" "removing old snapshot ${dir}"
    rm -rf "${dir}"
  done
else
  usb_log "notice" "would prune snapshots older than ${RETENTION_DAYS} days"
fi

usb_log "info" "snapshot completed (dry_run=${DRY_RUN}) dest=${snapshot_dir}"
