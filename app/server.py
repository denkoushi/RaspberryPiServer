import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psycopg
from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, Unauthorized
from flask_socketio import SocketIO

try:
    # When app/ is treated as a package (pytest, local scripts)
    from .document_viewer import document_viewer_bp  # type: ignore
except ImportError:
    # Docker runtime executes /app/server.py as a module
    from document_viewer import document_viewer_bp  # type: ignore


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app:app_password@postgres:5432/appdb",
)
API_TOKEN = os.getenv("API_TOKEN", "")
SOCKETIO_CORS_ORIGINS = os.getenv("SOCKETIO_CORS_ORIGINS", "*")
socketio = SocketIO(cors_allowed_origins=SOCKETIO_CORS_ORIGINS, async_mode="gevent")

PLAN_DATA_DIR = Path(os.getenv("PLAN_DATA_DIR", "/srv/rpi-server/data/plan")).resolve()
STATION_CONFIG_PATH = Path(os.getenv("STATION_CONFIG_PATH", "/srv/rpi-server/config/station.json")).resolve()

PLAN_DATASETS = {
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


def create_app() -> Flask:
    app = Flask(__name__)
    _configure_logging()
    _init_db()
    app.register_blueprint(document_viewer_bp)
    socketio.init_app(app, cors_allowed_origins=SOCKETIO_CORS_ORIGINS)

    @app.get("/healthz")
    def healthz():
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
        except Exception as exc:  # pylint: disable=broad-except
            app.logger.exception("Health check failed: %s", exc)
            return jsonify({"status": "unhealthy"}), 500
        return jsonify({"status": "ok"})

    @app.post("/api/v1/scans")
    def create_scan():
        _enforce_token()
        payload = request.get_json(silent=True) or {}
        part_code = _get_str(payload, "part_code")
        location_code = _get_str(payload, "location_code")
        scan_id = _get_str(payload, "scan_id", default=None) or _generate_scan_id()
        device_id = _get_str(payload, "device_id", default=None)
        scanned_at_raw = payload.get("scanned_at")

        if not part_code or not location_code:
            raise BadRequest("missing_part_or_location")

        scanned_at = _parse_timestamp(scanned_at_raw) if scanned_at_raw else datetime.now(timezone.utc)

        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO part_locations (
                        order_code,
                        location_code,
                        device_id,
                        last_scan_id,
                        scanned_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (order_code)
                    DO UPDATE SET
                        location_code = EXCLUDED.location_code,
                        device_id = EXCLUDED.device_id,
                        last_scan_id = EXCLUDED.last_scan_id,
                        scanned_at = EXCLUDED.scanned_at,
                        updated_at = now()
                    RETURNING order_code, location_code, device_id, last_scan_id, scanned_at, updated_at
                    """,
                    (part_code, location_code, device_id, scan_id, scanned_at),
                )
                row = cur.fetchone()

        response = {
            "accepted": True,
            "order_code": row[0],
            "location_code": row[1],
            "device_id": row[2],
            "scan_id": row[3],
            "scanned_at": _to_utc_iso(row[4]),
            "updated_at": _to_utc_iso(row[5]),
        }
        socketio.emit("part_location_updated", response, broadcast=True)
        socketio.emit("scan_update", response, broadcast=True)
        return jsonify(response), 201

    @app.get("/api/v1/production-plan")
    def get_production_plan():
        _enforce_token()
        dataset = _load_plan_dataset("production_plan")
        status = 200 if dataset["error"] is None else 404
        return jsonify(dataset), status

    @app.get("/api/v1/standard-times")
    def get_standard_times():
        _enforce_token()
        dataset = _load_plan_dataset("standard_times")
        status = 200 if dataset["error"] is None else 404
        return jsonify(dataset), status

    @app.get("/api/v1/part-locations")
    def get_part_locations():
        _enforce_token()
        limit_arg = request.args.get("limit", default=None, type=str)
        try:
            limit_value = int(limit_arg) if limit_arg is not None else 200
        except ValueError:
            raise BadRequest("invalid_limit")
        entries = _fetch_part_locations(limit_value)
        return jsonify({"entries": entries})

    @app.get("/api/v1/station-config")
    def get_station_config():
        _enforce_token()
        config = _load_station_config()
        return jsonify(config)

    @app.post("/api/v1/station-config")
    def update_station_config():
        _enforce_token()
        payload = request.get_json(silent=True) or {}
        config = _validate_station_payload(payload)
        saved = _save_station_config(config)
        return jsonify(saved)

    return app


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _init_db() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS part_locations (
                    order_code TEXT PRIMARY KEY,
                    location_code TEXT NOT NULL,
                    device_id TEXT,
                    last_scan_id TEXT,
                    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )


def _load_plan_dataset(key: str) -> dict:
    if key not in PLAN_DATASETS:
        raise BadRequest("unknown_dataset")

    cfg = PLAN_DATASETS[key]
    path = PLAN_DATA_DIR / cfg["filename"]
    result = {
        "label": cfg["label"],
        "entries": [],
        "updated_at": None,
        "error": None,
    }

    if not path.exists():
        result["error"] = f"{cfg['label']} not found"
        return result

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            if headers != cfg["columns"]:
                result["error"] = f"unexpected columns: {headers}"
                return result
            for row in reader:
                normalized = {column: row.get(column, "") for column in cfg["columns"]}
                result["entries"].append(normalized)
        result["updated_at"] = _get_file_mtime(path)
    except Exception as exc:  # pylint: disable=broad-except
        result["error"] = f"failed to load dataset: {exc}"
    return result


def _get_file_mtime(path: Path) -> Optional[str]:
    try:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return _to_utc_iso(timestamp)
    except Exception:  # pylint: disable=broad-except
        return None


def _load_station_config() -> dict:
    if STATION_CONFIG_PATH.exists():
        try:
            data = json.loads(STATION_CONFIG_PATH.read_text(encoding="utf-8"))
            return {
                "process": _ensure_str(data.get("process")),
                "available": _ensure_str_list(data.get("available")),
                "updated_at": data.get("updated_at"),
            }
        except Exception:  # pylint: disable=broad-except
            pass
    return {"process": "", "available": [], "updated_at": None}


def _save_station_config(config: dict) -> dict:
    payload = {
        "process": _ensure_str(config.get("process")),
        "available": _ensure_str_list(config.get("available")),
        "updated_at": _to_utc_iso(datetime.now(timezone.utc)),
    }
    STATION_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATION_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _ensure_str(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BadRequest("invalid_station_process")
    return value.strip()


def _ensure_str_list(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise BadRequest("invalid_station_available")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise BadRequest("invalid_station_available")
        stripped = item.strip()
        if stripped:
            result.append(stripped)
    return result


def _validate_station_payload(payload: dict) -> dict:
    return {
        "process": payload.get("process", ""),
        "available": payload.get("available", []),
    }


def _fetch_part_locations(limit: int) -> list[dict[str, object]]:
    try:
        limit_value = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        raise BadRequest("invalid_limit")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT order_code, location_code, device_id, last_scan_id, scanned_at, updated_at
                FROM part_locations
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit_value,),
            )
            rows = cur.fetchall()

    results: list[dict[str, object]] = []
    for order_code, location_code, device_id, last_scan_id, scanned_at, updated_at in rows:
        results.append(
            {
                "order_code": order_code,
                "location_code": location_code,
                "device_id": device_id,
                "last_scan_id": last_scan_id,
                "scanned_at": _to_utc_iso(scanned_at),
                "updated_at": _to_utc_iso(updated_at),
            }
        )
    return results
def _parse_timestamp(value) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise BadRequest("invalid_scanned_at") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise BadRequest("invalid_scanned_at")


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_str(payload: dict, key: str, default=None) -> str:
    value = payload.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BadRequest(f"{key}_not_string")
    return value.strip()


def _generate_scan_id() -> str:
    return datetime.now(timezone.utc).strftime("scan-%Y%m%d%H%M%S%f")


def _enforce_token() -> None:
    if not API_TOKEN:
        return
    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        raise Unauthorized("missing_token")
    token = auth_header[len(prefix) :].strip()
    if token != API_TOKEN:
        raise Unauthorized("invalid_token")


app = create_app()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8501")))
