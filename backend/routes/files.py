import mimetypes
from urllib.parse import quote

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..file_service import file_service

files_bp = Blueprint("files", __name__, url_prefix="/api/files")


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
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    except OSError as exc:
        return jsonify({"detail": str(exc)}), 500

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
        file_service.delete(g.current_user, relative_path)
    except FileNotFoundError:
        return jsonify({"detail": "path not found"}), 404
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    return "", 204


@files_bp.route("/batch-delete", methods=["POST"])
def batch_delete():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    paths = payload.get("paths")
    if not isinstance(paths, list) or not paths:
        return jsonify({"detail": "paths must be a non-empty list"}), 400

    results = file_service.delete_paths(g.current_user, paths)
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

    return jsonify({"moved": moved})


@files_bp.route("/batch-download", methods=["POST"])
def batch_download():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    paths = payload.get("paths")
    base_path = str(payload.get("base", ""))
    if not isinstance(paths, list) or not paths:
        return jsonify({"detail": "paths must be a non-empty list"}), 400

    try:
        buffer = file_service.build_download_archive(
            g.current_user,
            paths,
            base_path,
        )
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    return send_file(
        buffer,
        as_attachment=True,
        download_name="selected_files.zip",
        mimetype="application/zip",
    )
