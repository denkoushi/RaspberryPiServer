from __future__ import annotations

import importlib
import json
import types
from pathlib import Path
import sys

import pytest
from flask import Blueprint, Flask

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    content = ",".join(headers) + "\n"
    for row in rows:
        content += ",".join(row) + "\n"
    path.write_text(content, encoding="utf-8")


class _DummyCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return None

    def fetchall(self):
        return []


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


@pytest.fixture(name="logistics_app")
def fixture_logistics_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Flask, Path, list[tuple[str, dict, bool]], Path]:
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    _write_csv(
        plan_dir / "production_plan.csv",
        ["納期", "個数", "部品番号", "部品名", "製番", "工程名"],
        [["2025-01-01", "1", "PART-01", "部品A", "JOB-1", "切削"]],
    )
    _write_csv(
        plan_dir / "standard_times.csv",
        ["部品名", "機械標準工数", "製造オーダー番号", "部品番号", "工程名"],
        [["部品A", "12", "JOB-1", "PART-01", "切削"]],
    )

    jobs_path = tmp_path / "logistics" / "jobs.json"
    audit_path = tmp_path / "audit.log"

    monkeypatch.setenv("PLAN_DATA_DIR", str(plan_dir))
    monkeypatch.setenv("LOGISTICS_DATA_PATH", str(jobs_path))
    monkeypatch.setenv("API_TOKEN", "test-token")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.touch()
    monkeypatch.setenv("LOGISTICS_AUDIT_PATH", str(audit_path))

    class _DummyPsycopgModule:
        @staticmethod
        def connect(*args, **kwargs):
            return _DummyConnection()

    class _DummySocketIO:
        def __init__(self, *args, **kwargs):
            self.settings = {"args": args, "kwargs": kwargs}

        def init_app(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None

    fake_socketio_module = types.ModuleType("flask_socketio")
    setattr(fake_socketio_module, "SocketIO", _DummySocketIO)

    dummy_blueprint = Blueprint("document_viewer", __name__)
    fake_document_viewer = types.ModuleType("app.document_viewer")
    setattr(fake_document_viewer, "document_viewer_bp", dummy_blueprint)

    monkeypatch.setitem(sys.modules, "psycopg", _DummyPsycopgModule())
    monkeypatch.setitem(sys.modules, "flask_socketio", fake_socketio_module)
    monkeypatch.setitem(sys.modules, "app.document_viewer", fake_document_viewer)
    monkeypatch.setitem(sys.modules, "document_viewer", fake_document_viewer)

    from app import server

    importlib.reload(server)

    server.PLAN_DATA_DIR = plan_dir
    server.LOGISTICS_DATA_PATH = jobs_path
    server.API_TOKEN = "test-token"
    server._plan_cache = server.PlanCache(server.PLAN_DATA_DIR, server.PLAN_DATASETS)  # type: ignore[attr-defined]
    monkeypatch.setattr(server, "psycopg", _DummyPsycopg(), raising=False)

    emissions: list[tuple[str, dict, bool]] = []

    def _emit(event: str, data: dict, broadcast: bool = False) -> None:
        emissions.append((event, data, broadcast))

    monkeypatch.setattr(server.socketio, "emit", _emit)

    application = server.create_app()
    application.config["TESTING"] = True
    return application, jobs_path, emissions, audit_path


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_get_logistics_jobs_empty(logistics_app) -> None:
    app, jobs_path, emissions, _ = logistics_app
    client = app.test_client()

    resp = client.get("/api/logistics/jobs", headers=_auth())
    assert resp.status_code == 200
    assert resp.get_json() == {"items": []}
    assert jobs_path.exists()
    assert jobs_path.read_text(encoding="utf-8") == "[]"
    assert emissions == []


def test_create_logistics_job_persists_and_emits(logistics_app) -> None:
    app, jobs_path, emissions, _ = logistics_app
    client = app.test_client()

    payload = {
        "part_code": "PART-01",
        "from_location": "RACK-A1",
        "to_location": "RACK-B2",
    }
    resp = client.post("/api/logistics/jobs", json=payload, headers=_auth())
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["part_code"] == "PART-01"
    assert data["from_location"] == "RACK-A1"
    assert data["to_location"] == "RACK-B2"
    assert data["status"] == "pending"
    assert data["job_id"].startswith("job-")
    assert data["requested_at"]
    assert data["updated_at"]

    stored = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert len(stored) == 1
    assert stored[0]["job_id"] == data["job_id"]

    assert emissions == [("logistics_job_updated", data, True)]


def test_create_logistics_job_missing_fields_rejected(logistics_app) -> None:
    app, *_ = logistics_app
    client = app.test_client()

    resp = client.post(
        "/api/logistics/jobs",
        json={"part_code": "PART-01", "from_location": "RACK-A1"},
        headers=_auth(),
    )
    assert resp.status_code == 400


def test_update_logistics_job_status(logistics_app) -> None:
    app, jobs_path, emissions, _ = logistics_app
    client = app.test_client()

    create_resp = client.post(
        "/api/logistics/jobs",
        json={
            "job_id": "job-001",
            "part_code": "PART-01",
            "from_location": "RACK-A1",
            "to_location": "RACK-B2",
        },
        headers=_auth(),
    )
    assert create_resp.status_code == 201

    update_resp = client.post(
        "/api/logistics/jobs/job-001/status",
        json={"status": "in_transit", "to_location": "RACK-C3"},
        headers=_auth(),
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()
    assert updated["job_id"] == "job-001"
    assert updated["status"] == "in_transit"
    assert updated["to_location"] == "RACK-C3"

    stored = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert stored[0]["status"] == "in_transit"
    assert stored[0]["to_location"] == "RACK-C3"

    events = [event for event, *_ in emissions]
    assert events.count("logistics_job_updated") == 2


def test_update_logistics_job_missing_status_rejected(logistics_app) -> None:
    app, *_ = logistics_app
    client = app.test_client()

    resp = client.post(
        "/api/logistics/jobs/job-unknown/status",
        json={"from_location": "RACK-A1"},
        headers=_auth(),
    )
    assert resp.status_code == 400


def test_update_logistics_job_not_found(logistics_app) -> None:
    app, *_ = logistics_app
    client = app.test_client()

    resp = client.post(
        "/api/logistics/jobs/job-unknown/status",
        json={"status": "completed"},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_get_jobs_with_limit(logistics_app) -> None:
    app, *_ = logistics_app
    client = app.test_client()

    for index in range(3):
        resp = client.post(
            "/api/logistics/jobs",
            json={
                "job_id": f"job-{index}",
                "part_code": f"PART-{index}",
                "from_location": f"FROM-{index}",
                "to_location": f"TO-{index}",
            },
            headers=_auth(),
        )
        assert resp.status_code == 201

    limited = client.get("/api/logistics/jobs?limit=2", headers=_auth())
    assert limited.status_code == 200
    items = limited.get_json()["items"]
    assert len(items) == 2
    assert items[0]["updated_at"] >= items[1]["updated_at"]


def test_get_jobs_invalid_limit_returns_400(logistics_app) -> None:
    app, *_ = logistics_app
    client = app.test_client()

    resp = client.get("/api/logistics/jobs?limit=abc", headers=_auth())
    assert resp.status_code == 400


def test_logistics_jobs_pruned_to_max(logistics_app, monkeypatch) -> None:
    app, jobs_path, _, _ = logistics_app
    client = app.test_client()

    from app import server  # import within test to access module vars

    monkeypatch.setattr(server, "LOGISTICS_MAX_JOBS", 3)
    monkeypatch.setattr(server, "LOGISTICS_RETENTION_DAYS", 365)

    for index in range(5):
        resp = client.post(
            "/api/logistics/jobs",
            json={
                "job_id": f"job-{index}",
                "part_code": f"PART-{index}",
                "from_location": f"FROM-{index}",
                "to_location": f"TO-{index}",
                "requested_at": f"2025-10-31T12:0{index}:00Z",
            },
            headers=_auth(),
        )
        assert resp.status_code == 201

    stored = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert len(stored) == 3
    remaining_ids = [item["job_id"] for item in stored]
    assert set(remaining_ids) == {"job-4", "job-3", "job-2"}


def test_create_logistics_job_invalid_status(logistics_app) -> None:
    app, *_ = logistics_app
    client = app.test_client()

    resp = client.post(
        "/api/logistics/jobs",
        json={
            "part_code": "PART",
            "from_location": "FROM",
            "to_location": "TO",
            "status": "unknown",
        },
        headers=_auth(),
    )
    assert resp.status_code == 400


def test_logistics_status_transition_conflict(logistics_app) -> None:
    app, jobs_path, _, _ = logistics_app
    client = app.test_client()

    resp = client.post(
        "/api/logistics/jobs",
        json={
            "job_id": "job-xyz",
            "part_code": "PART-X",
            "from_location": "FROM-X",
            "to_location": "TO-X",
        },
        headers=_auth(),
    )
    assert resp.status_code == 201

    resp = client.post(
        "/api/logistics/jobs/job-xyz/status",
        json={"status": "completed"},
        headers=_auth(),
    )
    assert resp.status_code == 200

    resp_conflict = client.post(
        "/api/logistics/jobs/job-xyz/status",
        json={"status": "in_transit"},
        headers=_auth(),
    )
    assert resp_conflict.status_code == 409
    stored = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert stored[0]["status"] == "completed"


def test_logistics_audit_log_records_events(logistics_app) -> None:
    app, _, emissions, audit_path = logistics_app
    client = app.test_client()

    resp = client.post(
        "/api/logistics/jobs",
        json={
            "job_id": "job-audit",
            "part_code": "PART-A",
            "from_location": "FROM-A",
            "to_location": "TO-A",
        },
        headers=_auth(),
    )
    assert resp.status_code == 201

    resp = client.post(
        "/api/logistics/jobs/job-audit/status",
        json={"status": "in_transit"},
        headers=_auth(),
    )
    assert resp.status_code == 200

    from app import server

    for handler in server._get_logistics_audit_logger().handlers:
        handler.flush()

    contents = audit_path.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in contents:
        start = line.find("{")
        if start == -1:
            continue
        chunk = line[start:]
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        entries.append(data)
    events = {entry.get("event") for entry in entries}
    assert "create" in events or "update" in events
    assert "status_update" in events
    # Ensure socket emissions still occurred
    assert any(event == "logistics_job_updated" for event, *_ in emissions)
