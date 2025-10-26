#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
DEFAULT_TEMPLATE="${REPO_ROOT}/docs/test-notes/template-mirror-daily-check.md"
TARGET_DIR="${REPO_ROOT}/docs/test-notes"

usage() {
  cat <<'USAGE'
Usage: create_mirror_check_note.sh [options]
  --date YYYY-MM-DD   Generate note for the specified date (default: today)
  --template PATH     Use custom template path
  --force             Overwrite if the target file already exists
  --help              Show this help
USAGE
}

TEMPLATE="${DEFAULT_TEMPLATE}"
DATE_PREFIX=$(date +%Y-%m-%d)
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      [[ $# -lt 2 ]] && usage && exit 1
      DATE_PREFIX="$2"
      shift 2
      ;;
    --template)
      [[ $# -lt 2 ]] && usage && exit 1
      TEMPLATE="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

TARGET_FILE="${TARGET_DIR}/${DATE_PREFIX}-mirror-check.md"

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "Template not found: ${TEMPLATE}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

if [[ -f "${TARGET_FILE}" && "${FORCE}" != true ]]; then
  echo "File already exists: ${TARGET_FILE}" >&2
  echo "(use --force to overwrite)" >&2
  exit 1
fi

cp "${TEMPLATE}" "${TARGET_FILE}"

cat <<INFO
Created ${TARGET_FILE}
Please edit the file to record mirror verification results.
INFO
