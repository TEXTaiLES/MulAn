from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .api.internal import internal_api
from .api.public import public_api
from .errors import ApiError
from .storage.filesystem import FileStore


def create_app(test_config: dict | None = None) -> Flask:
    static_dir = Path(__file__).resolve().parent / "static"
    # Vite emits files under static/assets and references them as /assets/*.
    # The explicit SPA/static handler below serves that exact tree; Flask's
    # automatic static route would otherwise look one directory too shallow.
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        MULAN_DATA_DIR=os.environ.get("MULAN_DATA_DIR", str(Path.cwd() / "data")),
        MULAN_RESOURCE_TTL_HOURS=float(os.environ.get("MULAN_RESOURCE_TTL_HOURS", "24")),
        MAX_CONTENT_LENGTH=int(os.environ.get("MULAN_MAX_UPLOAD_MB", "512")) * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    store = FileStore(Path(app.config["MULAN_DATA_DIR"]))
    store.initialize()
    store.cleanup_expired(float(app.config["MULAN_RESOURCE_TTL_HOURS"]))
    app.extensions["mulan_store"] = store

    app.register_blueprint(public_api, url_prefix="/api/v1")
    app.register_blueprint(internal_api, url_prefix="/api/internal/v1")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify(error.as_dict()), error.status

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error):
        return jsonify({"error": {"code": "upload_too_large", "message": "The upload exceeds the configured size limit.", "details": {}}}), 413

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        if error.code == 404 and not request.path.startswith("/api/"):
            return serve_spa("")
        return jsonify({"error": {"code": error.name.lower().replace(" ", "_"), "message": error.description, "details": {}}}), error.code

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception("Unhandled error", exc_info=error)
        return jsonify({"error": {"code": "internal_error", "message": "An unexpected server error occurred.", "details": {}}}), 500

    @app.get("/")
    @app.get("/<path:path>")
    def serve_spa(path: str = ""):
        if path.startswith("api/"):
            abort(404, description="API endpoint not found.")
        candidate = (static_dir / path).resolve()
        if path and static_dir in candidate.parents and candidate.is_file():
            return send_from_directory(static_dir, candidate.relative_to(static_dir).as_posix(), max_age=31536000 if path.startswith("assets/") else None)
        if path.startswith("assets/"):
            return "", 404
        index = static_dir / "index.html"
        if index.exists():
            return send_from_directory(static_dir, "index.html")
        return jsonify({"name": "MulAn", "message": "Frontend is not built. Run the Vite development server on port 5173."})

    return app
