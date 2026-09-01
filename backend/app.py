import os

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from .auth_service import auth_service
from .config import APP_HOST, APP_PORT, MAX_CONTENT_LENGTH
from .database import db_manager
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

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=APP_HOST,
        port=APP_PORT,
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        threaded=True,
    )
