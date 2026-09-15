from functools import wraps
from datetime import datetime
import mimetypes
import os
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, current_app, g, jsonify, request, send_file
from itsdangerous import BadSignature, SignatureExpired

from ..admin_service import admin_service
from ..admin_file_service import admin_file_service
from ..auth_service import auth_service
from ..database import db_manager
from ..file_service import file_service, format_size
from ..log_service import log_service
from ..recycle_service import recycle_service
from ..school_service import school_service
from ..preview_service import preview_service

admin_bp=Blueprint("admin",__name__,url_prefix="/api/admin")

def admin_required(view):
    @wraps(view)
    def wrapped(*args,**kwargs):
        token=request.headers.get("Authorization","").removeprefix("Bearer ").strip()
        try: payload=current_app.admin_serializer.loads(token,max_age=12*3600)
        except (BadSignature,SignatureExpired): return jsonify({"detail":"管理员登录已失效"}),401
        if payload.get("role")!="admin" or not payload.get("admin_id"):
            return jsonify({"detail":"无权限"}),403
        admin = admin_service.find_by_id(payload["admin_id"])
        if not admin or admin["status"] != "active":
            return jsonify({"detail":"管理员账号不可用，请重新登录"}),401
        g.current_admin = admin
        return view(*args,**kwargs)
    return wrapped

@admin_bp.post("/login")
def login():
    payload=request.get_json(silent=True) or {}
    admin = admin_service.login(payload.get("username"), payload.get("password"))
    if not admin:
        return jsonify({"detail":"管理员账号或密码错误"}),401
    return jsonify({"token":current_app.admin_serializer.dumps({"role":"admin", "admin_id":admin["id"]})})

@admin_bp.get("/overview")
@admin_required
def overview():
    return jsonify({"admins":admin_service.list(),"classes":school_service.classes(),"students":school_service.students(),"requests":school_service.requests(),"reports":school_service.reports(),"announcements":school_service.announcements()})

@admin_bp.get("/dashboard-stats")
@admin_required
def dashboard_stats():
    from datetime import datetime, timedelta
    classes = school_service.classes()
    students = school_service.students()
    requests = school_service.requests()
    reports = school_service.reports()
    admins = admin_service.list()
    student_storage = sum(s["used"] for s in students)
    admin_storage = 0
    total_files = 0
    total_folders = 0
    student_files = 0
    class_storage = []
    for cls in classes:
        cls_students = [s for s in students if s["class_id"] == cls["id"]]
        cls_used = sum(s["used"] for s in cls_students)
        class_storage.append({
            "id": cls["id"],
            "name": cls["name"],
            "users": len(cls_students),
            "storage_used": cls_used,
            "storage_display": format_size(cls_used),
        })
        for s in cls_students:
            root = file_service.user_root(s)
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d != ".DS_Store" and not (Path(dirpath) / d).is_symlink()]
                total_folders += len(dirnames)
                file_count = len([f for f in filenames if f != ".DS_Store" and not (Path(dirpath) / f).is_symlink()])
                total_files += file_count
                student_files += file_count
    for admin in admins:
        root = admin_file_service.root(admin["id"])
        admin_storage += file_service._directory_size(root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".DS_Store" and not (Path(dirpath) / d).is_symlink()]
            total_folders += len(dirnames)
            total_files += len([f for f in filenames if f != ".DS_Store" and not (Path(dirpath) / f).is_symlink()])
    total_storage = student_storage + admin_storage
    today = datetime.now().date()
    activity = []
    for i in range(6, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        log_total = log_service.list_all_logs(day=day, page_size=1)["total"]
        activity.append({"date": day, "operations": log_total})
    # Keep the dashboard card consistent with the activity chart: both show
    # today's total file-operation volume rather than a deduplicated user count.
    today_active_users = activity[-1]["operations"] if activity else 0
    return jsonify({
        "totals": {
            "classes": len(classes),
            "users": len(students),
            "active_users": sum(1 for s in students if s["status"] == "active"),
            "pending_requests": len(requests),
            "reports": len(reports),
            "admins": len(admins),
            "storage_used": total_storage,
            "storage_display": format_size(total_storage),
            "student_storage_used": student_storage,
            "student_storage_display": format_size(student_storage),
            "admin_storage_used": admin_storage,
            "admin_storage_display": format_size(admin_storage),
            "files": total_files,
            "folders": total_folders,
            "student_files": student_files,
            "today_active_users": today_active_users,
        },
        "class_storage": class_storage,
        "activity": activity,
    })

@admin_bp.post("/admins")
@admin_required
def create_admin():
    payload = request.get_json(silent=True) or {}
    try:
        admin_id = admin_service.create(payload.get("username"), payload.get("password"))
    except ValueError as exc:
        return jsonify({"detail":str(exc)}),400
    admin_file_service.root(admin_id)
    return jsonify({"id":admin_id}),201

@admin_bp.patch("/admins/<int:admin_id>")
@admin_required
def update_admin(admin_id):
    payload = request.get_json(silent=True) or {}
    current = admin_service.find_by_id(admin_id)
    if not current:
        return jsonify({"detail":"管理员不存在"}),400
    old_name = current["username"]
    new_name = payload.get("username", old_name)
    moved_directory = False
    try:
        if new_name != old_name:
            admin_file_service.rename_owner_directories(admin_id, old_name, new_name)
            moved_directory = True
        admin_service.update(admin_id, payload.get("username"), payload.get("password"), payload.get("status"))
    except Exception as exc:
        if moved_directory:
            try:
                admin_file_service.rename_owner_directories(admin_id, new_name, old_name)
            except Exception:
                current_app.logger.exception("管理员目录回滚失败")
        if isinstance(exc, (ValueError, FileExistsError)):
            return jsonify({"detail":str(exc)}),400
        current_app.logger.exception("管理员信息更新失败")
        return jsonify({"detail":"管理员信息更新失败"}),500
    return "",204

@admin_bp.get("/messages")
@admin_required
def messages():
    try:
        class_id=int(request.args.get("class_id","0") or 0) or None
        day=request.args.get("date","").strip() or None
        page=max(1,int(request.args.get("page","1")))
        page_size=min(100,max(10,int(request.args.get("page_size","20"))))
        if day:
            from datetime import datetime
            datetime.strptime(day,"%Y-%m-%d")
    except ValueError:return jsonify({"detail":"消息筛选参数无效"}),400
    reports=school_service.reports_page(class_id,day,page,page_size)
    return jsonify({"requests":school_service.requests(class_id,day),"reports":reports["items"],"reports_paging":{key:reports[key] for key in ("total","page","page_size","total_pages")}})

@admin_bp.get("/logs")
@admin_required
def logs():
    action=request.args.get("action","all"); day=request.args.get("date","").strip()
    if action not in {"all",*log_service.ACTION_PREFIXES.keys()}:return jsonify({"detail":"日志类型无效"}),400
    try:
        page=max(1,int(request.args.get("page","1")))
        page_size=min(100,max(10,int(request.args.get("page_size","20"))))
        class_id=int(request.args.get("class_id","0") or 0)
        user_id=int(request.args.get("user_id","0") or 0)
        if day:
            from datetime import datetime
            datetime.strptime(day,"%Y-%m-%d")
    except ValueError:return jsonify({"detail":"日志筛选参数无效"}),400
    return jsonify(log_service.list_all_logs(None if action=="all" else action,day or None,class_id or None,user_id or None,page,page_size))

@admin_bp.post("/classes")
@admin_required
def create_class():
    try: class_id=school_service.create_class((request.get_json(silent=True) or {}).get("name"))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"id":class_id}),201

@admin_bp.patch("/classes/<int:class_id>")
@admin_required
def rename_class(class_id):
    try: school_service.rename_class(class_id,(request.get_json(silent=True) or {}).get("name"))
    except FileExistsError as exc:return jsonify({"detail":str(exc)}),409
    except ValueError as exc:return jsonify({"detail":str(exc)}),400
    return "",204

@admin_bp.delete("/classes/<int:class_id>")
@admin_required
def delete_class(class_id):
    try:school_service.delete_class(class_id)
    except ValueError as exc:return jsonify({"detail":str(exc)}),409
    return "",204

@admin_bp.post("/requests/<int:request_id>/review")
@admin_required
def review(request_id):
    try:school_service.review(request_id,bool((request.get_json(silent=True) or {}).get("approve")))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return "",204

@admin_bp.patch("/students/<int:user_id>")
@admin_required
def update_student(user_id):
    payload=request.get_json(silent=True) or {}
    try:school_service.update_student(user_id,payload.get("username"),payload.get("class_id"),payload.get("password"),payload.get("status"))
    except FileExistsError as exc:return jsonify({"detail":str(exc)}),409
    except ValueError as exc:return jsonify({"detail":str(exc)}),400
    return "",204

@admin_bp.delete("/students/<int:user_id>")
@admin_required
def delete_student(user_id):
    payload=request.get_json(silent=True) or {}
    if payload.get("acknowledge")!="我确认删除用户并将文件移入回收站":return jsonify({"detail":"请确认删除操作"}),400
    try:school_service.delete_student(user_id,str(payload.get("username","")))
    except ValueError as exc:return jsonify({"detail":str(exc)}),400
    return "",204

@admin_bp.post("/students")
@admin_required
def create_student():
    payload=request.get_json(silent=True) or {}
    try:user_id=school_service.create_user(payload.get("class_id"),payload.get("username"),payload.get("password"))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"id":user_id}),201

@admin_bp.post("/login-attempts/clear")
@admin_required
def clear_login_attempts():
    return jsonify({"cleared":auth_service.clear_login_attempts()})

@admin_bp.get("/personal-files")
@admin_required
def personal_files():
    try:
        result = admin_file_service.list_entries(g.current_admin["id"], request.args.get("path", ""))
        # 共享状态仅是附加信息，不能因为记录表异常而阻塞管理员读取或上传文件。
        try:
            shares = admin_file_service.shares_for_admin(g.current_admin["id"])
            share_ids = admin_file_service.share_ids_for_admin(g.current_admin["id"])
        except Exception:
            current_app.logger.exception("Failed to load administrator file shares")
            shares, share_ids = {}, {}
        for item in result["entries"]:
            item["shared_groups"] = shares.get(item["path"], "")
            item["shared_class_ids"] = share_ids.get(item["path"], [])
        return jsonify(result)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/upload")
@admin_required
def personal_upload():
    files = request.files.getlist("files"); relatives = request.form.getlist("relative_paths")
    if not files or len(files) != len(relatives):
        return jsonify({"detail": "上传参数无效"}), 400
    try:
        uploaded = admin_file_service.upload(g.current_admin["id"], request.form.get("path", ""), files, relatives)
        return jsonify({"uploaded": uploaded})
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/mkdir")
@admin_required
def personal_mkdir():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"path": admin_file_service.mkdir(g.current_admin["id"], payload.get("path", ""), payload.get("name", ""))}), 201
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/rename")
@admin_required
def personal_rename():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"path": admin_file_service.rename(g.current_admin["id"], payload.get("path", ""), payload.get("name", ""))})
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/move")
@admin_required
def personal_move():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"paths": admin_file_service.move(g.current_admin["id"], payload.get("paths", []), payload.get("destination", ""))})
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/delete")
@admin_required
def personal_delete():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"items": admin_file_service.delete(g.current_admin["id"], payload.get("paths", []))})
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.get("/personal-files/download")
@admin_required
def personal_download():
    try:
        target = admin_file_service.target(g.current_admin["id"], request.args.get("path", ""))
        if target.is_file():
            return send_file(target, as_attachment=True, download_name=target.name)
        archive = tempfile.NamedTemporaryFile(prefix="shuijing-admin-", suffix=".zip", delete=False)
        archive_path = Path(archive.name); archive.close()
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as output:
            for child in target.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    output.write(child, arcname=str(Path(target.name) / child.relative_to(target)))
        response = send_file(archive_path, as_attachment=True, download_name=f"{target.name}.zip")
        response.call_on_close(lambda: archive_path.unlink(missing_ok=True)); return response
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/downloads/prepare")
@admin_required
def prepare_admin_download():
    payload=request.get_json(silent=True) or {}
    scope=payload.get("scope")
    paths=payload.get("paths")
    if scope not in {"personal","class"} or not isinstance(paths,list) or not paths:
        return jsonify({"detail":"下载参数无效"}),400
    try:
        if scope=="personal":
            for path in paths: admin_file_service.target(g.current_admin["id"],path)
            ticket_data={"scope":"personal","paths":paths}
        else:
            class_id=int(payload.get("class_id"))
            for path in paths:
                user,sub_path,_=_class_path(class_id,path)
                if not file_service.resolve_user_path(user,sub_path).exists(): raise FileNotFoundError(path)
            ticket_data={"scope":"class","class_id":class_id,"paths":paths}
    except Exception as exc:
        return jsonify({"detail":str(exc)}),400
    ticket=current_app.admin_serializer.dumps({"purpose":"download","admin_id":g.current_admin["id"],**ticket_data})
    return jsonify({"url":f"/api/admin/downloads/ticket/{quote(ticket)}"})

@admin_bp.get("/downloads/ticket/<path:ticket>")
def admin_download_ticket(ticket):
    archive_path=None
    try:
        payload=current_app.admin_serializer.loads(ticket,max_age=300)
        admin=admin_service.find_by_id(payload.get("admin_id"))
        if payload.get("purpose")!="download" or not admin or admin["status"]!="active": raise ValueError("invalid ticket")
        paths=payload.get("paths")
        if not isinstance(paths,list) or not paths: raise ValueError("invalid ticket")
        sources=[]
        if payload.get("scope")=="personal":
            for path in paths: sources.append((admin_file_service.target(admin["id"],path),Path(path)))
        elif payload.get("scope")=="class":
            class_id=int(payload.get("class_id"))
            for path in paths:
                user,sub_path,class_path=_class_path(class_id,path)
                sources.append((file_service.resolve_user_path(user,sub_path),Path(class_path)))
        else: raise ValueError("invalid ticket")
        if len(sources)==1 and sources[0][0].is_file():
            target=sources[0][0]
            return send_file(target,as_attachment=True,download_name=target.name,conditional=True)
        temp=tempfile.NamedTemporaryFile(prefix="shuijing-admin-download-",suffix=".zip",delete=False)
        archive_path=Path(temp.name);temp.close()
        with zipfile.ZipFile(archive_path,"w",zipfile.ZIP_DEFLATED) as archive:
            for source,display_path in sources:
                if source.is_file() and not source.is_symlink(): archive.write(source,arcname=str(display_path))
                elif source.is_dir():
                    for child in source.rglob("*"):
                        if child.is_file() and not child.is_symlink(): archive.write(child,arcname=str(display_path/child.relative_to(source)))
        response=send_file(archive_path,as_attachment=True,download_name="管理员文件.zip",conditional=True)
        response.call_on_close(lambda:archive_path.unlink(missing_ok=True));return response
    except (BadSignature,SignatureExpired,KeyError,TypeError,ValueError):
        return jsonify({"detail":"下载链接已失效或无效"}),401
    except FileNotFoundError:
        return jsonify({"detail":"文件不存在"}),404
    except Exception:
        if archive_path: archive_path.unlink(missing_ok=True)
        current_app.logger.exception("管理员下载失败")
        return jsonify({"detail":"下载失败"}),500

@admin_bp.post("/personal-files/share")
@admin_required
def personal_share():
    payload = request.get_json(silent=True) or {}
    try:
        admin_file_service.set_shares(g.current_admin["id"], payload.get("paths", []), payload.get("class_ids", []))
        return "", 204
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/shares/clear")
@admin_required
def clear_personal_shares():
    try:
        return jsonify({"removed": admin_file_service.clear_all_shares(g.current_admin["id"])})
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

@admin_bp.post("/personal-files/preview/start")
@admin_required
def personal_preview_start():
    try:
        path = request.args.get("path", "")
        target = admin_file_service.target(g.current_admin["id"], path)
        if not target.is_file():
            raise ValueError("文件夹不能直接预览")
        return jsonify({"url": preview_service.preview_url(current_app, {
            "kind": "admin", "admin_id": int(g.current_admin["id"]), "path": path,
        }, target.name)})
    except Exception as exc:
        return jsonify({"detail": str(exc)}), 400

def _student(user_id):
    user=db_manager.find_user_by_id(user_id)
    if not user or user["status"]=="deleted":raise ValueError("学生不存在")
    return user

def _class_students(class_id):
    return school_service.students_for_class(class_id)

def _class_path(class_id, raw_path, allow_student_root=True):
    normalized=file_service.normalize_relative_path(raw_path)
    if not normalized:raise ValueError("请选择学生目录")
    first,*rest=normalized.split("/")
    user=next((student for student in _class_students(class_id) if student["storage_key"]==first),None)
    if not user:raise ValueError("学生目录不存在")
    sub_path="/".join(rest)
    if not allow_student_root and not sub_path:raise ValueError("不能在班级文件页修改学生根目录")
    return user,sub_path,normalized

@admin_bp.get("/classes/<int:class_id>/files")
@admin_required
def class_files(class_id):
    relative=file_service.normalize_relative_path(request.args.get("path",""))
    try:
        students=_class_students(class_id)
        if not students and not any(int(item["id"])==class_id for item in school_service.classes()):raise ValueError("班级不存在")
        if not relative:
            entries=[]
            for user in students:
                root=file_service.user_root(user)
                entries.append(file_service._entry_info(user,root,user["storage_key"]))
        else:
            user,sub_path,prefix=_class_path(class_id,relative)
            entries=file_service.list_entries(user,sub_path)
            for item in entries:item["path"]=f"{user['storage_key']}/{item['path']}"
    except (ValueError,FileNotFoundError) as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"path":relative,"entries":entries})

@admin_bp.post("/classes/<int:class_id>/mkdir")
@admin_required
def class_mkdir(class_id):
    payload=request.get_json(silent=True) or {}
    try:
        user,sub_path,_=_class_path(class_id,payload.get("path",""))
        created=file_service.create_folder(user,sub_path,payload.get("name"))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"path":f"{user['storage_key']}/{created}"}),201

@admin_bp.post("/classes/<int:class_id>/rename")
@admin_required
def class_rename(class_id):
    payload=request.get_json(silent=True) or {}
    try:
        user,sub_path,_=_class_path(class_id,payload.get("path",""),False)
        renamed=file_service.rename_path(user,sub_path,payload.get("name",""))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify(renamed)

@admin_bp.post("/classes/<int:class_id>/delete-file")
@admin_required
def class_delete_file(class_id):
    try:
        user,sub_path,_=_class_path(class_id,(request.get_json(silent=True) or {}).get("path",""),False)
        item=recycle_service.move_to_recycle(user,sub_path)
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify(item)

@admin_bp.get("/classes/<int:class_id>/download")
@admin_required
def class_download(class_id):
    try:
        user,sub_path,_=_class_path(class_id,request.args.get("path",""))
        target=file_service.resolve_user_path(user,sub_path)
        if not target.exists():raise FileNotFoundError(sub_path)
        if target.is_file():return send_file(target,as_attachment=True,download_name=target.name)
        archive=file_service.build_download_archive(user,[sub_path],sub_path.rsplit("/",1)[0] if "/" in sub_path else "")
        response=send_file(archive,as_attachment=True,download_name=f"{target.name}.zip")
        response.call_on_close(lambda:archive.unlink(missing_ok=True));return response
    except Exception as exc:return jsonify({"detail":str(exc)}),400

@admin_bp.post("/classes/<int:class_id>/batch-download")
@admin_required
def class_batch_download(class_id):
    paths=(request.get_json(silent=True) or {}).get("paths",[])
    if not isinstance(paths,list) or not paths:return jsonify({"detail":"请选择要下载的项目"}),400
    temp=tempfile.NamedTemporaryFile(prefix="shuijing-class-",suffix=".zip",delete=False);archive_path=Path(temp.name);temp.close()
    try:
        with zipfile.ZipFile(archive_path,"w",zipfile.ZIP_DEFLATED) as archive:
            for raw_path in paths:
                user,sub_path,class_path=_class_path(class_id,raw_path)
                source=file_service.resolve_user_path(user,sub_path)
                if not source.exists():raise FileNotFoundError(class_path)
                if source.is_dir():
                    for child in source.rglob("*"):
                        if child.name==".DS_Store" or child.is_symlink():continue
                        child_rel=child.relative_to(source)
                        archive.write(str(child),arcname=str(Path(class_path)/child_rel))
                elif not source.is_symlink():archive.write(str(source),arcname=class_path)
        response=send_file(archive_path,as_attachment=True,download_name="班级文件.zip")
        response.call_on_close(lambda:archive_path.unlink(missing_ok=True));return response
    except Exception as exc:
        archive_path.unlink(missing_ok=True);return jsonify({"detail":str(exc)}),400

@admin_bp.post("/classes/<int:class_id>/preview/start")
@admin_required
def start_class_preview(class_id):
    try:
        user,sub_path,_=_class_path(class_id,request.args.get("path",""),False)
        target=file_service.download_target(user,sub_path)
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"url":preview_service.preview_url(current_app,{
        "kind":"student","user_id":int(user["id"]),"path":sub_path,
    },target.name)})

@admin_bp.post("/classes/<int:class_id>/upload")
@admin_required
def class_upload(class_id):
    parent=request.form.get("path","");files=request.files.getlist("files");relatives=request.form.getlist("relative_paths")
    if not files or len(files)!=len(relatives):return jsonify({"detail":"上传参数无效"}),400
    try:
        user,sub_path,_=_class_path(class_id,parent)
        uploaded=[file_service.upload_file(user,sub_path,rel,file) for file,rel in zip(files,relatives)]
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"uploaded":uploaded})

@admin_bp.post("/classes/<int:class_id>/move")
@admin_required
def class_move(class_id):
    payload=request.get_json(silent=True) or {};paths=payload.get("paths",[])
    try:
        destination_user,destination_sub,_=_class_path(class_id,payload.get("destination",""))
        sources=[]
        for raw in paths:
            user,sub_path,_=_class_path(class_id,raw,False)
            if user["id"]!=destination_user["id"]:raise ValueError("暂不支持跨学生移动文件")
            sources.append(sub_path)
        moved=file_service.move_paths(destination_user,sources,destination_sub)
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"moved":moved})

@admin_bp.post("/classes/<int:class_id>/batch-delete")
@admin_required
def class_batch_delete(class_id):
    paths=(request.get_json(silent=True) or {}).get("paths",[])
    if not isinstance(paths,list) or not paths:return jsonify({"detail":"请选择要删除的项目"}),400
    results=[]
    for raw_path in paths:
        try:
            user,sub_path,class_path=_class_path(class_id,raw_path,False)
            recycle_service.move_to_recycle(user,sub_path);results.append({"path":class_path,"deleted":True})
        except Exception as exc:results.append({"path":str(raw_path),"deleted":False,"error":str(exc)})
    return jsonify({"results":results})

@admin_bp.get("/students/<int:user_id>/files")
@admin_required
def files(user_id):
    try:
        user=_student(user_id); path=request.args.get("path",""); entries=file_service.list_entries(user,path)
    except (ValueError,FileNotFoundError) as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"path":file_service.normalize_relative_path(path),"entries":entries})

@admin_bp.post("/students/<int:user_id>/mkdir")
@admin_required
def mkdir(user_id):
    payload=request.get_json(silent=True) or {}
    try:path=file_service.create_folder(_student(user_id),payload.get("path",""),payload.get("name"))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"path":path}),201

@admin_bp.post("/students/<int:user_id>/rename")
@admin_required
def rename(user_id):
    payload=request.get_json(silent=True) or {}
    try:item=file_service.rename_path(_student(user_id),payload.get("path",""),payload.get("name",""))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify(item)

@admin_bp.post("/students/<int:user_id>/delete")
@admin_required
def delete_file(user_id):
    try:item=recycle_service.move_to_recycle(_student(user_id),(request.get_json(silent=True) or {}).get("path",""))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify(item)

@admin_bp.get("/students/<int:user_id>/download")
@admin_required
def download(user_id):
    try:target=file_service.download_target(_student(user_id),request.args.get("path",""))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return send_file(target,as_attachment=True,download_name=target.name)

@admin_bp.post("/students/<int:user_id>/batch-download")
@admin_required
def batch_download(user_id):
    payload=request.get_json(silent=True) or {}
    try:
        archive=file_service.build_download_archive(_student(user_id),payload.get("paths",[]),payload.get("base_path",""))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    response=send_file(archive,as_attachment=True,download_name="云盘文件.zip")
    response.call_on_close(lambda: archive.unlink(missing_ok=True))
    return response

@admin_bp.post("/students/<int:user_id>/upload")
@admin_required
def upload(user_id):
    user=_student(user_id); parent=request.form.get("path",""); files=request.files.getlist("files"); relatives=request.form.getlist("relative_paths")
    if not files or len(files)!=len(relatives):return jsonify({"detail":"上传参数无效"}),400
    try:uploaded=[file_service.upload_file(user,parent,rel,file) for file,rel in zip(files,relatives)]
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"uploaded":uploaded})

@admin_bp.post("/students/<int:user_id>/move")
@admin_required
def move(user_id):
    payload=request.get_json(silent=True) or {}
    try:moved=file_service.move_paths(_student(user_id),payload.get("paths",[]),payload.get("destination",""))
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"moved":moved})

@admin_bp.post("/announcements")
@admin_required
def announcement():
    payload=request.get_json(silent=True) or {}
    try:school_service.replace_announcements(payload.get("class_ids") or [payload.get("class_id")],payload.get("title"),payload.get("content"))
    except ValueError as exc:return jsonify({"detail":str(exc)}),400
    return "",204

@admin_bp.get("/recycle")
@admin_required
def recycle():
    items=[]
    for user in school_service.students():
        for item in recycle_service.list_items(user):item.update(user_id=user["id"],username=user["username"],class_name=user["class_name"]);items.append(item)
    for row in admin_file_service.list_recycle_items():
        # SQLite returns sqlite3.Row while MySQL returns a dict.  Copy both so
        # adding display-only ownership fields never mutates an immutable row.
        item = dict(row)
        item.update(
            owner_type="admin",
            user_id=None,
            username=item.pop("admin_name"),
            class_name="管理员个人文件",
            name=item.pop("item_name"),
            type=item.pop("item_type"),
            path=item["original_path"],
        )
        items.append(item)
    def deleted_timestamp(item):
        value = item["deleted_at"]
        if hasattr(value, "timestamp"):
            return value.timestamp()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()

    items.sort(key=deleted_timestamp, reverse=True)
    return jsonify({"items":items})

@admin_bp.post("/recycle/<int:item_id>/restore")
@admin_required
def restore(item_id):
    payload=request.get_json(silent=True) or {}
    try:
        if payload.get("owner_type") == "admin": path=admin_file_service.restore_recycle_item(item_id)
        else: path=recycle_service.restore(_student(int(payload.get("user_id"))),item_id,require_password=False)
    except Exception as exc:return jsonify({"detail":str(exc)}),400
    return jsonify({"path":path})
