from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
    url_for,
)


def _get_docs_root() -> Path:
    root = Path(
        os.getenv(
            "VIEWER_DOCS_DIR",
            "/srv/rpi-server/documents",
        )
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


DOCUMENTS_ROOT = _get_docs_root()
VIEWER_API_TOKEN = os.getenv("VIEWER_API_TOKEN", "").strip()
VIEWER_CORS_ORIGINS = os.getenv("VIEWER_CORS_ORIGINS", "*").strip() or "*"
VIEWER_LOG_PATH_RAW = os.getenv(
    "VIEWER_LOG_PATH",
    "/srv/rpi-server/logs/document_viewer.log",
).strip()
VIEWER_LOG_PATH = None if not VIEWER_LOG_PATH_RAW else Path(VIEWER_LOG_PATH_RAW).resolve()


def _configure_logger() -> logging.Logger:
    logger = logging.getLogger("document_viewer")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        if getattr(handler, "_document_viewer_handler", False):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pylint: disable=broad-except
                pass

    if VIEWER_LOG_PATH is None:
        return logger

    try:
        VIEWER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return logger

    handler = RotatingFileHandler(
        VIEWER_LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler._document_viewer_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return logger


LOGGER = _configure_logger()


document_viewer_bp = Blueprint("document_viewer", __name__)


def _log_info(message: str, *args) -> None:
    LOGGER.info(message, *args)
    current_app.logger.info(message, *args)


def _log_warning(message: str, *args) -> None:
    LOGGER.warning(message, *args)
    current_app.logger.warning(message, *args)


def _to_cache_busting_url(filename: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"/documents/{filename}?v={timestamp}"


def _find_document(part_number: str) -> Optional[str]:
    normalized = part_number.strip()
    if not normalized:
        return None

    lower = normalized.lower()
    for candidate in DOCUMENTS_ROOT.glob("*.pdf"):
        if candidate.stem.lower() == lower:
            return candidate.name

    direct = DOCUMENTS_ROOT / f"{normalized}.pdf"
    if direct.exists():
        return direct.name
    return None


def _enforce_token() -> None:
    if not VIEWER_API_TOKEN:
        return
    prefix = "Bearer "
    header = request.headers.get("Authorization", "")
    if not header.startswith(prefix):
        abort(401, description="missing_token")
    token = header[len(prefix) :].strip()
    if token != VIEWER_API_TOKEN:
        abort(401, description="invalid_token")


@document_viewer_bp.after_request
def add_cors_headers(response):
    if VIEWER_CORS_ORIGINS == "*":
        response.headers["Access-Control-Allow-Origin"] = "*"
    else:
        response.headers["Access-Control-Allow-Origin"] = VIEWER_CORS_ORIGINS
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


@document_viewer_bp.route("/api/documents/<path:part_number>", methods=["GET", "OPTIONS"])
def get_document(part_number: str):
    if request.method == "OPTIONS":
        return ("", 204)

    _enforce_token()

    filename = _find_document(part_number)
    if not filename:
        _log_info("Document not found: %s", part_number)
        return jsonify({"found": False, "message": "document not found"}), 404

    _log_info("Document lookup success: %s -> %s", part_number, filename)
    url = _to_cache_busting_url(filename)
    return jsonify(
        {
            "found": True,
            "partNumber": part_number,
            "filename": filename,
            "url": url,
        }
    )


@document_viewer_bp.route("/documents/<path:filename>")
def serve_document(filename: str):
    safe_path = (DOCUMENTS_ROOT / filename).resolve()
    if not safe_path.is_file() or DOCUMENTS_ROOT not in safe_path.parents:
        _log_warning("Invalid document access attempt: %s", filename)
        abort(404)
    return send_from_directory(DOCUMENTS_ROOT, filename, mimetype="application/pdf")


@document_viewer_bp.route("/viewer")
def viewer_page():
    """
    Render a lightweight DocumentViewer UI that runs directly on RaspberryPiServer.
    既存の Window A 依存をなくし、サーバー単体で PDF を配信・表示できるようにする。
    """
    api_sample = url_for("document_viewer.get_document", part_number="__sample__", _external=True)
    docs_sample = url_for("document_viewer.serve_document", filename="__sample__.pdf", _external=True)
    config = {
        "api_base": api_sample.rsplit("/", 1)[0],
        "docs_base": docs_sample.rsplit("/", 1)[0],
        "socket_base": request.url_root.rstrip("/"),
        "socket_path": "/socket.io",
        "api_token": VIEWER_API_TOKEN,
    }
    return render_template("document_viewer/viewer.html", config=config)


@document_viewer_bp.route("/viewer/health")
def viewer_health():
    """
    Health endpoint used by Window A UI to確認 DocumentViewer service availability.
    """
    return jsonify({"status": "ok", "docs_root": str(DOCUMENTS_ROOT)})
