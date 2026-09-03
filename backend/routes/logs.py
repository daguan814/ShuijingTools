from flask import Blueprint, g, jsonify

from ..log_service import log_service

logs_bp = Blueprint("logs", __name__, url_prefix="/api/logs")


@logs_bp.route("", methods=["GET"])
def list_logs():
    return jsonify(log_service.list_logs(g.current_user["id"]))
