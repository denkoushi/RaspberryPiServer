#!/usr/bin/env python3

"""mirrorctl: RaspberryPiServer mirror operations helper CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CONFIG_PATH = Path("/etc/mirrorctl/config.json")
CONFIG_ENV_VAR = "MIRRORCTL_CONFIG"


class MirrorCtlError(Exception):
    """Custom error for mirrorctl failures."""


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    candidate = (
        Path(os.environ[CONFIG_ENV_VAR])
        if CONFIG_ENV_VAR in os.environ
        else (path or DEFAULT_CONFIG_PATH)
    )
    if not candidate.exists():
        raise MirrorCtlError(f"設定ファイルが見つかりません: {candidate}")
    try:
        with candidate.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise MirrorCtlError(f"設定ファイルの JSON 解析に失敗しました: {candidate}") from exc
    return data


def run_systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def get_unit_state(unit: str) -> Dict[str, str]:
    try:
        active = run_systemctl("is-active", unit)
        enabled = run_systemctl("is-enabled", unit)
    except FileNotFoundError:
        return {"active": "unsupported", "enabled": "unsupported"}
    return {
        "active": active.stdout.strip() if active.returncode == 0 else active.stderr.strip(),
        "enabled": enabled.stdout.strip() if enabled.returncode == 0 else enabled.stderr.strip(),
    }


def read_last_line(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        line = deque(fh, maxlen=1)
    return line[0].rstrip("\n") if line else None


def read_counter(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    timer_name = config.get("mirror_timer", "mirror-compare.timer")
    service_name = config.get("mirror_service", "mirror-compare.service")
    status_dir = Path(config.get("status_dir", "/var/lib/mirror"))
    log_dir = Path(config.get("log_dir", "/srv/rpi-server/logs"))
    ok_counter_path = Path(config.get("ok_counter_file", status_dir / "ok_counter"))

    timer_state = get_unit_state(timer_name)
    service_state = get_unit_state(service_name)

    ok_counter = read_counter(ok_counter_path)
    last_status = read_last_line(log_dir / "mirror_status.log")
    last_diff = read_last_line(log_dir / "mirror_diff.log")

    print(f"Config Path    : {args.config or os.environ.get(CONFIG_ENV_VAR, DEFAULT_CONFIG_PATH)}")
    print(f"Pi Zero Host   : {config.get('pi_zero_host', 'N/A')}")
    print(f"Timer ({timer_name})   : active={timer_state['active']} enabled={timer_state['enabled']}")
    print(f"Service ({service_name}): active={service_state['active']} enabled={service_state['enabled']}")
    print(f"OK Counter     : {ok_counter if ok_counter is not None else 'N/A'}")
    print(f"Last Status    : {last_status or 'N/A'}")
    print(f"Last Diff      : {last_diff or 'N/A'}")
    return 0


def not_implemented(subcommand: str) -> int:
    print(
        f"{subcommand} は未実装です。docs/mirrorctl-spec.md を参照し、"
        "実装方針に沿って拡張してください。",
        file=sys.stderr,
    )
    return 64


def cmd_enable(args: argparse.Namespace) -> int:
    return not_implemented("enable")


def cmd_disable(args: argparse.Namespace) -> int:
    return not_implemented("disable")


def cmd_rotate(args: argparse.Namespace) -> int:
    return not_implemented("rotate")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RaspberryPiServer mirror operations controller")
    parser.add_argument(
        "--config",
        type=Path,
        help=f"設定ファイルパス（省略時は {CONFIG_ENV_VAR} or {DEFAULT_CONFIG_PATH}）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="現在のミラー状態を表示").set_defaults(func=cmd_status)
    subparsers.add_parser("enable", help="ミラー送信を有効化").set_defaults(func=cmd_enable)
    subparsers.add_parser("disable", help="ミラー送信を無効化").set_defaults(func=cmd_disable)
    subparsers.add_parser("rotate", help="ミラー関連ログをローテーション").set_defaults(func=cmd_rotate)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MirrorCtlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    sys.exit(main())
