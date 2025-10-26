import importlib
import sys
from types import SimpleNamespace

import pytest
from flask import Flask


@pytest.fixture
def viewer_module(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    sample_pdf = docs_dir / "TestPart.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n%Test Document\n")

    monkeypatch.setenv("VIEWER_DOCS_DIR", str(docs_dir))
    monkeypatch.setenv("VIEWER_CORS_ORIGINS", "http://example.com")
    monkeypatch.delenv("VIEWER_API_TOKEN", raising=False)

    sys.modules.pop("app.document_viewer", None)
    module = importlib.import_module("app.document_viewer")
    module = importlib.reload(module)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(module.document_viewer_bp)

    return SimpleNamespace(module=module, app=app, pdf=sample_pdf)


def test_get_document_success(viewer_module):
    client = viewer_module.app.test_client()
    response = client.get("/api/documents/TestPart")
    body = response.get_json()

    assert response.status_code == 200
    assert body["found"] is True
    assert body["filename"] == viewer_module.pdf.name
    assert body["url"].startswith("/documents/")
    assert response.headers["Access-Control-Allow-Origin"] == "http://example.com"


def test_get_document_case_insensitive(viewer_module):
    client = viewer_module.app.test_client()
    response = client.get("/api/documents/testpart")
    assert response.status_code == 200
    assert response.get_json()["found"] is True


def test_get_document_trims_whitespace(viewer_module):
    client = viewer_module.app.test_client()
    response = client.get("/api/documents/%20TestPart%20")
    assert response.status_code == 200
    assert response.get_json()["found"] is True


def test_get_document_not_found(viewer_module):
    client = viewer_module.app.test_client()
    response = client.get("/api/documents/unknown")

    assert response.status_code == 404
    assert response.get_json()["found"] is False


def test_get_document_requires_token(viewer_module, monkeypatch):
    monkeypatch.setenv("VIEWER_API_TOKEN", "secret-token")
    sys.modules.pop("app.document_viewer", None)
    module = importlib.import_module("app.document_viewer")
    module = importlib.reload(module)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(module.document_viewer_bp)
    client = app.test_client()

    missing = client.get("/api/documents/TestPart")
    assert missing.status_code == 401

    ok = client.get(
        "/api/documents/TestPart",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert ok.status_code == 200


def test_serve_document_returns_file(viewer_module):
    client = viewer_module.app.test_client()
    response = client.get(f"/documents/{viewer_module.pdf.name}")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-1.4")


def test_serve_document_rejects_traversal(viewer_module):
    client = viewer_module.app.test_client()
    response = client.get("/documents/../../etc/passwd")
    assert response.status_code == 404


def test_options_request_returns_cors_headers(viewer_module):
    client = viewer_module.app.test_client()
    response = client.options("/api/documents/TestPart")

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "http://example.com"
    assert response.headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type"
    assert response.headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"
