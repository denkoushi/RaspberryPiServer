import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler
import psycopg
from flask import Flask, jsonify, request
from contextlib import contextmanager

from filelock import FileLock, Timeout
from werkzeug.exceptions import BadRequest, Conflict, ServiceUnavailable, Unauthorized
from flask_socketio import SocketIO

try:
    # When app/ is treated as a package (pytest, local scripts)
    from .document_viewer import document_viewer_bp  # type: ignore
    from .plan_cache import PlanCache  # type: ignore
except ImportError:
    # Docker runtime executes /app/server.py as a module
    from document_viewer import document_viewer_bp  # type: ignore
    from plan_cache import PlanCache  # type: ignore


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app:app_password@postgres:5432/appdb",
)
API_TOKEN = os.getenv("API_TOKEN", "")
SOCKETIO_CORS_ORIGINS = os.getenv("SOCKETIO_CORS_ORIGINS", "*")
socketio = SocketIO(cors_allowed_origins=SOCKETIO_CORS_ORIGINS, async_mode="gevent")

PLAN_DATA_DIR = Path(os.getenv("PLAN_DATA_DIR", "/srv/rpi-server/data/plan")).resolve()
STATION_CONFIG_PATH = Path(os.getenv("STATION_CONFIG_PATH", "/srv/rpi-server/config/station.json")).resolve()
LOGISTICS_DATA_PATH = Path(
    os.getenv("LOGISTICS_DATA_PATH", "/srv/rpi-server/data/logistics/jobs.json")
).resolve()
_default_lock_name = LOGISTICS_DATA_PATH.name + ".lock"
LOGISTICS_LOCK_PATH = Path(
    os.getenv("LOGISTICS_LOCK_PATH", str(LOGISTICS_DATA_PATH.parent / _default_lock_name))
).resolve()
LOGISTICS_LOCK_TIMEOUT = float(os.getenv("LOGISTICS_LOCK_TIMEOUT", "5"))
LOGISTICS_RETENTION_DAYS = int(os.getenv("LOGISTICS_RETENTION_DAYS", "30"))
LOGISTICS_MAX_JOBS = int(os.getenv("LOGISTICS_MAX_JOBS", "500"))
LOGISTICS_AUDIT_PATH = Path(
    os.getenv("LOGISTICS_AUDIT_PATH", "/srv/rpi-server/logs/logistics_audit.log")
).resolve()
_LOGISTICS_STATUSES_ENV = os.getenv(
    "LOGISTICS_ALLOWED_STATUSES", "pending,in_transit,completed,cancelled"
)
LOGISTICS_ALLOWED_STATUSES = {
    item.strip().lower() for item in _LOGISTICS_STATUSES_ENV.split(",") if item.strip()
}
if not LOGISTICS_ALLOWED_STATUSES:
    LOGISTICS_ALLOWED_STATUSES = {"pending", "in_transit", "completed", "cancelled"}
LOGISTICS_TERMINAL_STATUSES = {"completed", "cancelled"}
_LOGISTICS_AUDIT_LOGGER = None

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

_plan_cache = PlanCache(PLAN_DATA_DIR, PLAN_DATASETS)


@contextmanager
def _lock_logistics_store():
    LOGISTICS_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(LOGISTICS_LOCK_PATH), timeout=LOGISTICS_LOCK_TIMEOUT)
    try:
        with lock:
            yield
    except Timeout as exc:
        logging.getLogger(__name__).warning("Failed to acquire logistics lock: %s", exc)
        raise ServiceUnavailable("logistics_store_locked") from exc


def _ensure_logistics_store_locked() -> None:
    LOGISTICS_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOGISTICS_DATA_PATH.exists():
        LOGISTICS_DATA_PATH.write_text("[]", encoding="utf-8")


def _ensure_logistics_store() -> None:
    with _lock_logistics_store():
        _ensure_logistics_store_locked()


def _read_logistics_jobs() -> list[dict[str, object]]:
    with _lock_logistics_store():
        _ensure_logistics_store_locked()
        try:
            data = json.loads(LOGISTICS_DATA_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            logging.getLogger(__name__).exception("Failed to parse logistics jobs JSON")
        return []


def _write_logistics_jobs(jobs: list[dict[str, object]]) -> None:
    trimmed = _prune_logistics_jobs(jobs)
    payload = json.dumps(trimmed, ensure_ascii=False, indent=2)
    tmp_path = LOGISTICS_DATA_PATH.with_suffix(".tmp")
    with _lock_logistics_store():
        _ensure_logistics_store_locked()
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(LOGISTICS_DATA_PATH)


def _generate_logistics_job_id() -> str:
    now = datetime.now(timezone.utc)
    return "job-" + now.strftime("%Y%m%d%H%M%S%f")


def _parse_logistics_timestamp(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _prune_logistics_jobs(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    if not isinstance(jobs, list):
        return []

    retention_cutoff = None
    if LOGISTICS_RETENTION_DAYS > 0:
        retention_cutoff = datetime.now(timezone.utc) - timedelta(days=LOGISTICS_RETENTION_DAYS)

    filtered: list[dict[str, object]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        timestamp = (
            _parse_logistics_timestamp(job.get("updated_at"))
            or _parse_logistics_timestamp(job.get("requested_at"))
        )
        if retention_cutoff and timestamp and timestamp < retention_cutoff:
            continue
        filtered.append(job)

    filtered.sort(
        key=lambda item: (
            _parse_logistics_timestamp(item.get("updated_at"))
            or _parse_logistics_timestamp(item.get("requested_at"))
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )

    if LOGISTICS_MAX_JOBS > 0:
        return filtered[: LOGISTICS_MAX_JOBS]
    return filtered


def _normalize_logistics_status(value: str) -> str:
    return value.strip().lower()


def _validate_logistics_status(status: str) -> str:
    if not status:
        raise BadRequest("missing_status")
    normalized = _normalize_logistics_status(status)
    if normalized not in LOGISTICS_ALLOWED_STATUSES:
        raise BadRequest("invalid_status")
    return normalized


def _allowed_status_transitions(current_status: str) -> set[str]:
    base_map = {
        "pending": {"pending", "in_transit", "completed", "cancelled"},
        "in_transit": {"in_transit", "completed", "cancelled"},
        "completed": {"completed"},
        "cancelled": {"cancelled"},
    }
    allowed = base_map.get(current_status, {current_status})
    normalized = {_normalize_logistics_status(item) for item in allowed}
    filtered = normalized & LOGISTICS_ALLOWED_STATUSES
    return filtered or {current_status}


def _get_logistics_audit_logger() -> logging.Logger:
    global _LOGISTICS_AUDIT_LOGGER
    if _LOGISTICS_AUDIT_LOGGER is not None:
        return _LOGISTICS_AUDIT_LOGGER

    logger = logging.getLogger("logistics.audit")
    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - best effort
                pass

    LOGISTICS_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOGISTICS_AUDIT_PATH,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _LOGISTICS_AUDIT_LOGGER = logger
    return logger


def _log_logistics_event(event: str, job: dict, previous: dict | None = None, note: str | None = None) -> None:
    record = {
        "event": event,
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "part_code": job.get("part_code"),
        "from_location": job.get("from_location"),
        "to_location": job.get("to_location"),
        "updated_at": job.get("updated_at"),
    }
    if previous:
        record["previous_status"] = previous.get("status")
        record["previous_to_location"] = previous.get("to_location")
    if note:
        record["note"] = note

    logger = _get_logistics_audit_logger()
    logger.info(json.dumps(record, ensure_ascii=False))


def create_app() -> Flask:
    app = Flask(__name__)
    _configure_logging()
    _init_db()
    _ensure_logistics_store()
    app.register_blueprint(document_viewer_bp)
    socketio.init_app(app, cors_allowed_origins=SOCKETIO_CORS_ORIGINS)

    try:
        summary = _plan_cache.refresh()
        app.logger.info("Initial plan cache loaded: %s", summary)
    except Exception as exc:  # pylint: disable=broad-except
        app.logger.exception("Initial plan cache refresh failed: %s", exc)

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

    @app.get("/api/logistics/jobs")
    def get_logistics_jobs():
        _enforce_token()
        limit_arg = request.args.get("limit", default=None, type=str)
        try:
            limit_value = int(limit_arg) if limit_arg is not None else 100
        except ValueError:
            raise BadRequest("invalid_limit")
        limit_value = max(1, min(limit_value, 500))
        jobs = _read_logistics_jobs()
        jobs_sorted = sorted(
            jobs,
            key=lambda item: item.get("updated_at") or item.get("requested_at") or "",
            reverse=True,
        )
        return jsonify({"items": jobs_sorted[:limit_value]})

    @app.post("/api/logistics/jobs")
    def create_logistics_job():
        _enforce_token()
        payload = request.get_json(silent=True) or {}
        job_id = _get_str(payload, "job_id", default=None) or _generate_logistics_job_id()
        part_code = _get_str(payload, "part_code")
        from_location = _get_str(payload, "from_location")
        to_location = _get_str(payload, "to_location")
        status_raw = _get_str(payload, "status", default="pending") or "pending"
        requested_at = _get_str(payload, "requested_at", default=None)

        if not part_code:
            raise BadRequest("missing_part_code")
        if not from_location:
            raise BadRequest("missing_from_location")
        if not to_location:
            raise BadRequest("missing_to_location")
        status = _validate_logistics_status(status_raw)

        jobs = _read_logistics_jobs()
        now_iso = _to_utc_iso(datetime.now(timezone.utc))
        existing = None
        for index, job in enumerate(jobs):
            if job.get("job_id") == job_id:
                existing = (index, job)
                break

        base_requested = requested_at or (existing[1].get("requested_at") if existing else None) or now_iso
        previous = existing[1] if existing else None
        previous_status = previous.get("status") if previous else None
        if previous_status is not None:
            allowed = _allowed_status_transitions(previous_status)
            if status not in allowed:
                note = f"invalid_transition {previous_status}->{status}"
                _log_logistics_event(
                    "create_conflict",
                    {
                        "job_id": job_id,
                        "status": status,
                        "part_code": part_code,
                        "from_location": from_location,
                        "to_location": to_location,
                        "updated_at": now_iso,
                    },
                    previous=previous,
                    note=note,
                )
                return (
                    jsonify(
                        {
                            "error": "invalid_status_transition",
                            "current": previous_status,
                            "requested": status,
                        }
                    ),
                    409,
                )

        job_record = {
            "job_id": job_id,
            "part_code": part_code,
            "from_location": from_location,
            "to_location": to_location,
            "status": status,
            "requested_at": base_requested,
            "updated_at": now_iso,
        }

        if existing:
            jobs[existing[0]] = job_record
        else:
            jobs.append(job_record)

        _write_logistics_jobs(jobs)
        socketio.emit("logistics_job_updated", job_record, broadcast=True)
        _log_logistics_event("create" if not existing else "update", job_record, previous=previous)
        return jsonify(job_record), 201

    @app.post("/api/logistics/jobs/<job_id>/status")
    def update_logistics_job(job_id: str):
        _enforce_token()
        payload = request.get_json(silent=True) or {}
        status_raw = _get_str(payload, "status")
        from_location = _get_str(payload, "from_location", default=None)
        to_location = _get_str(payload, "to_location", default=None)

        if not status_raw:
            raise BadRequest("missing_status")
        status = _validate_logistics_status(status_raw)

        jobs = _read_logistics_jobs()
        updated = None
        now_iso = _to_utc_iso(datetime.now(timezone.utc))
        previous = None
        for index, job in enumerate(jobs):
            if job.get("job_id") == job_id:
                previous = dict(job)
                current_status = _normalize_logistics_status(job.get("status", ""))
                allowed = _allowed_status_transitions(current_status)
                if status not in allowed:
                    _log_logistics_event(
                        "status_transition_conflict",
                        {
                            "job_id": job_id,
                            "status": status,
                            "part_code": job.get("part_code"),
                            "from_location": from_location or job.get("from_location"),
                            "to_location": to_location or job.get("to_location"),
                            "updated_at": now_iso,
                        },
                        previous=job,
                    )
                    return (
                        jsonify(
                            {
                                "error": "invalid_status_transition",
                                "current": current_status,
                                "requested": status,
                            }
                        ),
                        409,
                    )
                if from_location:
                    job["from_location"] = from_location
                if to_location:
                    job["to_location"] = to_location
                job["status"] = status
                job["updated_at"] = now_iso
                jobs[index] = job
                updated = job
                break

        if not updated:
            _log_logistics_event(
                "update_not_found",
                {
                    "job_id": job_id,
                    "status": status,
                    "from_location": from_location,
                    "to_location": to_location,
                    "updated_at": now_iso,
                },
                note="job_not_found",
            )
            return jsonify({"error": "not_found"}), 404

        _write_logistics_jobs(jobs)
        socketio.emit("logistics_job_updated", updated, broadcast=True)
        _log_logistics_event("status_update", updated, previous=previous)
        return jsonify(updated)

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

    @app.post("/internal/plan-cache/refresh")
    def refresh_plan_cache():
        _enforce_token()
        try:
            summary = _plan_cache.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            app.logger.exception("Plan cache refresh failed: %s", exc)
            return jsonify({"status": "error", "error": str(exc)}), 500
        response = {
            "status": "ok",
            "refreshed": summary,
            "loaded_at": _plan_cache.loaded_at_iso(),
        }
        app.logger.info("Plan cache refreshed: %s", summary)
        return jsonify(response)

    return app


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _get_logistics_audit_logger()


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

    try:
        return _plan_cache.get_dataset(key)
    except KeyError as exc:
        raise BadRequest(str(exc)) from exc


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
