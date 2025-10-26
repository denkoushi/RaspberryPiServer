import importlib
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest

try:
    import psycopg  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    psycopg = ModuleType("psycopg")
    sys.modules["psycopg"] = psycopg  # type: ignore


class SocketIOStub:
    def __init__(self, *args, **kwargs):  # pylint: disable=unused-argument
        self.app = None

    def init_app(self, app, **kwargs):  # pylint: disable=unused-argument
        self.app = app

    def emit(self, event, data=None, **kwargs):  # pylint: disable=unused-argument
        return None

    def run(self, app, host=None, port=None, **kwargs):  # pylint: disable=unused-argument
        return (app, host, port)


class FakeDatabase:
    def __init__(self):
        self.rows = {}

    def connect(self, dsn=None, autocommit=False, **kwargs):  # pylint: disable=unused-argument
        return FakeConnection(self)

    def upsert_part_location(self, params):
        order_code, location_code, device_id, scan_id, scanned_at = params
        now = datetime.now(timezone.utc)
        record = {
            "order_code": order_code,
            "location_code": location_code,
            "device_id": device_id,
            "last_scan_id": scan_id,
            "scanned_at": scanned_at or now,
            "updated_at": now,
        }
        self.rows[order_code] = record
        return (
            record["order_code"],
            record["location_code"],
            record["device_id"],
            record["last_scan_id"],
            record["scanned_at"],
            record["updated_at"],
        )


class FakeConnection:
    def __init__(self, database):
        self._database = database

    def cursor(self):
        return FakeCursor(self._database)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeCursor:
    def __init__(self, database):
        self._database = database
        self._result = None

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).upper()
        if "SELECT 1" in normalized:
            self._result = (1,)
            return
        if "INSERT INTO PART_LOCATIONS" in normalized:
            self._result = self._database.upsert_part_location(params)
            return
        # CREATE TABLE などのクエリは副作用なしで無視
        self._result = None

    def fetchone(self):
        return self._result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def server_module(monkeypatch, tmp_path):
    fake_db = FakeDatabase()
    monkeypatch.setattr(psycopg, "connect", fake_db.connect, raising=False)
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    monkeypatch.setenv("VIEWER_DOCS_DIR", str(docs_dir))
    monkeypatch.setenv("VIEWER_LOG_PATH", str(tmp_path / "viewer.log"))
    sys.modules.pop("app.document_viewer", None)
    socketio_module = ModuleType("flask_socketio")
    socketio_module.SocketIO = SocketIOStub
    monkeypatch.setitem(sys.modules, "flask_socketio", socketio_module)
    module = importlib.import_module("app.server")
    module = importlib.reload(module)
    captured = []

    def fake_emit(event, data=None, **kwargs):
        captured.append(SimpleNamespace(event=event, data=data, kwargs=kwargs))

    monkeypatch.setattr(module.socketio, "emit", fake_emit)
    monkeypatch.setattr(module, "API_TOKEN", "")
    return SimpleNamespace(module=module, db=fake_db, emitted=captured)


def test_healthz_returns_ok(server_module):
    client = server_module.module.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_create_scan_persists_and_emits(server_module):
    payload = {
        "part_code": "testpart",
        "location_code": "RACK-A1",
        "device_id": "handheld-01",
    }

    client = server_module.module.app.test_client()
    response = client.post("/api/v1/scans", json=payload)
    body = response.get_json()

    assert response.status_code == 201
    assert body["order_code"] == "testpart"
    assert body["location_code"] == "RACK-A1"
    assert body["device_id"] == "handheld-01"
    assert body["accepted"] is True
    assert body["scan_id"].startswith("scan-")
    assert body["scanned_at"].endswith("Z")
    assert body["updated_at"].endswith("Z")

    stored = server_module.db.rows["testpart"]
    assert stored["location_code"] == "RACK-A1"
    assert stored["device_id"] == "handheld-01"
    assert isinstance(stored["scanned_at"], datetime)
    assert isinstance(stored["updated_at"], datetime)

    events = server_module.emitted
    assert [evt.event for evt in events] == ["part_location_updated", "scan_update"]
    assert all(evt.kwargs.get("broadcast") is True for evt in events)
    for evt in events:
        assert evt.data == body


def test_create_scan_requires_bearer_token(server_module, monkeypatch):
    monkeypatch.setattr(server_module.module, "API_TOKEN", "secret-token")
    client = server_module.module.app.test_client()

    unauthorized = client.post(
        "/api/v1/scans",
        json={"part_code": "x", "location_code": "y"},
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/api/v1/scans",
        json={"part_code": "x", "location_code": "y"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert authorized.status_code == 201


def test_create_scan_with_custom_timestamp(server_module):
    client = server_module.module.app.test_client()

    response = client.post(
        "/api/v1/scans",
        json={
            "part_code": "custom",
            "location_code": "LOC-1",
            "scanned_at": "2024-12-31T12:34:56Z",
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body["scanned_at"] == "2024-12-31T12:34:56Z"


def test_create_scan_with_epoch_timestamp(server_module):
    client = server_module.module.app.test_client()
    epoch_value = 1735685696.5  # 任意の epoch 秒
    response = client.post(
        "/api/v1/scans",
        json={
            "part_code": "epoch",
            "location_code": "LOC-2",
            "scanned_at": epoch_value,
        },
    )
    body = response.get_json()

    expected_iso = datetime.fromtimestamp(epoch_value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    assert response.status_code == 201
    assert body["scanned_at"] == expected_iso


def test_create_scan_missing_fields(server_module):
    client = server_module.module.app.test_client()
    response = client.post(
        "/api/v1/scans",
        json={"part_code": "missing"},
    )
    assert response.status_code == 400


def test_create_scan_rejects_non_string_fields(server_module):
    client = server_module.module.app.test_client()
    response = client.post(
        "/api/v1/scans",
        json={"part_code": "test", "location_code": 123},
    )
    assert response.status_code == 400


def test_create_scan_invalid_timestamp(server_module):
    client = server_module.module.app.test_client()
    response = client.post(
        "/api/v1/scans",
        json={
            "part_code": "badts",
            "location_code": "LOC-3",
            "scanned_at": "not-a-date",
        },
    )
    assert response.status_code == 400
