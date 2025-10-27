#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PREFIX="${PREFIX:-/usr/local/toolmaster}"
BIN_DIR="${PREFIX}/bin"
LIB_DIR="${PREFIX}/lib"
SCRIPT_SUPPORT_DIR="${PREFIX}/scripts"
SYSTEMD_DIR="/etc/systemd/system"
UDEV_RULES_DIR="/etc/udev/rules.d"
DEFAULT_ENV="/etc/default/raspi-server"
MIRRORCTL_DIR="/etc/mirrorctl"
MIRRORCTL_CONFIG="${MIRRORCTL_DIR}/config.json"

MODE="install"
ENABLE_TIMERS=1

log() {
  echo "[install-server-stack] $*" >&2
}

usage() {
  cat <<'USAGE'
Usage: install_server_stack.sh [OPTIONS]

Options:
  --install           Install or update the server stack (default)
  --remove            Remove installed files and disable timers
  --skip-enable       Do not enable/start tool-snapshot.timer or mirror-compare.timer
  -h, --help          Show this help message

Environment overrides:
  PREFIX=/custom/path  Base directory for installed scripts (default: /usr/local/toolmaster)
USAGE
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    log "This script must be run as root."
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --install)
        MODE="install"
        shift
        ;;
      --remove)
        MODE="remove"
        shift
        ;;
      --skip-enable)
        ENABLE_TIMERS=0
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        log "Unknown option: $1"
        usage
        exit 64
        ;;
    esac
  done
}

install_scripts() {
  log "Installing scripts into ${PREFIX}"
  install -d "${BIN_DIR}" "${LIB_DIR}" "${SCRIPT_SUPPORT_DIR}"

  local tool_scripts=(
    "tool-ingest-sync.sh"
    "tool-dist-export.sh"
    "tool-dist-sync.sh"
    "tool-backup-export.sh"
    "tool-snapshot.sh"
  )

  for script in "${tool_scripts[@]}"; do
    install -m 755 "${REPO_ROOT}/scripts/${script}" "${BIN_DIR}/${script}"
  done

  install -m 755 "${REPO_ROOT}/scripts/update_plan_cache.py" "${SCRIPT_SUPPORT_DIR}/update_plan_cache.py"
  install -m 644 "${REPO_ROOT}/lib/toolmaster-usb.sh" "${LIB_DIR}/toolmaster-usb.sh"
  install -m 644 "${REPO_ROOT}/lib/toolmaster-usb.sh" "/usr/local/lib/toolmaster-usb.sh"

  for link_script in "${tool_scripts[@]}"; do
    ln -sf "${BIN_DIR}/${link_script}" "/usr/local/bin/${link_script}"
  done

  install -m 755 "${REPO_ROOT}/scripts/mirrorctl.py" "/usr/local/bin/mirrorctl"
  install -m 755 "${REPO_ROOT}/scripts/mirror_compare.py" "/usr/local/bin/mirror_compare.py"
}

install_systemd_units() {
  log "Installing systemd unit files"
  install -m 644 "${REPO_ROOT}/systemd/raspi-server.service" "${SYSTEMD_DIR}/raspi-server.service"
  install -m 644 "${REPO_ROOT}/systemd/tool-snapshot.service" "${SYSTEMD_DIR}/tool-snapshot.service"
  install -m 644 "${REPO_ROOT}/systemd/tool-snapshot.timer" "${SYSTEMD_DIR}/tool-snapshot.timer"
  install -m 644 "${REPO_ROOT}/systemd/usb-ingest@.service" "${SYSTEMD_DIR}/usb-ingest@.service"
  install -m 644 "${REPO_ROOT}/systemd/usb-dist-export@.service" "${SYSTEMD_DIR}/usb-dist-export@.service"
  install -m 644 "${REPO_ROOT}/systemd/usb-backup@.service" "${SYSTEMD_DIR}/usb-backup@.service"
  install -m 644 "${REPO_ROOT}/systemd/mirror-compare.service" "${SYSTEMD_DIR}/mirror-compare.service"
  install -m 644 "${REPO_ROOT}/systemd/mirror-compare.timer" "${SYSTEMD_DIR}/mirror-compare.timer"

  log "Installing udev rules"
  install -m 644 "${REPO_ROOT}/udev/90-toolmaster.rules" "${UDEV_RULES_DIR}/90-toolmaster.rules"

  if [[ ! -f "${DEFAULT_ENV}" ]]; then
    install -m 640 "${REPO_ROOT}/config/raspi-server.env.sample" "${DEFAULT_ENV}"
    log "Placed ${DEFAULT_ENV} (edit to match production values)"
  else
    log "Skipping ${DEFAULT_ENV} (already exists)"
  fi

  install -d "${MIRRORCTL_DIR}"
  if [[ ! -f "${MIRRORCTL_CONFIG}" ]]; then
    install -m 640 "${REPO_ROOT}/config/mirrorctl-config.sample.json" "${MIRRORCTL_CONFIG}"
    log "Placed ${MIRRORCTL_CONFIG} (update SSH host/credentials before use)"
  else
    log "Skipping ${MIRRORCTL_CONFIG} (already exists)"
  fi
}

ensure_directories() {
  local runtime_dirs=(
    "/srv/rpi-server/master"
    "/srv/rpi-server/docviewer"
    "/srv/rpi-server/data/plan"
    "/srv/rpi-server/logs"
    "/srv/rpi-server/snapshots"
  )
  for dir in "${runtime_dirs[@]}"; do
    install -d -m 775 "${dir}"
  done
}

enable_services() {
  log "Reloading systemd units"
  systemctl daemon-reload
  udevadm control --reload || true

  if [[ ${ENABLE_TIMERS} -eq 1 ]]; then
    log "Enabling timers"
    systemctl enable --now tool-snapshot.timer
    systemctl enable --now mirror-compare.timer
  else
    log "Skipping timer enable as requested"
  fi
}

install_stack() {
  install_scripts
  install_systemd_units
  ensure_directories
  enable_services
  log "Installation completed"
}

remove_stack() {
  log "Disabling timers (if active)"
  systemctl disable --now tool-snapshot.timer 2>/dev/null || true
  systemctl disable --now mirror-compare.timer 2>/dev/null || true

  log "Removing systemd unit files"
  rm -f \
    "${SYSTEMD_DIR}/raspi-server.service" \
    "${SYSTEMD_DIR}/tool-snapshot.service" \
    "${SYSTEMD_DIR}/tool-snapshot.timer" \
    "${SYSTEMD_DIR}/usb-ingest@.service" \
    "${SYSTEMD_DIR}/usb-dist-export@.service" \
    "${SYSTEMD_DIR}/usb-backup@.service" \
    "${SYSTEMD_DIR}/mirror-compare.service" \
    "${SYSTEMD_DIR}/mirror-compare.timer"

  rm -f "${UDEV_RULES_DIR}/90-toolmaster.rules"

  log "Removing installed scripts"
  local tool_scripts=(
    "tool-ingest-sync.sh"
    "tool-dist-export.sh"
    "tool-dist-sync.sh"
    "tool-backup-export.sh"
    "tool-snapshot.sh"
  )
  for script in "${tool_scripts[@]}"; do
    rm -f "/usr/local/bin/${script}"
    rm -f "${BIN_DIR}/${script}"
  done

  rm -f "/usr/local/bin/mirrorctl" "/usr/local/bin/mirror_compare.py"
  rm -f "${LIB_DIR}/toolmaster-usb.sh" "/usr/local/lib/toolmaster-usb.sh"
  rm -f "${SCRIPT_SUPPORT_DIR}/update_plan_cache.py"

  if [[ -d "${BIN_DIR}" ]]; then
    rmdir --ignore-fail-on-non-empty "${BIN_DIR}" 2>/dev/null || true
  fi
  if [[ -d "${LIB_DIR}" ]]; then
    rmdir --ignore-fail-on-non-empty "${LIB_DIR}" 2>/dev/null || true
  fi
  if [[ -d "${SCRIPT_SUPPORT_DIR}" ]]; then
    rmdir --ignore-fail-on-non-empty "${SCRIPT_SUPPORT_DIR}" 2>/dev/null || true
  fi
  if [[ -d "${PREFIX}" ]]; then
    rmdir --ignore-fail-on-non-empty "${PREFIX}" 2>/dev/null || true
  fi

  systemctl daemon-reload
  udevadm control --reload || true
  log "Removal completed"
}

main() {
  parse_args "$@"
  require_root

  case "${MODE}" in
    install)
      install_stack
      ;;
    remove)
      remove_stack
      ;;
    *)
      log "Unknown mode: ${MODE}"
      exit 1
      ;;
  esac
}

main "$@"
