#!/usr/bin/env python3
"""
Copy production plan / standard time CSVs from the master directory into
the API-facing PLAN_DATA_DIR so RaspberryPiServer endpoints serve the
latest data immediately after USB ingest.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

PLAN_DATASETS: Dict[str, List[str]] = {
    "production_plan.csv": ["納期", "個数", "部品番号", "部品名", "製番", "工程名"],
    "standard_times.csv": ["部品名", "機械標準工数", "製造オーダー番号", "部品番号", "工程名"],
}


def resolve_paths() -> tuple[Path, Path]:
    server_root = Path(os.environ.get("SERVER_ROOT", "/srv/rpi-server")).resolve()
    source_dir = Path(os.environ.get("SERVER_MASTER_DIR", server_root / "master")).resolve()
    target_dir = Path(os.environ.get("PLAN_DATA_DIR", server_root / "data/plan")).resolve()
    return source_dir, target_dir


def find_source(base: Path, filename: str) -> Path | None:
    candidates = [
        base / filename,
        base / "plan" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def validate_header(path: Path, expected: List[str]) -> bool:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            headers = next(reader, [])
    except Exception as exc:  # pragma: no cover - logged for operator visibility
        print(f"[plan-refresh] failed to read header from {path}: {exc}", file=sys.stderr)
        return False
    if headers != expected:
        print(
            f"[plan-refresh] unexpected header for {path.name}: {headers} (expected {expected})",
            file=sys.stderr,
        )
        return False
    return True


def copy_dataset(source: Path, dest: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"[plan-refresh] (dry-run) copy {source} -> {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    try:
        dest.chmod(0o640)
    except PermissionError:
        pass
    print(f"[plan-refresh] copied {source.name} -> {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh plan datasets for RaspberryPiServer API")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without copying files")
    args = parser.parse_args()

    source_dir, target_dir = resolve_paths()
    status = 0

    if not source_dir.exists():
        print(f"[plan-refresh] source directory not found: {source_dir}", file=sys.stderr)
        return 0

    for filename, expected_header in PLAN_DATASETS.items():
        source_path = find_source(source_dir, filename)
        if source_path is None:
            print(f"[plan-refresh] warning: {filename} not found under {source_dir}", file=sys.stderr)
            continue
        if not validate_header(source_path, expected_header):
            status = 1
            continue
        dest_path = target_dir / filename
        copy_dataset(source_path, dest_path, args.dry_run)

    return status


if __name__ == "__main__":
    sys.exit(main())
