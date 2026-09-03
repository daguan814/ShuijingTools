from datetime import datetime, timedelta

from .database import db_manager


class LogService:
    ACTION_PREFIXES = {
        "upload": ("上传%",),
        "create": ("新建%",),
        "download": ("下载%", "批量下载%"),
        "move": ("移动%",),
        "delete": ("删除%",),
        "restore": ("恢复%",),
    }

    def _filters(self, user_id, action=None, day=None):
        ph = db_manager.placeholder()
        clauses = [f"user_id = {ph}"]
        params = [user_id]

        prefixes = self.ACTION_PREFIXES.get(action, ())
        if prefixes:
            clauses.append("(" + " OR ".join(f"content LIKE {ph}" for _ in prefixes) + ")")
            params.extend(prefixes)

        if day:
            start = datetime.strptime(day, "%Y-%m-%d")
            clauses.append(f"created_at >= {ph} AND created_at < {ph}")
            params.extend((start, start + timedelta(days=1)))

        return " AND ".join(clauses), params

    def list_logs(self, user_id: int, action=None, day=None, page=1, page_size=20):
        ph = db_manager.placeholder()
        where, params = self._filters(user_id, action, day)
        conn = db_manager.get_connection()
        count_cursor = db_manager.cursor(conn)
        count_cursor.execute(f"SELECT COUNT(*) FROM user_logs WHERE {where}", tuple(params))
        total = int(count_cursor.fetchone()[0])
        count_cursor.close()
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)

        cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(
            f"""
            SELECT id, content, created_at
            FROM user_logs
            WHERE {where}
            ORDER BY id DESC
            LIMIT {ph} OFFSET {ph}
            """,
            tuple(params + [page_size, (page - 1) * page_size]),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {
            "items": [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def add_log(self, user_id: int, content: str) -> int:
        ph = db_manager.placeholder()
        now = db_manager.now_expr()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        cursor.execute(
            f"""
            INSERT INTO user_logs (user_id, content, created_at)
            VALUES ({ph}, {ph}, {now})
            """,
            (user_id, content),
        )
        conn.commit()
        log_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return log_id

log_service = LogService()
