import logging
import os
from datetime import datetime, timezone

import psycopg
from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, Unauthorized


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app:app_password@postgres:5432/appdb",
)
API_TOKEN = os.getenv("API_TOKEN", "")


def create_app() -> Flask:
    app = Flask(__name__)
    _configure_logging()
    _init_db()

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
        return jsonify(response), 201

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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8501")))
