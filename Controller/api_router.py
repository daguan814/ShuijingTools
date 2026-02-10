import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from Service.auth_service import auth_service
from Service.text_service import text_service
from Service.trash_service import trash_service

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix='/api')


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.client.host if request.client else ''


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
    rel = Path(rel_path.replace('\\', '/'))
    if rel.is_absolute():
        raise HTTPException(status_code=400, detail='invalid path')
    target = (UPLOAD_DIR / rel).resolve()
    upload_resolved = UPLOAD_DIR.resolve()
    if upload_resolved not in target.parents and target != upload_resolved:
        raise HTTPException(status_code=400, detail='invalid path')
    return target


def list_uploads():
    uploads = []
    for full_path in UPLOAD_DIR.glob('*'):
        if not full_path.is_file():
            continue
        uploads.append({
            'path': full_path.name,
            'size': format_size(full_path.stat().st_size),
            'mtime': full_path.stat().st_mtime,
        })
    uploads.sort(key=lambda item: item['mtime'], reverse=True)
    for item in uploads:
        item.pop('mtime', None)
    return uploads


@router.get('/health')
def health():
    return {'ok': True}


@router.post('/auth/verify')
async def verify_auth(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid json')
    passcode = str(payload.get('passcode', '')).strip()
    if not passcode:
        raise HTTPException(status_code=400, detail='passcode required')
    ok = auth_service.verify_passcode(passcode)
    if not ok:
        raise HTTPException(status_code=401, detail='invalid passcode')
    return {'ok': True}


@router.get('/texts')
def get_texts():
    texts = text_service.get_all_texts()
    return [
        {
            'id': text[0],
            'content': text[1],
            'created_at': text[2],
            'is_favorite': bool(text[3]),
            'favorite_group': int(text[4]),
        }
        for text in texts
    ]


@router.post('/texts')
def add_text(request: Request, content: str = Form(...)):
    content = (content or '').strip()
    if not content:
        raise HTTPException(status_code=400, detail='content is empty')
    text_id = text_service.add_text(content)
    text_service.add_log('text_add', text_id=text_id, content=content, client_ip=get_client_ip(request))
    return {'id': text_id}


@router.delete('/texts/{text_id}')
def delete_text(text_id: int, request: Request):
    deleted = text_service.delete_text(text_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='text not found')
    text_service.add_log('text_delete', text_id=text_id, client_ip=get_client_ip(request))
    return {'ok': True}


@router.post('/texts/{text_id}/favorite')
def toggle_favorite(text_id: int, request: Request):
    favorited = text_service.toggle_favorite(text_id)
    if favorited is None:
        raise HTTPException(status_code=404, detail='text not found')
    text_service.add_log(
        'text_favorite' if favorited else 'text_unfavorite',
        text_id=text_id,
        client_ip=get_client_ip(request),
    )
    return {'id': text_id, 'is_favorite': favorited}


@router.get('/favorites')
def get_favorites():
    favorites = text_service.get_favorite_texts()
    return [
        {
            'id': text[0],
            'content': text[1],
            'created_at': text[2],
            'is_favorite': bool(text[3]),
            'favorite_group': int(text[4]),
        }
        for text in favorites
    ]


@router.post('/favorites/move')
async def move_favorite(request: Request):
    payload = await request.json()
    text_id = int(payload.get('id'))
    group_id = int(payload.get('group'))

    moved = text_service.move_favorite_group(text_id, group_id)
    if moved is None:
        raise HTTPException(status_code=404, detail='favorite not found')

    text_service.add_log(
        'text_favorite_move',
        text_id=text_id,
        content=f'group={group_id}',
        client_ip=get_client_ip(request),
    )
    return {'id': text_id, 'group': group_id}


@router.get('/files')
def get_files():
    return list_uploads()


@router.post('/files/upload')
async def upload_files(request: Request, files: list[UploadFile] = File(...)):
    for f in files:
        if not f or not f.filename:
            continue
        target = safe_join_upload(f.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'wb') as dst:
            shutil.copyfileobj(f.file, dst)
        text_service.add_log('file_upload', content=f.filename, client_ip=get_client_ip(request))
    return JSONResponse(status_code=204, content={})


@router.get('/files/download/{filepath:path}')
def download_file(filepath: str):
    target = safe_join_upload(filepath)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail='file not found')
    return FileResponse(path=str(target), filename=target.name)


@router.post('/files/delete')
def delete_file(request: Request, path: str = Form(...)):
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
        text_service.add_log('file_delete', content=path, client_ip=get_client_ip(request))
    return JSONResponse(status_code=204, content={})


@router.get('/trash')
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

    return {'texts': texts_list, 'files': file_list}


@router.post('/trash/restore/text/{text_id}')
def restore_text(text_id: int, request: Request):
    restored = text_service.restore_text(text_id)
    if not restored:
        raise HTTPException(status_code=404, detail='text not found')
    text_service.add_log('text_restore', text_id=text_id, client_ip=get_client_ip(request))
    return JSONResponse(status_code=204, content={})


@router.post('/trash/restore/file')
def restore_file(request: Request, id: int = Form(...)):
    file_row = trash_service.get_file(id)
    if not file_row:
        raise HTTPException(status_code=404, detail='file not found')

    trash_path = safe_join_upload(file_row['trash_path'])
    if not trash_path.exists() or not trash_path.is_file():
        trash_service.remove_file(id)
        raise HTTPException(status_code=404, detail='file data missing')

    restore_path = safe_join_upload(file_row['original_path'])
    restore_rel = file_row['original_path']

    if restore_path.exists():
        stem = restore_path.stem
        suffix = restore_path.suffix
        restore_rel = f"{stem}-restored-{id}{suffix}"
        restore_path = safe_join_upload(restore_rel)

    restore_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_path), str(restore_path))
    trash_service.remove_file(id)
    text_service.add_log('file_restore', content=restore_rel, client_ip=get_client_ip(request))
    return JSONResponse(status_code=204, content={})


@router.delete('/trash/text/{text_id}')
def delete_trash_text(text_id: int, request: Request):
    deleted = text_service.purge_deleted_text(text_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='text not found')
    text_service.add_log('trash_delete_text', text_id=text_id, client_ip=get_client_ip(request))
    return JSONResponse(status_code=204, content={})


@router.delete('/trash/file/{file_id}')
def delete_trash_file(file_id: int, request: Request):
    file_row = trash_service.get_file(file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail='file not found')

    trash_service.remove_file(file_id)
    text_service.add_log('trash_delete_file', content=file_row.get('original_path', ''), client_ip=get_client_ip(request))
    return JSONResponse(status_code=204, content={})


@router.post('/trash/clear')
def clear_trash(request: Request):
    files = trash_service.list_files()
    removed_count = len(files)

    trash_service.clear_files()
    deleted_text_count = text_service.purge_deleted_texts()
    text_service.add_log(
        'trash_clear',
        content=f'file_count={removed_count},text_count={deleted_text_count}',
        client_ip=get_client_ip(request),
    )

    return {'removed_files': removed_count, 'removed_texts': deleted_text_count}
