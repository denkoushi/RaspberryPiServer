from __future__ import annotations

from pathlib import Path
import sys

import pytest
from flask import Flask

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    content = ",".join(headers) + "\n"
    for row in rows:
        content += ",".join(row) + "\n"
    path.write_text(content, encoding="utf-8")


@pytest.fixture(name="app")
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    headers_prod = ["納期", "個数", "部品番号", "部品名", "製番", "工程名"]
    headers_std = ["部品名", "機械標準工数", "製造オーダー番号", "部品番号", "工程名"]
    _write_csv(
        plan_dir / "production_plan.csv",
        headers_prod,
        [["2025-01-01", "10", "PART-01", "部品A", "JOB-1", "切削"]],
    )
    _write_csv(
        plan_dir / "standard_times.csv",
        headers_std,
        [["部品A", "12", "JOB-1", "PART-01", "切削"]],
    )

    monkeypatch.setenv("PLAN_DATA_DIR", str(plan_dir))
    monkeypatch.setenv("API_TOKEN", "test-token")

    from app import server

    server.PLAN_DATA_DIR = Path(plan_dir)
    server.API_TOKEN = "test-token"
    server._plan_cache = server.PlanCache(server.PLAN_DATA_DIR, server.PLAN_DATASETS)  # type: ignore[attr-defined]
    class _DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return None

    class _DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _DummyCursor()

    class _DummyPsycopg:
        def connect(self, *args, **kwargs):
            return _DummyConnection()

    monkeypatch.setattr(server, "psycopg", _DummyPsycopg(), raising=False)

    application = server.create_app()
    application.config["TESTING"] = True
    return application


def test_internal_plan_cache_refresh_requires_token(app: Flask) -> None:
    client = app.test_client()

    resp = client.post("/internal/plan-cache/refresh")
    assert resp.status_code == 401

    resp_ok = client.post(
        "/internal/plan-cache/refresh",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp_ok.status_code == 200
    data = resp_ok.get_json()
    assert data["status"] == "ok"
    assert data["refreshed"]["production_plan"]["entries"] == 1
