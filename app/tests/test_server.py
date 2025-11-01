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
        self.loans = {}
        self.users = {}
        self.tools = {}
        self.tool_names = set()
        self.loan_counter = 1

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

    def list_part_locations(self, limit):
        items = sorted(
            self.rows.values(),
            key=lambda item: item["updated_at"],
            reverse=True,
        )
        limited = items[: max(1, min(limit, 1000))]
        result = []
        for row in limited:
            result.append(
                (
                    row["order_code"],
                    row["location_code"],
                    row["device_id"],
                    row["last_scan_id"],
                    row["scanned_at"],
                    row["updated_at"],
                )
            )
        return result

    def add_loan(self, *, tool_uid: str, borrower_uid: str, loaned_at=None, returned_at=None):
        loan_id = self.loan_counter
        self.loan_counter += 1
        if loaned_at is None:
            loaned_at = datetime.now(timezone.utc)
        self.loans[loan_id] = {
            "id": loan_id,
            "tool_uid": tool_uid,
            "borrower_uid": borrower_uid,
            "loaned_at": loaned_at,
            "returned_at": returned_at,
        }
        return loan_id

    def list_open_loans(self, limit: int):
        open_loans = [loan for loan in self.loans.values() if loan["returned_at"] is None]
        open_loans.sort(key=lambda item: item["loaned_at"], reverse=True)
        result = []
        for loan in open_loans[: max(1, min(limit, 1000))]:
            tool_name = self.tools.get(loan["tool_uid"], loan["tool_uid"])
            borrower_name = self.users.get(loan["borrower_uid"], loan["borrower_uid"])
            result.append(
                (
                    loan["id"],
                    loan["tool_uid"],
                    tool_name,
                    loan["borrower_uid"],
                    borrower_name,
                    loan["loaned_at"],
                )
            )
        return result

    def list_recent_history(self, limit: int):
        entries = []
        for loan in self.loans.values():
            action = "返却" if loan["returned_at"] else "貸出"
            tool_name = self.tools.get(loan["tool_uid"], loan["tool_uid"])
            borrower_name = self.users.get(loan["borrower_uid"], loan["borrower_uid"])
            entries.append(
                (
                    action,
                    tool_name,
                    borrower_name,
                    loan["loaned_at"],
                    loan["returned_at"],
                )
            )
        entries.sort(
            key=lambda item: (item[4] or item[3] or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        return entries[: max(1, min(limit, 1000))]


class FakeConnection:
    def __init__(self, database):
        self._database = database

    def cursor(self):
        return FakeCursor(self._database)

    def commit(self):  # pylint: disable=unused-argument
        return None

    def rollback(self):  # pylint: disable=unused-argument
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeCursor:
    def __init__(self, database):
        self._database = database
        self._result = None
        self._result_all = None
        self.rowcount = 0

    def execute(self, query, params=None):
        self.rowcount = 0
        normalized = " ".join(query.split())
        upper = normalized.upper()
        if upper.strip() == "SELECT 1":
            self._result = (1,)
            return
        if "INSERT INTO PART_LOCATIONS" in upper:
            self._result = self._database.upsert_part_location(params)
            return
        if "FROM PART_LOCATIONS" in upper and "SELECT" in upper:
            limit = params[0] if params else 200
            self._result_all = self._database.list_part_locations(limit)
            return
        # CREATE TABLE などのクエリは副作用なしで無視
        if "INSERT INTO USERS" in upper:
            uid, name = params
            self._database.users[uid] = name
            self.rowcount = 1
            return
        if "INSERT INTO TOOLS" in upper:
            uid, name = params
            self._database.tools[uid] = name
            self.rowcount = 1
            return
        if "SELECT FULL_NAME FROM USERS WHERE UID" in upper:
            uid = params[0]
            name = self._database.users.get(uid)
            self._result = (name,) if name else None
            return
        if "SELECT NAME FROM TOOLS WHERE UID" in upper:
            uid = params[0]
            name = self._database.tools.get(uid)
            self._result = (name,) if name else None
            return
        if "SELECT COALESCE(NAME" in upper and "FROM TOOLS WHERE UID" in upper:
            uid_param = params[1]
            name = self._database.tools.get(uid_param)
            self._result = (name or params[0],)
            return
        if "SELECT COALESCE(FULL_NAME" in upper and "FROM USERS WHERE UID" in upper:
            uid_param = params[1]
            name = self._database.users.get(uid_param)
            self._result = (name or params[0],)
            return
        if "SELECT NAME FROM TOOL_MASTER" in upper:
            names = sorted(self._database.tool_names)
            self._result_all = [(name,) for name in names]
            self.rowcount = len(names)
            return
        if "INSERT INTO TOOL_MASTER" in upper:
            (name,) = params
            self._database.tool_names.add(name)
            self.rowcount = 1
            return
        if "DELETE FROM TOOL_MASTER" in upper:
            (name,) = params
            if name in self._database.tool_names:
                self._database.tool_names.remove(name)
                self.rowcount = 1
            else:
                self.rowcount = 0
            return
        if "SELECT 1 FROM TOOLS WHERE NAME" in upper:
            (name,) = params
            exists = any(tool_name == name for tool_name in self._database.tools.values())
            self._result = (1,) if exists else None
            return
        if "SELECT L.ID" in upper and "FROM LOANS" in upper and "RETURNED_AT IS NULL" in upper and "ORDER BY" in upper:
            limit = params[0] if params else 100
            rows = self._database.list_open_loans(limit)
            self._result_all = rows
            self.rowcount = len(rows)
            return
        if "SELECT L.TOOL_UID" in upper and "FROM LOANS L" in upper and "RETURNED_AT IS NULL" in upper:
            (loan_id,) = params
            loan = self._database.loans.get(loan_id)
            if loan and loan["returned_at"] is None:
                tool_name = self._database.tools.get(loan["tool_uid"], loan["tool_uid"])
                self._result = (loan["tool_uid"], tool_name)
            else:
                self._result = None
            return
        if "CASE WHEN L.RETURNED_AT" in upper and "FROM LOANS" in upper:
            limit = params[0] if params else 50
            rows = self._database.list_recent_history(limit)
            self._result_all = rows
            self.rowcount = len(rows)
            return
        if "UPDATE LOANS" in upper and "RETURNING TOOL_UID" in upper:
            (loan_id,) = params
            loan = self._database.loans.get(loan_id)
            if not loan or loan["returned_at"] is not None:
                self._result = None
                self.rowcount = 0
            else:
                loan["returned_at"] = datetime.now(timezone.utc)
                self._result = (loan["tool_uid"], loan["borrower_uid"])
                self.rowcount = 1
            return
        if "DELETE FROM LOANS" in upper:
            (loan_id,) = params
            loan = self._database.loans.get(loan_id)
            if loan and loan["returned_at"] is None:
                del self._database.loans[loan_id]
                self.rowcount = 1
            else:
                self.rowcount = 0
            self._result = None
            return
        self._result = None
        self._result_all = None

    def fetchone(self):
        return self._result

    def fetchall(self):
        return self._result_all or []

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
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    monkeypatch.setenv("PLAN_DATA_DIR", str(plan_dir))
    monkeypatch.setenv("STATION_CONFIG_PATH", str(tmp_path / "station.json"))
    logistics_path = tmp_path / "logistics" / "jobs.json"
    logistics_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOGISTICS_DATA_PATH", str(logistics_path))
    audit_path = tmp_path / "logs" / "logistics_audit.log"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOGISTICS_AUDIT_PATH", str(audit_path))
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


def test_get_loans_returns_entries(server_module):
    db = server_module.db
    db.users["user-1"] = "User One"
    db.tools["tool-1"] = "Tool One"
    db.add_loan(tool_uid="tool-1", borrower_uid="user-1")

    client = server_module.module.app.test_client()
    response = client.get("/api/loans")
    body = response.get_json()

    assert response.status_code == 200
    assert len(body["open_loans"]) == 1
    assert body["open_loans"][0]["tool_uid"] == "tool-1"
    assert body["open_loans"][0]["borrower_uid"] == "user-1"
    assert body["history"]


def test_manual_return_marks_loan_and_emits(server_module):
    db = server_module.db
    db.users["user-2"] = "User Two"
    db.tools["tool-2"] = "Tool Two"
    loan_id = db.add_loan(tool_uid="tool-2", borrower_uid="user-2")

    client = server_module.module.app.test_client()
    response = client.post(f"/api/loans/{loan_id}/manual_return")

    assert response.status_code == 200
    assert db.loans[loan_id]["returned_at"] is not None
    assert any(evt.event == "transaction_complete" for evt in server_module.emitted)


def test_delete_loan_removes_entry(server_module):
    db = server_module.db
    db.users["user-3"] = "User Three"
    db.tools["tool-3"] = "Tool Three"
    loan_id = db.add_loan(tool_uid="tool-3", borrower_uid="user-3")

    client = server_module.module.app.test_client()
    response = client.delete(f"/api/loans/{loan_id}")

    assert response.status_code == 200
    assert loan_id not in db.loans


def test_register_user_and_tool(server_module):
    client = server_module.module.app.test_client()

    response_user = client.post("/api/register_user", json={"uid": "user-4", "name": "User Four"})
    assert response_user.status_code == 200
    assert server_module.db.users["user-4"] == "User Four"

    response_tool = client.post("/api/register_tool", json={"uid": "tool-4", "name": "Tool Four"})
    assert response_tool.status_code == 200
    assert server_module.db.tools["tool-4"] == "Tool Four"

    tag_response = client.get("/api/tag-info/user-4")
    assert tag_response.status_code == 200
    assert tag_response.get_json()["type"] == "user"


def test_add_and_delete_tool_name(server_module):
    client = server_module.module.app.test_client()

    add_response = client.post("/api/add_tool_name", json={"name": "Wrench"})
    assert add_response.status_code == 200
    assert "Wrench" in server_module.db.tool_names

    delete_response = client.post("/api/delete_tool_name", json={"name": "Wrench"})
    assert delete_response.status_code == 200
    assert "Wrench" not in server_module.db.tool_names


def test_delete_tool_name_conflict(server_module):
    db = server_module.db
    db.tools["tool-5"] = "Hammer"
    client = server_module.module.app.test_client()
    client.post("/api/add_tool_name", json={"name": "Hammer"})

    conflict_response = client.post("/api/delete_tool_name", json={"name": "Hammer"})
    assert conflict_response.status_code == 409


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


def test_get_production_plan(server_module, tmp_path):
    plan_dir = server_module.module.PLAN_DATA_DIR
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_csv = plan_dir / "production_plan.csv"
    plan_csv.write_text(
        "納期,個数,部品番号,部品名,製番,工程名\n2025-01-01,10,PART-1,部品A,JOB-1,切削\n",
        encoding="utf-8",
    )

    client = server_module.module.app.test_client()
    response = client.get("/api/v1/production-plan")
    body = response.get_json()

    assert response.status_code == 200
    assert body["entries"][0]["部品番号"] == "PART-1"
    assert body["updated_at"].endswith("Z")


def test_get_standard_times(server_module):
    plan_dir = server_module.module.PLAN_DATA_DIR
    plan_dir.mkdir(parents=True, exist_ok=True)
    csv_path = plan_dir / "standard_times.csv"
    csv_path.write_text(
        "部品名,機械標準工数,製造オーダー番号,部品番号,工程名\n部品A,12.3,ORDER-1,PART-1,切削\n",
        encoding="utf-8",
    )

    client = server_module.module.app.test_client()
    response = client.get("/api/v1/standard-times")
    body = response.get_json()

    assert response.status_code == 200
    assert body["entries"][0]["製造オーダー番号"] == "ORDER-1"


def test_station_config_get_and_post(server_module):
    client = server_module.module.app.test_client()

    # default (no file)
    response = client.get("/api/v1/station-config")
    assert response.status_code == 200
    assert response.get_json()["available"] == []

    payload = {"process": "切削", "available": ["切削", "研磨"]}
    post_response = client.post("/api/v1/station-config", json=payload)
    body = post_response.get_json()

    assert post_response.status_code == 200
    assert body["process"] == "切削"
    assert body["available"] == ["切削", "研磨"]
    assert body["updated_at"].endswith("Z")


def test_part_locations_endpoint(server_module):
    client = server_module.module.app.test_client()
    client.post(
        "/api/v1/scans",
        json={"part_code": "ABC", "location_code": "RACK-1"},
    )

    response = client.get("/api/v1/part-locations?limit=5")
    assert response.status_code == 200
    data = response.get_json()
    assert data["entries"][0]["order_code"] == "ABC"
