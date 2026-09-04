import os
import mimetypes
from urllib.parse import quote

from flask import Blueprint, after_this_request, current_app, g, jsonify, request, send_file
from itsdangerous import BadSignature, SignatureExpired

from ..file_service import file_service
from ..log_service import log_service
from ..recycle_service import recycle_service

files_bp = Blueprint("files", __name__, url_prefix="/api/files")


def _summarize_paths(paths, limit=6):
    clean = [str(path) for path in paths if path]
    shown = "、".join(clean[:limit])
    if len(clean) > limit:
        shown += f" 等（共 {len(clean)} 项）"
    return shown


def _record_action(user_id, action, detail):
    try:
        log_service.add_log(user_id, f"{action}：{detail}")
    except Exception:
        current_app.logger.exception("Failed to record user file operation")


@files_bp.route("", methods=["GET"])
def list_files():
    relative_path = request.args.get("path", "")
    try:
        entries = file_service.list_entries(g.current_user, relative_path)
    except FileNotFoundError:
        return jsonify({"detail": "directory not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    return jsonify(
        {
            "path": file_service.normalize_relative_path(relative_path),
            "entries": entries,
        }
    )


@files_bp.route("/upload", methods=["POST"])
def upload_files():
    parent_path = request.form.get("path", "")
    files = request.files.getlist("files")
    relative_paths = request.form.getlist("relative_paths")

    if not files:
        return jsonify({"detail": "no files received"}), 400
    if len(relative_paths) != len(files):
        return jsonify({"detail": "relative_paths count does not match files"}), 400

    uploaded = []
    uploaded_relative_paths = []
    try:
        for file_storage, relative_name in zip(files, relative_paths):
            if not file_storage or not file_storage.filename:
                continue
            if not relative_name:
                relative_name = file_storage.filename
            uploaded.append(
                file_service.upload_file(
                    g.current_user,
                    parent_path,
                    relative_name,
                    file_storage,
                )
            )
            uploaded_relative_paths.append(str(relative_name).replace("\\", "/"))
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    except OSError as exc:
        return jsonify({"detail": str(exc)}), 500

    folder_roots = sorted(
        {path.split("/", 1)[0] for path in uploaded_relative_paths if "/" in path}
    )
    direct_files = [
        item["path"]
        for item, source in zip(uploaded, uploaded_relative_paths)
        if "/" not in source
    ]
    if direct_files:
        _record_action(g.current_user["id"], "上传文件", _summarize_paths(direct_files))
    for folder in folder_roots:
        count = sum(
            1
            for path in uploaded_relative_paths
            if path == folder or path.startswith(f"{folder}/")
        )
        folder_path = "/".join(
            part
            for part in (file_service.normalize_relative_path(parent_path), folder)
            if part
        )
        _record_action(
            g.current_user["id"],
            "上传文件夹",
            f"{folder_path}（{count} 个文件）",
        )

    return jsonify({"uploaded": uploaded})


@files_bp.route("/mkdir", methods=["POST"])
def make_directory():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    parent_path = str(payload.get("path", ""))
    name = str(payload.get("name", ""))
    try:
        created_path = file_service.create_folder(g.current_user, parent_path, name)
    except FileExistsError:
        return jsonify({"detail": "folder already exists"}), 409
    except FileNotFoundError:
        return jsonify({"detail": "parent directory not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    _record_action(g.current_user["id"], "新建文件夹", created_path)
    return jsonify({"path": created_path}), 201


@files_bp.route("/download", methods=["GET"])
def download_file():
    relative_path = request.args.get("path", "")
    try:
        target = file_service.download_target(g.current_user, relative_path)
    except FileNotFoundError:
        return jsonify({"detail": "file not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    _record_action(g.current_user["id"], "下载文件", relative_path)
    return send_file(target, as_attachment=True, download_name=target.name)


@files_bp.route("/preview", methods=["GET"])
def preview_file():
    relative_path = request.args.get("path", "")
    try:
        target = file_service.download_target(g.current_user, relative_path)
    except FileNotFoundError:
        return jsonify({"detail": "file not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    mimetype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return send_file(
        target,
        as_attachment=False,
        download_name=target.name,
        mimetype=mimetype,
    )


@files_bp.route("/preview/start", methods=["POST"])
def start_preview():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    relative_path = str(payload.get("path", ""))
    try:
        target = file_service.download_target(g.current_user, relative_path)
    except FileNotFoundError:
        return jsonify({"detail": "file not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    normalized = file_service.normalize_relative_path(relative_path)
    parent = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
    preview_name = normalized.rsplit("/", 1)[-1]
    preview_token = current_app.preview_serializer.dumps(
        {
            "user_id": int(g.current_user["id"]),
            "root": parent,
        }
    )

    response = jsonify({"url": f"/preview/{quote(preview_name)}"})
    response.set_cookie(
        "preview_session",
        preview_token,
        max_age=3600,
        path="/preview",
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return response


@files_bp.route("/delete", methods=["POST"])
def delete_path():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        relative_path = str(payload.get("path", ""))
    else:
        relative_path = request.form.get("path", "")

    try:
        recycled = recycle_service.move_to_recycle(g.current_user, relative_path)
    except FileNotFoundError:
        return jsonify({"detail": "path not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    target_type = "文件夹" if recycled["type"] == "folder" else "文件"
    _record_action(
        g.current_user["id"],
        f"删除{target_type}（移入回收站）",
        recycled["path"],
    )
    return "", 204


@files_bp.route("/batch-delete", methods=["POST"])
def batch_delete():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    paths = payload.get("paths")
    if not isinstance(paths, list) or not paths:
        return jsonify({"detail": "paths must be a non-empty list"}), 400

    results = []
    for raw_path in paths:
        try:
            recycled = recycle_service.move_to_recycle(g.current_user, str(raw_path))
            results.append({"path": recycled["path"], "deleted": True})
            target_type = "文件夹" if recycled["type"] == "folder" else "文件"
            _record_action(
                g.current_user["id"],
                f"删除{target_type}（移入回收站）",
                recycled["path"],
            )
        except (FileNotFoundError, ValueError) as exc:
            results.append(
                {"path": str(raw_path), "deleted": False, "error": str(exc)}
            )
    return jsonify({"results": results})


@files_bp.route("/move", methods=["POST"])
def move_paths():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    paths = payload.get("paths")
    destination = str(payload.get("destination", ""))
    if not isinstance(paths, list) or not paths:
        return jsonify({"detail": "paths must be a non-empty list"}), 400
    if not destination:
        return jsonify({"detail": "destination is required"}), 400

    try:
        moved = file_service.move_paths(g.current_user, paths, destination)
    except FileExistsError as exc:
        return jsonify({"detail": str(exc)}), 409
    except FileNotFoundError:
        return jsonify({"detail": "destination or source not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    for item in moved:
        _record_action(
            g.current_user["id"],
            "移动",
            f"{item['path']} → {item['target']}",
        )
    return jsonify({"moved": moved})


@files_bp.route("/rename", methods=["POST"])
def rename_path():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    try:
        renamed = file_service.rename_path(
            g.current_user,
            str(payload.get("path", "")),
            str(payload.get("name", "")),
        )
    except FileExistsError:
        return jsonify({"detail": "同名文件或文件夹已存在"}), 409
    except FileNotFoundError:
        return jsonify({"detail": "path not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    if renamed["path"] != renamed["target"]:
        target_type = "文件夹" if renamed["type"] == "folder" else "文件"
        _record_action(
            g.current_user["id"],
            f"重命名{target_type}",
            f"{renamed['path']} → {renamed['target']}",
        )
    return jsonify(renamed)


@files_bp.route("/download/prepare", methods=["POST"])
def prepare_download():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    paths = payload.get("paths")
    base_path = str(payload.get("base", ""))
    if not isinstance(paths, list) or not paths:
        return jsonify({"detail": "paths must be a non-empty list"}), 400

    normalized = []
    try:
        for path in paths:
            rel = file_service.normalize_relative_path(path)
            if not rel:
                raise ValueError("cannot download user root")
            target = file_service.resolve_user_path(g.current_user, rel)
            if not target.exists():
                raise FileNotFoundError(rel)
            normalized.append(rel)
    except FileNotFoundError:
        return jsonify({"detail": "file not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    ticket = current_app.download_serializer.dumps(
        {"user_id": int(g.current_user["id"]), "paths": normalized, "base": base_path}
    )
    return jsonify({"url": f"/api/files/download/ticket/{quote(ticket)}"})


@files_bp.route("/download/ticket/<path:ticket>", methods=["GET"])
def download_with_ticket(ticket: str):
    try:
        payload = current_app.download_serializer.loads(ticket, max_age=300)
    except (SignatureExpired, BadSignature):
        return jsonify({"detail": "download link expired"}), 401

    from ..database import db_manager

    user = db_manager.find_user_by_id(int(payload.get("user_id", 0)))
    paths = payload.get("paths")
    if not user or not isinstance(paths, list) or not paths:
        return jsonify({"detail": "invalid download link"}), 400

    try:
        if len(paths) == 1:
            target = file_service.resolve_user_path(user, paths[0])
            if target.is_file():
                _record_action(user["id"], "下载文件", paths[0])
                return send_file(target, as_attachment=True, download_name=target.name, conditional=True)

        archive_path = file_service.build_download_archive(user, paths, str(payload.get("base", "")))
    except FileNotFoundError:
        return jsonify({"detail": "file not found"}), 404
    except (OSError, ValueError) as exc:
        return jsonify({"detail": str(exc)}), 400

    @after_this_request
    def remove_archive(response):
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        return response

    action = "下载文件夹" if len(paths) == 1 else "批量下载"
    _record_action(user["id"], action, _summarize_paths(paths))
    return send_file(archive_path, as_attachment=True, download_name="selected_files.zip", mimetype="application/zip", conditional=True)
