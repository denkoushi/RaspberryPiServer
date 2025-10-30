#!/usr/bin/env bash
# Check RaspberryPiServer application logs for WARN/ERROR messages.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

TAIL_LINES=${TAIL_LINES:-200}
FILTER_REGEX=${FILTER_REGEX:-"WARN|ERROR"}
IGNORE_REGEX=${IGNORE_REGEX:-"attribute `version` is obsolete"}

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found." >&2
  exit 1
fi

log_output=$(sudo docker compose logs app --tail "${TAIL_LINES}" 2>&1)

filtered=$(printf '%s\n' "${log_output}" | grep -E "${FILTER_REGEX}" || true)
if [[ -n "${IGNORE_REGEX}" ]]; then
  filtered=$(printf '%s\n' "${filtered}" | grep -Ev "${IGNORE_REGEX}" || true)
fi

if [[ -z "${filtered}" ]]; then
  echo "[OK] No WARN/ERROR entries found in the last ${TAIL_LINES} lines (excluding ignored patterns)."
else
  echo "[WARN] Potential issues detected:"
  printf '%s\n' "${filtered}"
  exit 2
fi
