from flask import Blueprint, g, jsonify, request

from ..log_service import log_service

logs_bp = Blueprint("logs", __name__, url_prefix="/api/logs")


@logs_bp.route("", methods=["GET"])
def list_logs():
    return jsonify(log_service.list_logs(g.current_user["id"]))


@logs_bp.route("", methods=["POST"])
def add_log():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    content = str(payload.get("content", "")).strip()
    if not content:
        return jsonify({"detail": "content is required"}), 400

    log_id = log_service.add_log(g.current_user["id"], content)
    return jsonify({"id": log_id}), 201


@logs_bp.route("/<int:log_id>", methods=["DELETE"])
def delete_log(log_id: int):
    deleted = log_service.delete_log(g.current_user["id"], log_id)
    if not deleted:
        return jsonify({"detail": "log not found"}), 404
    return "", 204
