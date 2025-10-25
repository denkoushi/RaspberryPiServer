#!/usr/bin/env python3

"""mirror_compare: daily comparison script for RaspberryPiServer mirror deployment."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "psycopg が見つかりません。`sudo apt install python3-psycopg2` などで導入してください。"
    ) from exc


DEFAULT_CONFIG_PATH = Path("/etc/mirrorctl/config.json")
CONFIG_ENV_VAR = "MIRRORCTL_CONFIG"
PART_LOCATIONS_FIELDS = (
    "location_code",
    "device_id",
    "last_scan_id",
    "scanned_at",
    "updated_at",
)


class MirrorCompareError(Exception):
    """Raised when comparison fails."""


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    candidate = (
        Path(os.environ[CONFIG_ENV_VAR])
        if CONFIG_ENV_VAR in os.environ
        else (path or DEFAULT_CONFIG_PATH)
    )
    if not candidate.exists():
        raise MirrorCompareError(f"設定ファイルが見つかりません: {candidate}")
    try:
        return load_json(candidate)
    except json.JSONDecodeError as exc:
        raise MirrorCompareError(f"設定ファイルの JSON 解析に失敗しました: {candidate}") from exc


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def read_counter(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return 0
    except ValueError:
        return 0


def write_counter(path: Path, value: int, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.write_text(f"{value}\n", encoding="utf-8")


def utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_part_locations(conn: psycopg.Connection) -> Dict[str, Dict[str, Any]]:
    query = """
        SELECT
          order_code,
          location_code,
          device_id,
          last_scan_id,
          scanned_at AT TIME ZONE 'UTC' AS scanned_at,
          updated_at AT TIME ZONE 'UTC' AS updated_at
        FROM part_locations
    """
    data: Dict[str, Dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            order_code = row[0]
            normalized = {
                "order_code": order_code,
                "location_code": row[1],
                "device_id": row[2],
                "last_scan_id": row[3],
                "scanned_at": utc_iso(row[4]),
                "updated_at": utc_iso(row[5]),
            }
            data[order_code] = normalized
    return data


def compare_records(
    primary: Dict[str, Dict[str, Any]],
    mirror: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int, int]:
    diffs: List[Dict[str, Any]] = []
    all_keys = set(primary) | set(mirror)
    for key in sorted(all_keys):
        p = primary.get(key)
        m = mirror.get(key)
        if p is None:
            diffs.append(
                {
                    "order_code": key,
                    "reason": "missing_in_primary",
                    "mirror": m,
                }
            )
            continue
        if m is None:
            diffs.append(
                {
                    "order_code": key,
                    "reason": "missing_in_mirror",
                    "primary": p,
                }
            )
            continue
        field_diffs = {
            field: (p[field], m[field])
            for field in PART_LOCATIONS_FIELDS
            if p.get(field) != m.get(field)
        }
        if field_diffs:
            diffs.append(
                {
                    "order_code": key,
                    "reason": "field_mismatch",
                    "diff": field_diffs,
                    "primary": p,
                    "mirror": m,
                }
            )
    return diffs, len(primary), len(mirror)


def append_json_line(path: Path, payload: Dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False))
        return
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def mirror_compare(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    primary_uri = config.get("primary_db_uri")
    mirror_uri = config.get("mirror_db_uri")
    if not primary_uri or not mirror_uri:
        raise MirrorCompareError("設定ファイルに primary_db_uri / mirror_db_uri を追加してください。")

    status_dir = Path(config.get("status_dir", "/var/lib/mirror"))
    log_dir = Path(config.get("log_dir", "/srv/rpi-server/logs"))
    ensure_dirs(status_dir, log_dir)
    ok_counter_path = Path(config.get("ok_counter_file", status_dir / "ok_counter"))
    status_log = log_dir / "mirror_status.log"
    diff_log = log_dir / "mirror_diff.log"

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    dry_run = args.dry_run
    strict = args.strict

    try:
        with psycopg.connect(primary_uri) as primary_conn, psycopg.connect(mirror_uri) as mirror_conn:
            primary_data = fetch_part_locations(primary_conn)
            mirror_data = fetch_part_locations(mirror_conn)
    except psycopg.Error as exc:
        error_payload = {"timestamp": now_iso, "status": "ERROR", "message": str(exc)}
        append_json_line(status_log, error_payload, dry_run=dry_run)
        if strict:
            raise MirrorCompareError(str(exc)) from exc
        return 1

    diffs, count_primary, count_mirror = compare_records(primary_data, mirror_data)
    diff_count = len(diffs)

    ok_counter = read_counter(ok_counter_path)
    if diff_count == 0:
        ok_counter += 1
    else:
        ok_counter = 0

    status_payload = {
        "timestamp": now_iso,
        "status": "OK" if diff_count == 0 else "DIFF",
        "primary_count": count_primary,
        "mirror_count": count_mirror,
        "diff_count": diff_count,
        "ok_streak": ok_counter,
    }
    append_json_line(status_log, status_payload, dry_run=dry_run)
    write_counter(ok_counter_path, ok_counter, dry_run=dry_run)

    if diffs:
        diff_payload = {
            "timestamp": now_iso,
            "diff": diffs,
        }
        append_json_line(diff_log, diff_payload, dry_run=dry_run)

    if diff_count > 0 and strict:
        raise MirrorCompareError(f"{diff_count} 件の差分が検出されました。")

    return 0 if diff_count == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror comparison for RaspberryPiServer")
    parser.add_argument(
        "--config",
        type=Path,
        help=f"設定ファイルパス（省略時は {CONFIG_ENV_VAR} or {DEFAULT_CONFIG_PATH}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ログやカウンタを更新せず、結果を標準出力へ表示する",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="差分やエラーを検出した場合に例外を送出し、非ゼロ終了コードを返す",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return mirror_compare(args)
    except MirrorCompareError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
