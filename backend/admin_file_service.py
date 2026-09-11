import os
import shutil
import uuid
from pathlib import Path

from .admin_service import admin_service
from .config import RECYCLE_ROOT, STORAGE_ROOT
from .database import db_manager
from .file_service import file_service


class AdminFileService:
    """Dedicated private storage for administrators and controlled group sharing."""

    def _owner_name(self, admin_id):
        admin = admin_service.find_by_id(admin_id)
        if not admin:
            raise ValueError("管理员不存在")
        return file_service.normalize_storage_name(admin["username"])

    @staticmethod
    def _directory_base(base):
        directory = (base / "管理员文件").resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _owner_directory(self, base, admin_id, owner_name, create=True):
        """Return the username-based directory and migrate a legacy ID directory once."""
        directory = self._directory_base(base)
        named = (directory / file_service.normalize_storage_name(owner_name)).resolve()
        legacy = (directory / str(int(admin_id))).resolve()
        if named.parent != directory or legacy.parent != directory:
            raise ValueError("管理员文件目录无效")
        if legacy.exists() and legacy != named:
            if named.exists():
                if any(legacy.iterdir()):
                    raise FileExistsError(f"管理员文件目录冲突：{owner_name}")
                legacy.rmdir()
            else:
                shutil.move(str(legacy), str(named))
        if create:
            named.mkdir(parents=True, exist_ok=True)
        return named

    def root(self, admin_id):
        return self._owner_directory(STORAGE_ROOT, admin_id, self._owner_name(admin_id))

    def recycle_root(self, admin_id, create=True):
        return self._owner_directory(
            RECYCLE_ROOT, admin_id, self._owner_name(admin_id), create=create
        )

    def rename_owner_directories(self, admin_id, old_name, new_name):
        """Move storage and recycle directories when an administrator is renamed."""
        old_name = file_service.normalize_storage_name(old_name)
        new_name = file_service.normalize_storage_name(new_name)
        if old_name == new_name:
            return
        moved = []
        try:
            for base in (STORAGE_ROOT, RECYCLE_ROOT):
                directory = self._directory_base(base)
                old_root = self._owner_directory(base, admin_id, old_name, create=False)
                new_root = (directory / new_name).resolve()
                if new_root.parent != directory:
                    raise ValueError("管理员文件目录无效")
                if old_root.exists():
                    if new_root.exists():
                        raise FileExistsError(f"管理员文件目录冲突：{new_name}")
                    shutil.move(str(old_root), str(new_root))
                    moved.append((new_root, old_root))
        except Exception:
            for source, target in reversed(moved):
                if source.exists() and not target.exists():
                    shutil.move(str(source), str(target))
            raise

    def _path(self, admin_id, raw_path=""):
        relative = file_service.normalize_relative_path(raw_path)
        root = self.root(admin_id)
        target = (root / relative).resolve() if relative else root
        if target != root and root not in target.parents:
            raise ValueError("路径超出管理员文件目录")
        return target, relative

    def _entry(self, absolute, relative):
        stat = absolute.stat()
        if absolute.is_dir():
            folders = files = 0
            try:
                for child in absolute.iterdir():
                    if child.name == ".DS_Store":
                        continue
                    if child.is_dir():
                        folders += 1
                    elif child.is_file():
                        files += 1
            except OSError:
                pass
            size = file_service._directory_size(absolute)
            content = f"{folders} 个文件夹 · {files} 个文件"
        else:
            size = stat.st_size
            content = "--"
        from datetime import datetime, timezone
        from .file_service import format_size
        return {"name": absolute.name, "path": relative, "type": "folder" if absolute.is_dir() else "file",
                "size": size, "size_display": format_size(size), "content_display": content,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()}

    def list_entries(self, admin_id, path=""):
        target, relative = self._path(admin_id, path)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(relative)
        rows = [self._entry(child, f"{relative}/{child.name}".strip("/")) for child in target.iterdir() if child.name != ".DS_Store"]
        rows.sort(key=lambda item: (item["type"] != "folder", file_service._natural_sort_key(item["name"])))
        return {"path": relative, "entries": rows}

    def upload(self, admin_id, parent, uploaded_files, relatives):
        target, parent_rel = self._path(admin_id, parent)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(parent_rel)
        results = []
        for storage, raw_name in zip(uploaded_files, relatives):
            name = file_service.normalize_relative_path(raw_name)
            if not name:
                raise ValueError("文件路径无效")
            destination = (target / name).resolve()
            root = self.root(admin_id)
            if root not in destination.parents:
                raise ValueError("路径超出管理员文件目录")
            destination.parent.mkdir(parents=True, exist_ok=True)
            storage.save(str(destination))
            results.append({"path": f"{parent_rel}/{name}".strip("/"), "name": destination.name})
        return results

    def mkdir(self, admin_id, parent, name):
        target, parent_rel = self._path(admin_id, parent)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(parent_rel)
        child = (target / file_service.normalize_name(name)).resolve()
        if child.exists():
            raise FileExistsError(child.name)
        child.mkdir()
        return f"{parent_rel}/{child.name}".strip("/")

    def rename(self, admin_id, raw_path, name):
        source, relative = self._path(admin_id, raw_path)
        if not relative or not source.exists():
            raise ValueError("文件不存在或不能重命名根目录")
        target = (source.parent / file_service.normalize_name(name)).resolve()
        if target.exists() and target != source:
            raise FileExistsError(target.name)
        new_relative = str(target.relative_to(self.root(admin_id))).replace("\\", "/")
        source.rename(target)
        try:
            # A rename does not change ownership or access policy.  Keep the
            # existing group shares and only update their relative paths.
            self.rebase_shares(admin_id, relative, new_relative)
        except Exception:
            # Do not leave the filesystem and the share table pointing at
            # different names when a database update fails.
            target.rename(source)
            raise
        return new_relative

    def move(self, admin_id, paths, destination):
        dest, _ = self._path(admin_id, destination)
        if not dest.exists() or not dest.is_dir():
            raise FileNotFoundError(destination)
        moved = []
        for raw_path in paths:
            source, relative = self._path(admin_id, raw_path)
            if not relative or not source.exists():
                raise ValueError("文件不存在或不能移动根目录")
            target = (dest / source.name).resolve()
            if target == source.resolve():
                continue
            if target.exists() and target != source:
                raise FileExistsError(target.name)
            if source.is_dir() and source.resolve() in target.parents:
                raise ValueError("不能将文件夹移动到自身内部")
            source.rename(target)
            self.remove_shares(admin_id, relative, include_children=True)
            moved.append(str(target.relative_to(self.root(admin_id))).replace("\\", "/"))
        return moved

    def delete(self, admin_id, paths):
        moved = []
        for raw_path in paths:
            target, relative = self._path(admin_id, raw_path)
            if not relative or not target.exists():
                raise ValueError("文件不存在或不能删除根目录")
            self.remove_shares(admin_id, relative, include_children=True)
            stored_name = uuid.uuid4().hex
            recycle_root = self.recycle_root(admin_id)
            destination = recycle_root / stored_name
            item_type = "folder" if target.is_dir() else "file"
            item_name = target.name
            shutil.move(str(target), str(destination))
            conn = db_manager.get_connection(); cursor = db_manager.cursor(conn); ph = db_manager.placeholder()
            try:
                cursor.execute(
                    f"INSERT INTO admin_recycle_items (admin_id, original_path, stored_name, item_name, item_type, deleted_at) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {db_manager.now_expr()})",
                    (admin_id, relative, stored_name, item_name, item_type),
                )
                conn.commit(); moved.append({"id": cursor.lastrowid, "path": relative, "name": item_name})
            except Exception:
                conn.rollback()
                if destination.exists() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(destination), str(target))
                raise
            finally:
                cursor.close(); conn.close()
        return moved

    def list_recycle_items(self):
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute("SELECT r.id,r.admin_id,r.original_path,r.stored_name,r.item_name,r.item_type,r.deleted_at,a.username AS admin_name FROM admin_recycle_items r JOIN admin_users a ON a.id=r.admin_id ORDER BY r.id DESC")
        rows = cursor.fetchall(); cursor.close(); conn.close()
        return rows

    def restore_recycle_item(self, item_id):
        ph = db_manager.placeholder(); conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(f"SELECT id,admin_id,original_path,stored_name FROM admin_recycle_items WHERE id={ph}", (item_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close(); conn.close(); raise FileNotFoundError(str(item_id))
        recycle_root = self.recycle_root(row["admin_id"], create=False)
        source = recycle_root / row["stored_name"]
        target, _ = self._path(row["admin_id"], row["original_path"])
        if not source.exists():
            cursor.close(); conn.close(); raise FileNotFoundError(row["original_path"])
        if target.exists():
            cursor.close(); conn.close(); raise FileExistsError(row["original_path"])
        target.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(source), str(target))
        try:
            cursor.execute(f"DELETE FROM admin_recycle_items WHERE id={ph}", (item_id,)); conn.commit()
        except Exception:
            conn.rollback()
            if target.exists() and not source.exists(): shutil.move(str(target), str(source))
            raise
        finally:
            cursor.close(); conn.close()
        return row["original_path"]

    def target(self, admin_id, raw_path):
        target, relative = self._path(admin_id, raw_path)
        if not relative or not target.exists():
            raise FileNotFoundError(relative)
        return target

    def set_shares(self, admin_id, paths, class_ids):
        if not paths:
            raise ValueError("请选择要共享的文件")
        ids = sorted({int(item) for item in class_ids if str(item).strip()})
        ph = db_manager.placeholder()
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn)
        try:
            for raw_path in paths:
                target, relative = self._path(admin_id, raw_path)
                if not relative or not target.exists():
                    raise FileNotFoundError(relative)
                cursor.execute(f"DELETE FROM admin_file_shares WHERE admin_id={ph} AND relative_path={ph}", (admin_id, relative))
                for class_id in ids:
                    cursor.execute(f"INSERT INTO admin_file_shares(admin_id,relative_path,class_id) VALUES({ph},{ph},{ph})", (admin_id, relative, class_id))
            conn.commit()
        finally:
            cursor.close(); conn.close()

    def remove_shares(self, admin_id, relative, include_children=False):
        ph = db_manager.placeholder(); conn = db_manager.get_connection(); cursor = db_manager.cursor(conn)
        try:
            if include_children:
                cursor.execute(f"DELETE FROM admin_file_shares WHERE admin_id={ph} AND (relative_path={ph} OR relative_path LIKE {ph})", (admin_id, relative, f"{relative}/%"))
            else:
                cursor.execute(f"DELETE FROM admin_file_shares WHERE admin_id={ph} AND relative_path={ph}", (admin_id, relative))
            conn.commit()
        finally:
            cursor.close(); conn.close()

    def rebase_shares(self, admin_id, old_relative, new_relative):
        """Update direct and descendant share paths after an item is renamed."""
        ph = db_manager.placeholder()
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        try:
            # A target cannot exist on disk during rename, so any share records
            # already using the target prefix are stale records from an older
            # deleted item. Remove those first to avoid a unique-key collision.
            cursor.execute(
                f"DELETE FROM admin_file_shares WHERE admin_id={ph} "
                f"AND (relative_path={ph} OR relative_path LIKE {ph})",
                (admin_id, new_relative, f"{new_relative}/%"),
            )
            cursor.execute(
                f"SELECT id,relative_path FROM admin_file_shares WHERE admin_id={ph} "
                f"AND (relative_path={ph} OR relative_path LIKE {ph})",
                (admin_id, old_relative, f"{old_relative}/%"),
            )
            rows = cursor.fetchall()
            for row in rows:
                suffix = row["relative_path"][len(old_relative):]
                cursor.execute(
                    f"UPDATE admin_file_shares SET relative_path={ph} WHERE id={ph}",
                    (f"{new_relative}{suffix}", row["id"]),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close(); conn.close()

    def shares_for_admin(self, admin_id):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        aggregate = "GROUP_CONCAT(c.name, '、')" if db_manager.is_sqlite else "GROUP_CONCAT(c.name ORDER BY c.name SEPARATOR '、')"
        cursor.execute(f"SELECT relative_path,{aggregate} AS group_names FROM admin_file_shares s JOIN school_classes c ON c.id=s.class_id WHERE admin_id={ph} GROUP BY relative_path", (admin_id,))
        rows = cursor.fetchall(); cursor.close(); conn.close()
        return {row["relative_path"]: row["group_names"] for row in rows}

    def share_ids_for_admin(self, admin_id):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(f"SELECT relative_path,class_id FROM admin_file_shares WHERE admin_id={ph}", (admin_id,))
        rows = cursor.fetchall(); cursor.close(); conn.close()
        result = {}
        for row in rows:
            result.setdefault(row["relative_path"], []).append(row["class_id"])
        return result

    def shared_for_user(self, class_id):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(f"SELECT s.id,s.admin_id,s.relative_path,s.created_at,a.username AS admin_name FROM admin_file_shares s JOIN admin_users a ON a.id=s.admin_id WHERE s.class_id={ph} AND a.status='active' ORDER BY s.id DESC", (class_id,))
        rows = cursor.fetchall(); cursor.close(); conn.close()
        items=[]
        for row in rows:
            try:
                target = self.target(row["admin_id"], row["relative_path"])
                item = self._entry(target, row["relative_path"])
                item.update({"share_id":row["id"], "admin_name":row["admin_name"]})
                items.append(item)
            except FileNotFoundError:
                self.remove_shares(row["admin_id"], row["relative_path"])
        return items

    def shared_target(self, share_id, class_id):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection(); cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(f"SELECT admin_id,relative_path FROM admin_file_shares WHERE id={ph} AND class_id={ph}", (share_id, class_id))
        row = cursor.fetchone(); cursor.close(); conn.close()
        if not row:
            raise FileNotFoundError("共享文件不存在")
        return self.target(row["admin_id"], row["relative_path"])


admin_file_service = AdminFileService()
