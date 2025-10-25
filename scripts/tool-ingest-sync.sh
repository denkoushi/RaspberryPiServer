#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${REPO_ROOT}/lib/toolmaster-usb.sh"

USB_LOG_FILE="usb_ingest.log"
USB_LOG_TAG="tool-ingest-sync"

SERVER_ROOT="${SERVER_ROOT:-/srv/rpi-server}"
SERVER_MASTER_DIR="${SERVER_MASTER_DIR:-${SERVER_ROOT}/master}"
SERVER_DOC_DIR="${SERVER_DOC_DIR:-${SERVER_ROOT}/docviewer}"

DEVICE=""
DRY_RUN=0
FORCE=0
DRY_RUN_CREATED_DIRS=()

usage() {
  cat <<EOF
Usage: $(basename "$0") --device /dev/sdX1 [--dry-run] [--force]

Options:
  --device PATH   Block device to mount (required)
  --dry-run       Show planned operations without modifying data
  --force         Apply USB contents even if server data appears newer
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force)
      FORCE=1
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

if [[ -z "${DEVICE}" ]]; then
  echo "Error: --device is required" >&2
  usage
  exit 64
fi

rsync_flags=(-a --delete --human-readable)
if [[ ${DRY_RUN} -eq 1 ]]; then
  rsync_flags+=(--dry-run --itemize-changes)
fi

ensure_dir() {
  local path="$1"
  if [[ ! -d "${path}" ]]; then
    if [[ ${DRY_RUN} -eq 1 ]]; then
      mkdir -p "${path}"
      DRY_RUN_CREATED_DIRS+=("${path}")
      usb_log "notice" "created temporary directory for dry-run ${path}"
    else
      mkdir -p "${path}"
    fi
  fi
}

extract_meta_ts() {
  local file="$1"
  if [[ ! -f "${file}" ]]; then
    echo 0
    return 0
  fi
  if command -v jq >/dev/null 2>&1; then
    jq -r '.updated_at // 0' "${file}" 2>/dev/null || stat -c %Y "${file}"
  else
    python3 - "$file" <<'PY'
import json,sys,os
path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    value = data.get("updated_at", 0)
    print(int(value))
except Exception:
    print(int(os.stat(path).st_mtime))
PY
  fi
}

write_meta() {
  local file="$1"
  local ts
  ts="$(date +%s)"
  if [[ ${DRY_RUN} -eq 1 ]]; then
    usb_log "notice" "would update meta ${file} -> ${ts}"
    return 0
  fi
  mkdir -p "$(dirname "${file}")"
  printf '{"updated_at": %s}\n' "${ts}" > "${file}"
}

USB_MOUNT=""
cleanup() {
  if [[ -n "${USB_MOUNT}" ]]; then
    usb_unmount "${USB_MOUNT}" || true
  fi
  if [[ ${DRY_RUN} -eq 1 && ${#DRY_RUN_CREATED_DIRS[@]} -gt 0 ]]; then
    for dir in "${DRY_RUN_CREATED_DIRS[@]}"; do
      rmdir "${dir}" 2>/dev/null || true
    done
  fi
}
trap cleanup EXIT

USB_MOUNT="$(usb_mount_device "${DEVICE}")" || exit 1

if ! usb_validate_role "${USB_MOUNT}" "INGEST" "TOOLMASTER-INGEST"; then
  usb_log "err" "validation failed for ${DEVICE}"
  exit 2
fi

ensure_dir "${SERVER_MASTER_DIR}"
ensure_dir "${SERVER_DOC_DIR}"

USB_MASTER_META="${USB_MOUNT}/master/meta.json"
USB_DOC_META="${USB_MOUNT}/docviewer/meta.json"
SERVER_MASTER_META="${SERVER_MASTER_DIR}/meta.json"
SERVER_DOC_META="${SERVER_DOC_DIR}/meta.json"

usb_ts_master=$(extract_meta_ts "${USB_MASTER_META}")
server_ts_master=$(extract_meta_ts "${SERVER_MASTER_META}")
usb_ts_doc=$(extract_meta_ts "${USB_DOC_META}")
server_ts_doc=$(extract_meta_ts "${SERVER_DOC_META}")

apply_from_usb=0
if [[ ${FORCE} -eq 1 ]]; then
  apply_from_usb=1
else
  if (( usb_ts_master > server_ts_master )) || (( usb_ts_doc > server_ts_doc )); then
    apply_from_usb=1
  fi
fi

copy_from_usb() {
  local src="$1"
  local dest="$2"
  ensure_dir "${dest}"
  rsync "${rsync_flags[@]}" "${src}/" "${dest}/"
}

copy_to_usb() {
  local src="$1"
  local dest="$2"
  ensure_dir "${dest}"
  rsync "${rsync_flags[@]}" "${src}/" "${dest}/"
}

if [[ ${apply_from_usb} -eq 1 ]]; then
  usb_log "info" "applying USB contents to server (device=${DEVICE})"
  copy_from_usb "${USB_MOUNT}/master" "${SERVER_MASTER_DIR}"
  copy_from_usb "${USB_MOUNT}/docviewer" "${SERVER_DOC_DIR}"
else
  usb_log "notice" "server data newer; refreshing USB contents"
  copy_to_usb "${SERVER_MASTER_DIR}" "${USB_MOUNT}/master"
  copy_to_usb "${SERVER_DOC_DIR}" "${USB_MOUNT}/docviewer"
fi

if [[ ${apply_from_usb} -eq 1 ]]; then
  write_meta "${SERVER_MASTER_META}"
  write_meta "${SERVER_DOC_META}"
fi
write_meta "${USB_MASTER_META}"
write_meta "${USB_DOC_META}"

usb_log "info" "ingest completed (dry_run=${DRY_RUN} force=${FORCE})"
