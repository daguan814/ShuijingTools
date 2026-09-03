from flask import Blueprint, g, jsonify, request

from ..log_service import log_service
from ..recycle_service import recycle_service

recycle_bp = Blueprint("recycle", __name__, url_prefix="/api/recycle")


@recycle_bp.route("", methods=["GET"])
def list_recycle_items():
    return jsonify(recycle_service.list_items(g.current_user))


@recycle_bp.route("/<int:item_id>/restore", methods=["POST"])
def restore_recycle_item(item_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    try:
        restored_path = recycle_service.restore(
            g.current_user,
            item_id,
            payload.get("password", ""),
        )
    except PermissionError:
        return jsonify({"detail": "回收站密码错误。"}), 403
    except FileExistsError:
        return jsonify({"detail": "原位置已有同名文件或文件夹。"}), 409
    except FileNotFoundError:
        return jsonify({"detail": "回收站项目不存在。"}), 404
    except RuntimeError as exc:
        return jsonify({"detail": str(exc)}), 503

    log_service.add_log(g.current_user["id"], f"恢复：{restored_path}")
    return jsonify({"path": restored_path})
