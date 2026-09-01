from flask import Blueprint, g, jsonify, request

from ..auth_service import auth_service

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    username = str(payload.get("username", "")).strip()
    if not username:
        return jsonify({"detail": "username is required"}), 400

    user = auth_service.login(username)
    if not user:
        return jsonify({"detail": "user not found"}), 404

    token = auth_service.create_session(user["id"])
    return jsonify({"token": token, "user": auth_service.public_user(user)})


@auth_bp.route("/me", methods=["GET"])
def me():
    return jsonify({"user": auth_service.public_user(g.current_user)})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        auth_service.revoke_session(authorization[7:].strip())
    return "", 204
