from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _write_csv(path: Path, headers: list[str], rows: list[list[str]] | None = None) -> None:
    content = ",".join(headers) + "\n"
    if rows:
        for row in rows:
            content += ",".join(row) + "\n"
    path.write_text(content, encoding="utf-8")


def test_update_plan_cache_success(tmp_path: Path) -> None:
    source_dir = tmp_path / "master"
    source_dir.mkdir()
    target_dir = tmp_path / "data" / "plan"

    _write_csv(
        source_dir / "production_plan.csv",
        ["納期", "個数", "部品番号", "部品名", "製番", "工程名"],
        [["2025-01-01", "1", "PART-1", "部品A", "JOB-1", "切削"]],
    )
    _write_csv(
        source_dir / "standard_times.csv",
        ["部品名", "機械標準工数", "製造オーダー番号", "部品番号", "工程名"],
        [["部品A", "10", "JOB-1", "PART-1", "切削"]],
    )

    env = os.environ.copy()
    env["SERVER_ROOT"] = str(tmp_path)
    env["SERVER_MASTER_DIR"] = str(source_dir)
    env["PLAN_DATA_DIR"] = str(target_dir)

    result = subprocess.run(
        ["python3", "scripts/update_plan_cache.py"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    assert (target_dir / "production_plan.csv").exists()
    assert (target_dir / "standard_times.csv").exists()

    # Dry-run should not modify files or create new timestamps
    target_dir.joinpath("production_plan.csv").unlink()
    env["PLAN_DATA_DIR"] = str(tmp_path / "dryrun-plan")
    result_dry = subprocess.run(
        ["python3", "scripts/update_plan_cache.py", "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result_dry.returncode == 0, result_dry.stderr
    assert not (tmp_path / "dryrun-plan").exists()


def test_update_plan_cache_header_mismatch(tmp_path: Path) -> None:
    source_dir = tmp_path / "master"
    source_dir.mkdir()
    target_dir = tmp_path / "data" / "plan"

    _write_csv(source_dir / "production_plan.csv", ["unexpected", "header"])

    env = os.environ.copy()
    env["SERVER_ROOT"] = str(tmp_path)
    env["SERVER_MASTER_DIR"] = str(source_dir)
    env["PLAN_DATA_DIR"] = str(target_dir)

    result = subprocess.run(
        ["python3", "scripts/update_plan_cache.py"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode != 0
    assert "unexpected header" in result.stderr
