#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
TEMPLATE="${REPO_ROOT}/docs/test-notes/template-mirror-daily-check.md"
TARGET_DIR="${REPO_ROOT}/docs/test-notes"

DATE_PREFIX=$(date +%Y-%m-%d)
TARGET_FILE="${TARGET_DIR}/${DATE_PREFIX}-mirror-check.md"

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "Template not found: ${TEMPLATE}" >&2
  exit 1
fi

if [[ -f "${TARGET_FILE}" ]]; then
  echo "File already exists: ${TARGET_FILE}" >&2
  exit 1
fi

cp "${TEMPLATE}" "${TARGET_FILE}"

cat <<INFO
Created ${TARGET_FILE}
Please edit the file to record today's mirror verification results.
INFO
