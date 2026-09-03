import hmac
import shutil
import uuid

from .config import RECYCLE_BIN_PASSWORD, RECYCLE_ROOT
from .database import db_manager
from .file_service import file_service, format_size


class RecycleService:
    def user_recycle_root(self, user):
        root = RECYCLE_ROOT / file_service.normalize_username(user["username"])
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def move_to_recycle(self, user, relative_path):
        original_path = file_service.normalize_relative_path(relative_path)
        if not original_path:
            raise ValueError("cannot delete user root")

        source = file_service.resolve_user_path(user, original_path)
        if not source.exists():
            raise FileNotFoundError(original_path)

        stored_name = uuid.uuid4().hex
        destination = self.user_recycle_root(user) / stored_name
        item_type = "folder" if source.is_dir() else "file"
        item_name = source.name
        shutil.move(str(source), str(destination))

        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        ph = db_manager.placeholder()
        now = db_manager.now_expr()
        try:
            cursor.execute(
                f"""
                INSERT INTO recycle_items
                    (user_id, original_path, stored_name, item_name, item_type, deleted_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {now})
                """,
                (user["id"], original_path, stored_name, item_name, item_type),
            )
            conn.commit()
            item_id = cursor.lastrowid
        except Exception:
            conn.rollback()
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            raise
        finally:
            cursor.close()
            conn.close()

        return {
            "id": item_id,
            "path": original_path,
            "name": item_name,
            "type": item_type,
        }

    def list_items(self, user):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(
            f"""
            SELECT id, original_path, stored_name, item_name, item_type, deleted_at
            FROM recycle_items
            WHERE user_id = {ph}
            ORDER BY id DESC
            """,
            (user["id"],),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        root = self.user_recycle_root(user)
        items = []
        for row in rows:
            stored_path = root / row["stored_name"]
            size = stored_path.stat().st_size if stored_path.exists() and stored_path.is_file() else None
            items.append(
                {
                    "id": row["id"],
                    "name": row["item_name"],
                    "original_path": row["original_path"],
                    "type": row["item_type"],
                    "deleted_at": row["deleted_at"],
                    "size": size,
                    "size_display": format_size(size) if size is not None else "--",
                }
            )
        return items

    def restore(self, user, item_id, password):
        if not RECYCLE_BIN_PASSWORD:
            raise RuntimeError("recycle password is not configured")
        if not hmac.compare_digest(str(password), RECYCLE_BIN_PASSWORD):
            raise PermissionError("invalid recycle password")

        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(
            f"""
            SELECT id, original_path, stored_name, item_name, item_type
            FROM recycle_items
            WHERE id = {ph} AND user_id = {ph}
            LIMIT 1
            """,
            (item_id, user["id"]),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            raise FileNotFoundError(str(item_id))

        source = self.user_recycle_root(user) / row["stored_name"]
        destination = file_service.resolve_user_path(user, row["original_path"])
        if not source.exists():
            cursor.close()
            conn.close()
            raise FileNotFoundError(row["original_path"])
        if destination.exists():
            cursor.close()
            conn.close()
            raise FileExistsError(row["original_path"])

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        try:
            cursor.execute(
                f"DELETE FROM recycle_items WHERE id = {ph} AND user_id = {ph}",
                (item_id, user["id"]),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            if destination.exists() and not source.exists():
                shutil.move(str(destination), str(source))
            raise
        finally:
            cursor.close()
            conn.close()

        return row["original_path"]


recycle_service = RecycleService()
