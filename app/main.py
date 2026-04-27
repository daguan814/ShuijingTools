import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from Controller.api_router import api_bp
from Service.auth_service import auth_service
from db.database import db_manager

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__, static_folder=None)
app.register_blueprint(api_bp)


@app.before_request
def api_auth_middleware():
    from flask import request

    path = request.path
    if path.startswith("/api") and path not in ("/api/health", "/api/auth/verify"):
        auth_header = (request.headers.get("Authorization", "") or "").strip()
        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        if not token or not auth_service.verify_session(token):
            return jsonify({"detail": "unauthorized"}), 401
    return None


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/<path:filepath>", methods=["GET"])
def frontend_assets(filepath: str):
    if filepath.startswith("api/"):
        return jsonify({"detail": "not found"}), 404
    target = FRONTEND_DIR / filepath
    if target.exists() and target.is_file():
        return send_from_directory(str(FRONTEND_DIR), filepath)
    return send_from_directory(str(FRONTEND_DIR), "index.html")


def create_app() -> Flask:
    db_manager.init_db()
    return app


if __name__ == "__main__":
    db_manager.init_db()
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8080"))
    cert = os.getenv("SSL_CERT_FILE", "")
    key = os.getenv("SSL_KEY_FILE", "")
    ssl_context = (cert, key) if cert and key else None
    app.run(host=host, port=port, ssl_context=ssl_context, threaded=True)
