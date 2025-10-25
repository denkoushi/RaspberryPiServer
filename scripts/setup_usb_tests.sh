#!/usr/bin/env bash

set -euo pipefail

BASE_DIR="${1:-$PWD/usb-test-ready}"

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Command not found: $1"
}

require_cmd truncate
require_cmd losetup
require_cmd mkfs.ext4

mkdir -p "${BASE_DIR}" || die "cannot create ${BASE_DIR}"

case "${BASE_DIR}" in
  /*) ;;
  *) die "BASE_DIR must be absolute" ;;
esac

INGEST_IMG="${BASE_DIR}/ingest.img"
DIST_IMG="${BASE_DIR}/dist.img"
BACKUP_IMG="${BASE_DIR}/backup.img"

log() {
  local ts
  ts=$(date --iso-8601=seconds)
  printf '[%s] %s\n' "$ts" "$*"
}

setup_img() {
  local img="$1"
  local size="$2"
  log "Creating ${img} (${size})"
  truncate -s "$size" "$img"
}

attach_loop() {
  local img="$1"
  losetup -fP "$img"
  losetup -a | grep "$img" | cut -d: -f1 | head -n1 || die "failed to attach $img"
}

format_ext4() {
  local loop="$1"
  local label="$2"
  log "Formatting ${loop} with label ${label}"
  mkfs.ext4 -F -L "$label" "$loop"
}

create_role() {
  local loop="$1"
  local role="$2"
  local mp
  mp=$(mktemp -d)
  mount "$loop" "$mp"
  mkdir -p "$mp/.toolmaster"
  echo "$role" >"$mp/.toolmaster/role"
  umount "$mp"
  rmdir "$mp"
}

setup_img "$INGEST_IMG" 1G
setup_img "$DIST_IMG" 1G
setup_img "$BACKUP_IMG" 8G

LOOP1=$(attach_loop "$INGEST_IMG")
LOOP2=$(attach_loop "$DIST_IMG")
LOOP3=$(attach_loop "$BACKUP_IMG")

format_ext4 "$LOOP1" TM-INGEST
format_ext4 "$LOOP2" TM-DIST
format_ext4 "$LOOP3" TM-BACKUP

create_role "$LOOP1" INGEST
create_role "$LOOP2" DIST
create_role "$LOOP3" BACKUP

log "Setup complete"
losetup -a | grep "$BASE_DIR"
