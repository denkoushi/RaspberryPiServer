from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    request,
    send_from_directory,
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


document_viewer_bp = Blueprint("document_viewer", __name__)


def _to_cache_busting_url(filename: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"/documents/{filename}?v={timestamp}"


def _find_document(part_number: str) -> Optional[str]:
    normalized = part_number.strip()
    if not normalized:
        return None

    direct = DOCUMENTS_ROOT / f"{normalized}.pdf"
    if direct.exists():
        return direct.name

    lower = normalized.lower()
    for candidate in DOCUMENTS_ROOT.glob("*.pdf"):
        if candidate.stem.lower() == lower:
            return candidate.name
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
        current_app.logger.info("Document not found: %s", part_number)
        return jsonify({"found": False, "message": "document not found"}), 404

    current_app.logger.info("Document lookup success: %s -> %s", part_number, filename)
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
        abort(404)
    return send_from_directory(DOCUMENTS_ROOT, filename, mimetype="application/pdf")
