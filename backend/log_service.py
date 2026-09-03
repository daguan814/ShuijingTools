from .database import db_manager


class LogService:
    def list_logs(self, user_id: int):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(
            f"""
            SELECT id, content, created_at
            FROM user_logs
            WHERE user_id = {ph}
            ORDER BY id DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

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

    def delete_log(self, user_id: int, log_id: int) -> bool:
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        cursor.execute(
            f"DELETE FROM user_logs WHERE id = {ph} AND user_id = {ph}",
            (log_id, user_id),
        )
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        return affected > 0


log_service = LogService()
