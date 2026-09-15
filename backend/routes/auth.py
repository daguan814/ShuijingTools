import hashlib
import re
import uuid

from flask import Blueprint, current_app, g, jsonify, make_response, request, send_file
from itsdangerous import BadSignature, SignatureExpired
from urllib.parse import quote

from ..config import SECRET_KEY

from ..auth_service import auth_service
from ..file_service import file_service
from ..school_service import school_service
from ..admin_file_service import admin_file_service
from ..log_service import log_service
from pathlib import Path
import tempfile
import zipfile

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _login_device():
    device_id = request.cookies.get("login_device", "")
    if not re.fullmatch(r"[0-9a-f]{64}", device_id):
        device_id = uuid.uuid4().hex + uuid.uuid4().hex
    device_key = hashlib.sha256(f"{SECRET_KEY}:{device_id}".encode()).hexdigest()
    return device_id, device_key


def _login_response(payload, status, device_id):
    response = make_response(jsonify(payload), status)
    response.set_cookie(
        "login_device",
        device_id,
        max_age=365 * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return response


@auth_bp.route("/login", methods=["POST"])
def login():
    device_id, device_key = _login_device()
    attempt = auth_service.login_attempt_status(device_key)
    if attempt["blocked"]:
        blocked_until = attempt["blocked_until"]
        return _login_response(
            {
                "detail": "登录尝试次数过多，请在5小时后重试。",
                "blocked_until": blocked_until.isoformat(timespec="seconds"),
            },
            429,
            device_id,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _login_response({"detail": "invalid json"}, 400, device_id)

    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    class_id = payload.get("class_id")
    if not username or not password or not class_id:
        return _login_response({"detail": "班级、姓名和密码均为必填项"}, 400, device_id)

    user = auth_service.login(class_id, username, password)
    if not user:
        attempt = auth_service.record_login_failure(device_key)
        if attempt["blocked"]:
            return _login_response(
                {
                    "detail": "已连续失败5次，当前浏览器已锁定5小时。",
                    "blocked_until": attempt["blocked_until"].isoformat(timespec="seconds"),
                },
                429,
                device_id,
            )
        remaining = auth_service.MAX_LOGIN_FAILURES - attempt["failed_count"]
        return _login_response(
            {"detail": f"班级、姓名或密码错误，还可尝试 {remaining} 次。"},
            404,
            device_id,
        )

    auth_service.clear_login_failures(device_key)
    token = auth_service.create_session(user["id"])
    return _login_response(
        {"token": token, "user": auth_service.public_user(user)},
        200,
        device_id,
    )


@auth_bp.route("/me", methods=["GET"])
def me():
    user = auth_service.public_user(g.current_user)
    user["storage"] = file_service.storage_usage(g.current_user)
    return jsonify({"user": user})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        auth_service.revoke_session(authorization[7:].strip())
    return "", 204


@auth_bp.get("/classes")
def classes():
    return jsonify({"classes": school_service.classes()})


@auth_bp.post("/register")
def register():
    payload=request.get_json(silent=True) or {}; password=str(payload.get("password",""))
    if password != str(payload.get("confirm_password","")): return jsonify({"detail":"两次密码不一致"}),400
    try: request_id=school_service.register(payload.get("class_id"),payload.get("username"),password)
    except FileExistsError as exc: return jsonify({"detail":str(exc)}),409
    except (ValueError,TypeError) as exc: return jsonify({"detail":str(exc)}),400
    return jsonify({"id":request_id,"detail":"注册申请已提交，请等待管理员审核"}),201


@auth_bp.get("/announcements")
def announcements():
    return jsonify({"items":school_service.announcements_for(g.current_user["class_id"])})


@auth_bp.get("/shared-files")
def shared_files():
    return jsonify({"items": admin_file_service.shared_for_user(g.current_user["class_id"])})


@auth_bp.get("/shared-files/<int:share_id>/download")
def shared_download(share_id):
    try:
        target = admin_file_service.shared_target(share_id, g.current_user["class_id"])
        if target.is_file():
            log_service.add_log(g.current_user["id"], f"下载管理员共享文件：{target.name}")
            return send_file(target, as_attachment=True, download_name=target.name)
        temp = tempfile.NamedTemporaryFile(prefix="shuijing-shared-", suffix=".zip", delete=False)
        archive = Path(temp.name); temp.close()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for child in target.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    output.write(child, arcname=str(Path(target.name) / child.relative_to(target)))
        log_service.add_log(g.current_user["id"], f"下载管理员共享文件夹：{target.name}")
        response = send_file(archive, as_attachment=True, download_name=f"{target.name}.zip")
        response.call_on_close(lambda: archive.unlink(missing_ok=True)); return response
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 404


@auth_bp.get("/shared-files/<int:share_id>")
def shared_folder_entries(share_id):
    try:
        return jsonify(admin_file_service.shared_entries(share_id, g.current_user["class_id"], request.args.get("path", "")))
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"detail": str(exc)}), 404


@auth_bp.post("/shared-files/<int:share_id>/download/prepare")
def prepare_shared_download(share_id):
    """Create a short-lived browser-download URL after checking the user session."""
    try:
        path = request.args.get("path", "")
        admin_file_service.shared_target(share_id, g.current_user["class_id"], path)
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 404
    ticket = current_app.download_serializer.dumps(
        {
            "kind": "shared",
            "user_id": int(g.current_user["id"]),
            "class_id": int(g.current_user["class_id"]),
            "share_id": share_id,
            "path": path,
        }
    )
    return jsonify({"url": f"/api/auth/shared-files/download/ticket/{quote(ticket)}"})


@auth_bp.get("/shared-files/download/ticket/<path:ticket>")
def shared_download_with_ticket(ticket):
    try:
        payload = current_app.download_serializer.loads(ticket, max_age=300)
        if payload.get("kind") != "shared":
            raise ValueError("invalid ticket")
        user_id = int(payload["user_id"])
        class_id = int(payload["class_id"])
        share_id = int(payload["share_id"])
        target = admin_file_service.shared_target(share_id, class_id, payload.get("path", ""))
        if target.is_file():
            log_service.add_log(user_id, f"下载管理员共享文件：{target.name}")
            return send_file(target, as_attachment=True, download_name=target.name, conditional=True)
        temp = tempfile.NamedTemporaryFile(prefix="shuijing-shared-", suffix=".zip", delete=False)
        archive = Path(temp.name)
        temp.close()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for child in target.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    output.write(child, arcname=str(Path(target.name) / child.relative_to(target)))
        log_service.add_log(user_id, f"下载管理员共享文件夹：{target.name}")
        response = send_file(archive, as_attachment=True, download_name=f"{target.name}.zip", conditional=True)
        response.call_on_close(lambda: archive.unlink(missing_ok=True))
        return response
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return jsonify({"detail": "download link expired or invalid"}), 401
    except FileNotFoundError:
        return jsonify({"detail": "file not found"}), 404
    except Exception:
        current_app.logger.exception("Shared file download failed")
        return jsonify({"detail": "download failed"}), 500


@auth_bp.post("/reports")
def report():
    try: school_service.add_report(g.current_user["id"],(request.get_json(silent=True) or {}).get("content"))
    except ValueError as exc: return jsonify({"detail":str(exc)}),400
    return "",204
