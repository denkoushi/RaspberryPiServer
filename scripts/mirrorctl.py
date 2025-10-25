#!/usr/bin/env python3

"""mirrorctl: RaspberryPiServer mirror operations helper CLI."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


DEFAULT_CONFIG_PATH = Path("/etc/mirrorctl/config.json")
CONFIG_ENV_VAR = "MIRRORCTL_CONFIG"
BACKUP_SUFFIX = ".bak"
LOG_TARGETS = ("mirror_requests.log", "mirror_diff.log")


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


def run_command(command: Sequence[str], *, input_text: Optional[str] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        input=input_text,
    )


def run_systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return run_command(["systemctl", *args])


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
        lines = fh.readlines()
    return lines[-1].rstrip("\n") if lines else None


def read_counter(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def ssh_command(host: str, user: str, remote_command: str, *, input_text: Optional[str] = None, sudo: bool = False) -> subprocess.CompletedProcess[str]:
    target = f"{user}@{host}"
    cmd = ["ssh", "-o", "BatchMode=yes", target]
    if sudo:
        remote_command = f"sudo {remote_command}"
    cmd.append(remote_command)
    return run_command(cmd, input_text=input_text)


def fetch_remote_config(host: str, user: str, config_path: str) -> Dict[str, Any]:
    result = ssh_command(host, user, f"cat {config_path}")
    if result.returncode != 0:
        raise MirrorCtlError(f"Pi Zero 設定の取得に失敗しました: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MirrorCtlError("Pi Zero 設定の JSON 解析に失敗しました") from exc


def backup_remote_config(host: str, user: str, config_path: str) -> None:
    backup_cmd = f"cp {config_path} {config_path}{BACKUP_SUFFIX}"
    result = ssh_command(host, user, backup_cmd, sudo=True)
    if result.returncode != 0:
        raise MirrorCtlError(f"Pi Zero 設定のバックアップに失敗しました: {result.stderr.strip()}")


def write_remote_config(host: str, user: str, config_path: str, content: Dict[str, Any]) -> None:
    payload = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    result = ssh_command(host, user, f"tee {config_path}", input_text=payload)
    if result.returncode != 0:
        raise MirrorCtlError(f"Pi Zero 設定の書き込みに失敗しました: {result.stderr.strip()}")


def restart_remote_service(host: str, user: str, service: str) -> None:
    if not service:
        return
    result = ssh_command(host, user, f"systemctl restart {service}", sudo=True)
    if result.returncode != 0:
        raise MirrorCtlError(f"Pi Zero 側サービス再起動に失敗しました: {result.stderr.strip()}")


def log_event(log_dir: Path, message: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "mirror_status.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now().isoformat()} {message}\n")


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


def cmd_enable(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    host = config["pi_zero_host"]
    user = config.get("ssh_user", "pi")
    remote_path = config["config_path"]
    timer_name = config.get("mirror_timer", "mirror-compare.timer")
    service_name = config.get("mirror_service", "mirror-compare.service")
    pi_zero_service = config.get("pi_zero_service", "")
    mirror_endpoint = config.get("mirror_endpoint")
    primary_endpoint = config.get("primary_endpoint")
    status_dir = Path(config.get("status_dir", "/var/lib/mirror"))
    ok_counter_path = Path(config.get("ok_counter_file", status_dir / "ok_counter"))
    log_dir = Path(config.get("log_dir", "/srv/rpi-server/logs"))

    if not mirror_endpoint:
        raise MirrorCtlError("設定ファイルに mirror_endpoint が定義されていません。")

    backup_remote_config(host, user, remote_path)
    remote_config = fetch_remote_config(host, user, remote_path)
    remote_config["mirror_mode"] = True
    remote_config["mirror_endpoint"] = mirror_endpoint
    if primary_endpoint:
        remote_config.setdefault("primary_endpoint", primary_endpoint)
    write_remote_config(host, user, remote_path, remote_config)
    restart_remote_service(host, user, pi_zero_service)

    timer_result = run_systemctl("enable", "--now", timer_name)
    if timer_result.returncode != 0:
        raise MirrorCtlError(f"{timer_name} の有効化に失敗しました: {timer_result.stderr.strip()}")

    service_result = run_systemctl("restart", service_name)
    if service_result.returncode != 0:
        raise MirrorCtlError(f"{service_name} の再起動に失敗しました: {service_result.stderr.strip()}")

    status_dir.mkdir(parents=True, exist_ok=True)
    ok_counter_path.write_text("0\n", encoding="utf-8")

    log_event(log_dir, "enable executed")
    print("mirrorctl enable: 完了")
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    host = config["pi_zero_host"]
    user = config.get("ssh_user", "pi")
    remote_path = config["config_path"]
    timer_name = config.get("mirror_timer", "mirror-compare.timer")
    service_name = config.get("mirror_service", "mirror-compare.service")
    pi_zero_service = config.get("pi_zero_service", "")
    log_dir = Path(config.get("log_dir", "/srv/rpi-server/logs"))

    remote_config = fetch_remote_config(host, user, remote_path)
    remote_config["mirror_mode"] = False
    remote_config.pop("mirror_endpoint", None)
    write_remote_config(host, user, remote_path, remote_config)
    restart_remote_service(host, user, pi_zero_service)

    timer_result = run_systemctl("disable", "--now", timer_name)
    if timer_result.returncode != 0:
        raise MirrorCtlError(f"{timer_name} の無効化に失敗しました: {timer_result.stderr.strip()}")

    service_result = run_systemctl("stop", service_name)
    if service_result.returncode != 0:
        raise MirrorCtlError(f"{service_name} の停止に失敗しました: {service_result.stderr.strip()}")

    log_event(log_dir, "disable executed")
    print("mirrorctl disable: 完了")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    log_dir = Path(config.get("log_dir", "/srv/rpi-server/logs"))
    retention_days = int(config.get("log_retention_days", 30))
    now = datetime.now()
    log_dir.mkdir(parents=True, exist_ok=True)

    for target in LOG_TARGETS:
        src = log_dir / target
        if not src.exists():
            continue
        timestamp = now.strftime("%Y%m%d%H%M%S")
        dest = log_dir / f"{src.stem}-{timestamp}.log.gz"
        with src.open("rb") as source, gzip.open(dest, "wb") as gz:
            gz.write(source.read())
        src.unlink()

    cutoff = now - timedelta(days=retention_days)
    for gz_path in log_dir.glob("mirror_*.log.gz"):
        mtime = datetime.fromtimestamp(gz_path.stat().st_mtime)
        if mtime < cutoff:
            gz_path.unlink()

    log_event(log_dir, "rotate executed")
    print("mirrorctl rotate: 完了")
    return 0


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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MirrorCtlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    sys.exit(main())
