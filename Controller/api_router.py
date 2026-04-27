import shutil
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from werkzeug.exceptions import BadRequest

from Service.auth_service import auth_service
from Service.file_favorite_service import file_favorite_service
from Service.text_service import text_service
from Service.trash_service import trash_service

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.errorhandler(BadRequest)
def handle_bad_request(err):
    return jsonify({'detail': str(err.description or 'bad request')}), 400


def get_client_ip() -> str:
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or ''


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            if unit == 'B':
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def safe_join_upload(rel_path: str) -> Path:
    rel = Path(str(rel_path).replace('\\', '/'))
    if rel.is_absolute():
        raise BadRequest('invalid path')
    target = (UPLOAD_DIR / rel).resolve()
    upload_resolved = UPLOAD_DIR.resolve()
    if upload_resolved not in target.parents and target != upload_resolved:
        raise BadRequest('invalid path')
    return target


def list_uploads():
    favorite_paths = {item['path'] for item in file_favorite_service.list_paths()}
    uploads = []
    for full_path in UPLOAD_DIR.glob('*'):
        if not full_path.is_file():
            continue
        uploads.append({
            'path': full_path.name,
            'size': format_size(full_path.stat().st_size),
            'mtime': full_path.stat().st_mtime,
            'is_favorite': full_path.name in favorite_paths,
        })
    uploads.sort(key=lambda item: item['mtime'], reverse=True)
    for item in uploads:
        item.pop('mtime', None)
    return uploads


@api_bp.route('/health', methods=['GET'])
def health():
    return jsonify({'ok': True})


@api_bp.route('/auth/verify', methods=['POST'])
def verify_auth():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'detail': 'invalid json'}), 400

    passcode = str(payload.get('passcode', '')).strip()
    if not passcode:
        return jsonify({'detail': 'passcode required'}), 400

    client_ip = get_client_ip()
    result = auth_service.verify_passcode_with_ip(passcode, client_ip)
    if result.get('banned'):
        return jsonify({'detail': 'ip banned 7 days'}), 403
    if not result.get('ok'):
        return jsonify({'detail': 'invalid passcode'}), 401

    token = auth_service.create_session(client_ip)
    return jsonify({'ok': True, 'token': token})


@api_bp.route('/texts', methods=['GET'])
def get_texts():
    texts = text_service.get_all_texts()
    return jsonify([
        {
            'id': text[0],
            'content': text[1],
            'created_at': text[2],
            'is_favorite': bool(text[3]),
            'favorite_group': int(text[4]),
        }
        for text in texts
    ])


@api_bp.route('/texts', methods=['POST'])
def add_text():
    content = (request.form.get('content', '') or '').strip()
    if not content:
        return jsonify({'detail': 'content is empty'}), 400

    text_id = text_service.add_text(content)
    text_service.add_log('text_add', text_id=text_id, content=content, client_ip=get_client_ip())
    return jsonify({'id': text_id})


@api_bp.route('/texts/<int:text_id>', methods=['DELETE'])
def delete_text(text_id: int):
    deleted = text_service.delete_text(text_id)
    if not deleted:
        return jsonify({'detail': 'text not found'}), 404
    text_service.add_log('text_delete', text_id=text_id, client_ip=get_client_ip())
    return jsonify({'ok': True})


@api_bp.route('/texts/<int:text_id>/favorite', methods=['POST'])
def toggle_favorite(text_id: int):
    favorited = text_service.toggle_favorite(text_id)
    if favorited is None:
        return jsonify({'detail': 'text not found'}), 404
    text_service.add_log(
        'text_favorite' if favorited else 'text_unfavorite',
        text_id=text_id,
        client_ip=get_client_ip(),
    )
    return jsonify({'id': text_id, 'is_favorite': favorited})


@api_bp.route('/favorites', methods=['GET'])
def get_favorites():
    favorites = text_service.get_favorite_texts()
    return jsonify([
        {
            'id': text[0],
            'content': text[1],
            'created_at': text[2],
            'is_favorite': bool(text[3]),
            'favorite_group': int(text[4]),
        }
        for text in favorites
    ])


@api_bp.route('/favorites/move', methods=['POST'])
def move_favorite():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'detail': 'invalid json'}), 400

    try:
        text_id = int(payload.get('id'))
        group_id = int(payload.get('group'))
    except (TypeError, ValueError):
        return jsonify({'detail': 'invalid params'}), 400

    moved = text_service.move_favorite_group(text_id, group_id)
    if moved is None:
        return jsonify({'detail': 'favorite not found'}), 404

    text_service.add_log(
        'text_favorite_move',
        text_id=text_id,
        content=f'group={group_id}',
        client_ip=get_client_ip(),
    )
    return jsonify({'id': text_id, 'group': group_id})


@api_bp.route('/files', methods=['GET'])
def get_files():
    return jsonify(list_uploads())


@api_bp.route('/files/favorites', methods=['GET'])
def get_file_favorites():
    files_by_path = {item['path']: item for item in list_uploads()}
    favorites = []
    for item in file_favorite_service.list_paths():
        file_item = files_by_path.get(item['path'])
        if file_item:
            favorites.append(file_item)
    return jsonify(favorites)


@api_bp.route('/files/favorite', methods=['POST'])
def set_file_favorite():
    path = request.form.get('path', '')
    enabled = str(request.form.get('enabled', 'true')).lower() != 'false'
    target = safe_join_upload(path)
    if not target.exists() or not target.is_file():
        file_favorite_service.remove(path)
        return jsonify({'detail': 'file not found'}), 404

    file_favorite_service.set_favorite(path, enabled)
    text_service.add_log(
        'file_favorite' if enabled else 'file_unfavorite',
        content=path,
        client_ip=get_client_ip(),
    )
    return jsonify({'path': path, 'is_favorite': enabled})


@api_bp.route('/files/upload', methods=['POST'])
def upload_files():
    files = request.files.getlist('files')
    for file_obj in files:
        if not file_obj or not file_obj.filename:
            continue
        target = safe_join_upload(file_obj.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_obj.save(target)
        text_service.add_log('file_upload', content=file_obj.filename, client_ip=get_client_ip())
    return '', 204


@api_bp.route('/files/download/<path:filepath>', methods=['GET'])
def download_file(filepath: str):
    target = safe_join_upload(filepath)
    if not target.exists() or not target.is_file():
        return jsonify({'detail': 'file not found'}), 404
    return send_file(target, as_attachment=True, download_name=target.name)


@api_bp.route('/files/delete', methods=['POST'])
def delete_file():
    path = request.form.get('path', '')
    target = safe_join_upload(path)
    if target.exists() and target.is_file():
        size_bytes = target.stat().st_size
        trash_dir = UPLOAD_DIR / '.trash'
        trash_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}_{target.name}"
        trash_rel = f".trash/{unique_name}"
        trash_path = safe_join_upload(trash_rel)
        shutil.move(str(target), str(trash_path))
        trash_service.add_file(path, trash_rel, size_bytes)
        file_favorite_service.remove(path)
        text_service.add_log('file_delete', content=path, client_ip=get_client_ip())
    return '', 204


@api_bp.route('/trash', methods=['GET'])
def get_trash():
    deleted_texts = text_service.get_deleted_texts()
    files = trash_service.list_files()

    texts_list = [
        {
            'id': text[0],
            'content': text[1],
            'created_at': text[2],
        }
        for text in deleted_texts
    ]

    file_list = [
        {
            'id': f['id'],
            'original_path': f['original_path'],
            'size': format_size(f['size']),
            'deleted_at': f['deleted_at'],
        }
        for f in files
    ]

    return jsonify({'texts': texts_list, 'files': file_list})


@api_bp.route('/trash/restore/text/<int:text_id>', methods=['POST'])
def restore_text(text_id: int):
    restored = text_service.restore_text(text_id)
    if not restored:
        return jsonify({'detail': 'text not found'}), 404
    text_service.add_log('text_restore', text_id=text_id, client_ip=get_client_ip())
    return '', 204


@api_bp.route('/trash/restore/file', methods=['POST'])
def restore_file():
    raw_id = request.form.get('id')
    try:
        file_id = int(raw_id)
    except (TypeError, ValueError):
        return jsonify({'detail': 'invalid id'}), 400

    file_row = trash_service.get_file(file_id)
    if not file_row:
        return jsonify({'detail': 'file not found'}), 404

    trash_path = safe_join_upload(file_row['trash_path'])
    if not trash_path.exists() or not trash_path.is_file():
        trash_service.remove_file(file_id)
        return jsonify({'detail': 'file data missing'}), 404

    restore_path = safe_join_upload(file_row['original_path'])
    restore_rel = file_row['original_path']

    if restore_path.exists():
        stem = restore_path.stem
        suffix = restore_path.suffix
        restore_rel = f"{stem}-restored-{file_id}{suffix}"
        restore_path = safe_join_upload(restore_rel)

    restore_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_path), str(restore_path))
    trash_service.remove_file(file_id)
    text_service.add_log('file_restore', content=restore_rel, client_ip=get_client_ip())
    return '', 204


@api_bp.route('/trash/text/<int:text_id>', methods=['DELETE'])
def delete_trash_text(text_id: int):
    deleted = text_service.purge_deleted_text(text_id)
    if not deleted:
        return jsonify({'detail': 'text not found'}), 404
    text_service.add_log('trash_delete_text', text_id=text_id, client_ip=get_client_ip())
    return '', 204


@api_bp.route('/trash/file/<int:file_id>', methods=['DELETE'])
def delete_trash_file(file_id: int):
    file_row = trash_service.get_file(file_id)
    if not file_row:
        return jsonify({'detail': 'file not found'}), 404

    trash_service.remove_file(file_id)
    text_service.add_log('trash_delete_file', content=file_row.get('original_path', ''), client_ip=get_client_ip())
    return '', 204


@api_bp.route('/trash/clear', methods=['POST'])
def clear_trash():
    files = trash_service.list_files()
    removed_count = len(files)

    trash_service.clear_files()
    deleted_text_count = text_service.purge_deleted_texts()
    text_service.add_log(
        'trash_clear',
        content=f'file_count={removed_count},text_count={deleted_text_count}',
        client_ip=get_client_ip(),
    )

    return jsonify({'removed_files': removed_count, 'removed_texts': deleted_text_count})
