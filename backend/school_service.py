import uuid
from datetime import datetime

from werkzeug.security import generate_password_hash

from .config import STORAGE_ROOT
from .database import db_manager
from .file_service import file_service


class SchoolService:
    def rows(self, sql, params=()):
        conn=db_manager.get_connection(); cursor=db_manager.cursor(conn,dictionary=True)
        cursor.execute(sql,params); rows=[dict(row) for row in cursor.fetchall()]
        cursor.close(); conn.close(); return rows

    def classes(self):
        return self.rows("SELECT id,name,storage_key,created_at FROM school_classes ORDER BY name")

    def register(self,class_id,username,password):
        username=file_service.normalize_username(username)
        if len(password)<6: raise ValueError("密码至少需要6位")
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn, dictionary=True)
        cursor.execute(f"SELECT id FROM school_classes WHERE id={ph}",(class_id,))
        if not cursor.fetchone(): cursor.close(); conn.close(); raise ValueError("班级不存在")
        cursor.execute(f"SELECT id,status FROM storage_users WHERE username={ph}",(username,))
        existing = cursor.fetchone()
        if existing and existing["status"] != "deleted": cursor.close(); conn.close(); raise FileExistsError("用户名已被使用")
        cursor.execute(f"SELECT id FROM registration_requests WHERE username={ph} AND status='pending'",(username,))
        if cursor.fetchone(): cursor.close(); conn.close(); raise FileExistsError("该姓名已有待审核申请")
        cursor.execute(f"INSERT INTO registration_requests(class_id,username,password_hash) VALUES({ph},{ph},{ph})",(class_id,username,generate_password_hash(password)))
        conn.commit(); request_id=cursor.lastrowid; cursor.close(); conn.close(); return request_id

    def students(self):
        rows=self.rows("""SELECT u.id,u.username,u.storage_key,u.status,u.created_at,u.class_id,c.name AS class_name,c.storage_key AS class_storage_key
            FROM storage_users u JOIN school_classes c ON c.id=u.class_id WHERE u.status!='deleted' ORDER BY c.name,u.username""")
        for row in rows:
            usage=file_service.storage_usage(row)
            row["used"]=usage["used"]
            row["used_display"]=usage["used_display"]
            row["disk_total_display"]=usage["disk_total_display"]
        return rows

    def students_for_class(self, class_id):
        ph=db_manager.placeholder()
        return self.rows(f"""SELECT u.id,u.username,u.storage_key,u.status,u.class_id,
            c.name AS class_name,c.storage_key AS class_storage_key
            FROM storage_users u JOIN school_classes c ON c.id=u.class_id
            WHERE u.class_id={ph} AND u.status!='deleted' ORDER BY u.username""",(class_id,))

    def requests(self, class_id=None, day=None):
        ph=db_manager.placeholder(); where=["r.status='pending'"]; params=[]
        if class_id: where.append(f"r.class_id={ph}"); params.append(class_id)
        if day: where.append(f"DATE(r.created_at)={ph}"); params.append(day)
        return self.rows("""SELECT r.id,r.username,r.class_id,r.created_at,c.name AS class_name FROM registration_requests r
            JOIN school_classes c ON c.id=r.class_id WHERE """+" AND ".join(where)+" ORDER BY r.id",tuple(params))

    def review(self,request_id,approve):
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn,dictionary=True)
        cursor.execute(f"SELECT * FROM registration_requests WHERE id={ph} AND status='pending'",(request_id,)); row=cursor.fetchone()
        if not row: cursor.close(); conn.close(); raise ValueError("申请不存在或已处理")
        if approve:
            now=db_manager.now_expr()
            cursor.execute(f"SELECT id,status FROM storage_users WHERE username={ph}",(row["username"],))
            existing=cursor.fetchone()
            if existing and existing["status"] != "deleted": raise ValueError("用户名已被使用")
            if existing:
                cursor.execute(f"UPDATE storage_users SET storage_key={ph},class_id={ph},password_hash={ph},status='active',deleted_at=NULL,updated_at={now} WHERE id={ph}",(row["username"],row["class_id"],row["password_hash"],existing["id"]))
                user_id=existing["id"]
            else:
                cursor.execute(f"INSERT INTO storage_users(username,storage_key,class_id,password_hash,status,created_at,updated_at) VALUES({ph},{ph},{ph},{ph},'active',{now},{now})",(row["username"],row["username"],row["class_id"],row["password_hash"]))
                user_id=cursor.lastrowid
            status="approved"
        else: user_id=None; status="rejected"
        cursor.execute(f"UPDATE registration_requests SET status={ph},reviewed_at={db_manager.now_expr()} WHERE id={ph}",(status,request_id))
        conn.commit(); cursor.close(); conn.close()
        if user_id: file_service.ensure_user_root(db_manager.find_user_by_id(user_id))

    def create_user(self, class_id, username, password):
        request_id=self.register(class_id,username,password)
        self.review(request_id,True)
        user=db_manager.find_user_by_username(file_service.normalize_username(username))
        return user["id"] if user else None

    def create_class(self,name):
        name=file_service.normalize_storage_name(name); ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn)
        cursor.execute(f"INSERT INTO school_classes(name,storage_key) VALUES({ph},{ph})",(name,name)); conn.commit(); class_id=cursor.lastrowid; cursor.close(); conn.close()
        (STORAGE_ROOT/name).mkdir(parents=True,exist_ok=True); return class_id

    def rename_class(self,class_id,new_name):
        new_name=file_service.normalize_storage_name(new_name); ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn,dictionary=True)
        cursor.execute(f"SELECT * FROM school_classes WHERE id={ph}",(class_id,)); row=cursor.fetchone()
        if not row: cursor.close(); conn.close(); raise ValueError("班级不存在")
        source=STORAGE_ROOT/row["storage_key"]; target=STORAGE_ROOT/new_name
        if target.exists() and target!=source: cursor.close(); conn.close(); raise FileExistsError("同名班级目录已存在")
        moved = False
        try:
            if source.exists() and source != target:
                source.rename(target)
                moved = True
            cursor.execute(
                f"UPDATE school_classes SET name={ph},storage_key={ph} WHERE id={ph}",
                (new_name,new_name,class_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            if moved and target.exists() and not source.exists():
                target.rename(source)
            raise
        finally:
            cursor.close(); conn.close()

    def delete_class(self,class_id):
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn,dictionary=True)
        cursor.execute(f"SELECT * FROM school_classes WHERE id={ph}",(class_id,)); row=cursor.fetchone()
        if not row: cursor.close(); conn.close(); raise ValueError("班级不存在")
        cursor.execute(f"SELECT COUNT(*) AS total FROM storage_users WHERE class_id={ph} AND status!='deleted'",(class_id,))
        if cursor.fetchone()["total"]: cursor.close(); conn.close(); raise ValueError("用户组内仍有用户，不能删除")
        path=STORAGE_ROOT/row["storage_key"]
        if path.exists() and any(path.iterdir()): cursor.close(); conn.close(); raise ValueError("班级目录不为空，不能删除")
        if path.exists(): path.rmdir()
        cursor.execute(f"DELETE FROM school_classes WHERE id={ph}",(class_id,)); conn.commit(); cursor.close(); conn.close()

    def update_student(self,user_id,username=None,class_id=None,password=None,status=None):
        user=db_manager.find_user_by_id(user_id)
        if not user: raise ValueError("学生不存在")
        ph=db_manager.placeholder(); fields=[]; params=[]
        old_root=(STORAGE_ROOT/user["class_storage_key"]/user["storage_key"]).resolve()
        if username:
            username=file_service.normalize_username(username); fields += [f"username={ph}",f"storage_key={ph}"]; params += [username,username]
            existing=db_manager.find_user_by_username(username)
            if existing and existing["id"]!=user_id: raise FileExistsError("该姓名已被使用")
        target_class_key=user["class_storage_key"]
        if class_id is not None: fields.append(f"class_id={ph}"); params.append(class_id)
        if class_id is not None:
            rows=self.rows(f"SELECT storage_key FROM school_classes WHERE id={ph}",(class_id,))
            if not rows: raise ValueError("班级不存在")
            target_class_key=rows[0]["storage_key"]
        target_name=username or user["storage_key"]
        planned_root=STORAGE_ROOT/target_class_key/target_name
        if planned_root!=old_root and planned_root.exists() and any(planned_root.iterdir()): raise FileExistsError("目标学生目录非空")
        if password:
            if len(password)<6: raise ValueError("密码至少需要6位")
            fields.append(f"password_hash={ph}"); params.append(generate_password_hash(password)); status="active"
        if status:
            if status not in {"active","disabled","password_required"}: raise ValueError("状态无效")
            fields.append(f"status={ph}"); params.append(status)
        if not fields:return
        moved = False
        planned_root.parent.mkdir(parents=True,exist_ok=True)
        if old_root != planned_root and old_root.exists():
            if planned_root.exists(): planned_root.rmdir()
            old_root.rename(planned_root)
            moved = True
        conn=db_manager.get_connection(); cursor=db_manager.cursor(conn); params.append(user_id)
        try:
            cursor.execute(f"UPDATE storage_users SET {','.join(fields)} WHERE id={ph}",tuple(params))
            cursor.execute(f"DELETE FROM user_sessions WHERE user_id={ph}",(user_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            if moved and planned_root.exists() and not old_root.exists():
                old_root.parent.mkdir(parents=True,exist_ok=True)
                planned_root.rename(old_root)
            raise
        finally:
            cursor.close(); conn.close()
        file_service.ensure_user_root(db_manager.find_user_by_id(user_id))

    def delete_student(self,user_id,confirm_name):
        user=db_manager.find_user_by_id(user_id)
        if not user or user["username"]!=confirm_name: raise ValueError("确认姓名不匹配")
        root=(STORAGE_ROOT/user["class_storage_key"]/user["storage_key"]).resolve(); archive=STORAGE_ROOT/"回收站"/"已删除学生"
        archive.mkdir(parents=True,exist_ok=True)
        destination=archive/f"{datetime.now():%Y%m%d%H%M%S}-{user['class_storage_key']}-{user['storage_key']}-{uuid.uuid4().hex[:8]}"
        moved=False
        if root.exists(): root.rename(destination); moved=True
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn)
        try:
            cursor.execute(f"UPDATE storage_users SET status='deleted',deleted_at={db_manager.now_expr()} WHERE id={ph}",(user_id,))
            cursor.execute(f"DELETE FROM user_sessions WHERE user_id={ph}",(user_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            if moved and destination.exists() and not root.exists():
                root.parent.mkdir(parents=True,exist_ok=True); destination.rename(root)
            raise
        finally:
            cursor.close(); conn.close()

    def announcements_for(self,class_id):
        ph=db_manager.placeholder(); return self.rows(f"SELECT id,title,content,created_at FROM announcements WHERE class_id={ph} ORDER BY id DESC LIMIT 1",(class_id,))

    def announcements(self):
        return self.rows("""SELECT a.id,a.class_id,a.title,a.content,a.created_at,c.name AS class_name
            FROM announcements a JOIN school_classes c ON c.id=a.class_id ORDER BY a.id DESC""")

    def create_announcement(self,class_id,title,content):
        if not str(title).strip() or not str(content).strip(): raise ValueError("标题和内容不能为空")
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn)
        cursor.execute(f"INSERT INTO announcements(class_id,title,content) VALUES({ph},{ph},{ph})",(class_id,str(title).strip(),str(content).strip())); conn.commit(); cursor.close(); conn.close()

    def replace_announcements(self, class_ids, title, content):
        if not isinstance(class_ids, list) or not class_ids: raise ValueError("请至少选择一个用户组")
        title, content = str(title).strip(), str(content).strip()
        if not title or not content: raise ValueError("标题和内容不能为空")
        ids = sorted({int(item) for item in class_ids})
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn, dictionary=True)
        try:
            marks=",".join([ph]*len(ids))
            cursor.execute(f"SELECT COUNT(*) AS total FROM school_classes WHERE id IN ({marks})",tuple(ids))
            if cursor.fetchone()["total"] != len(ids): raise ValueError("用户组不存在")
            cursor.execute(f"DELETE FROM announcements WHERE class_id IN ({marks})",tuple(ids))
            cursor.executemany(f"INSERT INTO announcements(class_id,title,content) VALUES({ph},{ph},{ph})",[(item,title,content) for item in ids])
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            cursor.close(); conn.close()

    def add_report(self,user_id,content):
        content=str(content).strip()
        if not content: raise ValueError("汇报内容不能为空")
        ph=db_manager.placeholder(); conn=db_manager.get_connection(); cursor=db_manager.cursor(conn)
        cursor.execute(f"INSERT INTO student_reports(user_id,content) VALUES({ph},{ph})",(user_id,content)); conn.commit(); cursor.close(); conn.close()

    def reports(self, class_id=None, day=None):
        ph=db_manager.placeholder(); where=[]; params=[]
        if class_id: where.append(f"u.class_id={ph}"); params.append(class_id)
        if day: where.append(f"DATE(r.created_at)={ph}"); params.append(day)
        suffix=(" WHERE "+" AND ".join(where)) if where else ""
        return self.rows("""SELECT r.id,r.content,r.status,r.created_at,u.username,u.class_id,c.name AS class_name FROM student_reports r
            JOIN storage_users u ON u.id=r.user_id JOIN school_classes c ON c.id=u.class_id"""+suffix+" ORDER BY r.id DESC",tuple(params))

    def reports_page(self, class_id=None, day=None, page=1, page_size=20):
        """Return reports plus paging metadata for the administrator table."""
        ph=db_manager.placeholder(); where=[]; params=[]
        if class_id: where.append(f"u.class_id={ph}"); params.append(class_id)
        if day: where.append(f"DATE(r.created_at)={ph}"); params.append(day)
        suffix=(" WHERE "+" AND ".join(where)) if where else ""
        conn=db_manager.get_connection(); count_cursor=db_manager.cursor(conn)
        count_cursor.execute("SELECT COUNT(*) FROM student_reports r JOIN storage_users u ON u.id=r.user_id"+suffix,tuple(params))
        total=int(count_cursor.fetchone()[0]); count_cursor.close()
        total_pages=max(1,(total+page_size-1)//page_size); page=min(max(1,page),total_pages)
        cursor=db_manager.cursor(conn,dictionary=True)
        cursor.execute("""SELECT r.id,r.content,r.status,r.created_at,u.username,u.class_id,c.name AS class_name FROM student_reports r
            JOIN storage_users u ON u.id=r.user_id JOIN school_classes c ON c.id=u.class_id"""+suffix+
            f" ORDER BY r.id DESC LIMIT {ph} OFFSET {ph}",tuple(params+[page_size,(page-1)*page_size]))
        items=[dict(row) for row in cursor.fetchall()]
        cursor.close(); conn.close()
        return {"items":items,"total":total,"page":page,"page_size":page_size,"total_pages":total_pages}


school_service=SchoolService()
