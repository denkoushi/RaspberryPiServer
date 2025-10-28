from __future__ import annotations

import copy
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.plan_cache import PlanCache


DATASETS = {
    "production_plan": {
        "filename": "production_plan.csv",
        "columns": ["納期", "個数", "部品番号", "部品名", "製番", "工程名"],
        "label": "生産計画",
    },
    "standard_times": {
        "filename": "standard_times.csv",
        "columns": ["部品名", "機械標準工数", "製造オーダー番号", "部品番号", "工程名"],
        "label": "標準工数",
    },
}


def _write_csv(path: Path, headers: list[str], rows: list[list[str]] | None = None) -> None:
    lines = [",".join(headers)]
    for row in rows or []:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_plan_cache_refresh_and_get(tmp_path: Path) -> None:
    cache = PlanCache(tmp_path, DATASETS)

    _write_csv(
        tmp_path / "production_plan.csv",
        DATASETS["production_plan"]["columns"],  # type: ignore[index]
        [["2025-01-01", "10", "PART-01", "部品A", "JOB-1", "切削"]],
    )
    _write_csv(
        tmp_path / "standard_times.csv",
        DATASETS["standard_times"]["columns"],  # type: ignore[index]
        [["部品A", "12", "JOB-1", "PART-01", "切削"]],
    )

    summary = cache.refresh()
    assert summary["production_plan"]["entries"] == 1
    assert summary["production_plan"]["error"] is None

    dataset = cache.get_dataset("production_plan")
    assert dataset["entries"][0]["部品番号"] == "PART-01"
    assert dataset["error"] is None


def test_plan_cache_detects_header_mismatch(tmp_path: Path) -> None:
    cache = PlanCache(tmp_path, DATASETS)
    _write_csv(tmp_path / "production_plan.csv", ["unexpected"])

    result = cache.get_dataset("production_plan")
    assert result["error"] is not None
    assert result["entries"] == []


def test_plan_cache_auto_refresh_on_change(tmp_path: Path) -> None:
    cache = PlanCache(tmp_path, DATASETS)
    columns = DATASETS["production_plan"]["columns"]  # type: ignore[index]

    csv_path = tmp_path / "production_plan.csv"
    _write_csv(csv_path, columns, [["2025-01-01", "10", "PART-01", "部品A", "JOB-1", "切削"]])
    cache.refresh(["production_plan"])

    dataset = cache.get_dataset("production_plan")
    first_entries = copy.deepcopy(dataset["entries"])
    assert first_entries

    _write_csv(csv_path, columns, [["2025-02-01", "5", "PART-02", "部品B", "JOB-2", "組立"]])
    refreshed = cache.get_dataset("production_plan")
    assert refreshed["entries"][0]["部品番号"] == "PART-02"
