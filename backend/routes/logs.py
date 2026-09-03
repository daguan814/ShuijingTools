from datetime import datetime

from flask import Blueprint, g, jsonify, request

from ..log_service import log_service

logs_bp = Blueprint("logs", __name__, url_prefix="/api/logs")


@logs_bp.route("", methods=["GET"])
def list_logs():
    action = request.args.get("action", "all")
    day = request.args.get("date", "").strip()
    if action not in {"all", *log_service.ACTION_PREFIXES.keys()}:
        return jsonify({"detail": "invalid log action"}), 400
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(100, max(10, int(request.args.get("page_size", "20"))))
        if day:
            datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return jsonify({"detail": "invalid log query"}), 400

    return jsonify(
        log_service.list_logs(
            g.current_user["id"],
            action=None if action == "all" else action,
            day=day or None,
            page=page,
            page_size=page_size,
        )
    )
