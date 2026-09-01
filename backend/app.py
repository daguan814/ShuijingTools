import mimetypes
import os

from flask import Flask, g, jsonify, request, send_file
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import RequestEntityTooLarge

from .auth_service import auth_service
from .config import APP_HOST, APP_PORT, MAX_CONTENT_LENGTH, SECRET_KEY
from .database import db_manager
from .file_service import file_service
from .routes.auth import auth_bp
from .routes.files import files_bp


def _token_from_request():
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _add_cors_headers(response):
    origin = request.headers.get("Origin")
    response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Vary"] = "Origin"
    return response


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["SECRET_KEY"] = SECRET_KEY
    app.preview_serializer = URLSafeTimedSerializer(
        app.config["SECRET_KEY"],
        salt="shuijing-file-preview",
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)

    try:
        db_manager.init_db()
    except Exception as exc:
        print(f"Database initialization skipped: {exc}")

    @app.before_request
    def before_request():
        if request.method == "OPTIONS":
            response = app.response_class(status=204)
            return _add_cors_headers(response)

        if not request.path.startswith("/api"):
            return None

        if request.path in ("/api/health", "/api/auth/login"):
            return None

        token = _token_from_request()
        user = auth_service.get_user_by_token(token)
        if not user:
            return jsonify({"detail": "unauthorized"}), 401
        g.current_user = user
        return None

    @app.after_request
    def after_request(response):
        return _add_cors_headers(response)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error):
        return jsonify({"detail": "upload is too large"}), 413

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"detail": "not found"}), 404

    @app.errorhandler(500)
    def handle_server_error(_error):
        return jsonify({"detail": "internal server error"}), 500

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"ok": True})

    @app.route("/preview/<path:filepath>", methods=["GET"])
    def serve_preview(filepath: str):
        token = request.cookies.get("preview_session", "")
        if not token:
            return jsonify({"detail": "preview session missing"}), 401

        try:
            payload = app.preview_serializer.loads(token, max_age=3600)
        except (SignatureExpired, BadSignature):
            return jsonify({"detail": "preview session expired"}), 401

        user = db_manager.find_user_by_id(int(payload.get("user_id", 0)))
        if not user:
            return jsonify({"detail": "preview user not found"}), 401

        root_rel = file_service.normalize_relative_path(payload.get("root", ""))
        preview_rel = file_service.normalize_relative_path(filepath)
        full_rel = f"{root_rel}/{preview_rel}" if root_rel else preview_rel

        try:
            target = file_service.resolve_user_path(user, full_rel)
        except ValueError as exc:
            return jsonify({"detail": str(exc)}), 400

        if not target.exists() or not target.is_file():
            return jsonify({"detail": "file not found"}), 404

        mimetype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return send_file(target, as_attachment=False, mimetype=mimetype)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=APP_HOST,
        port=APP_PORT,
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        threaded=True,
    )
