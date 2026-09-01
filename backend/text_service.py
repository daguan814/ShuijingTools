from datetime import datetime

from .database import db_manager


class TextService:
    def list_notes(self, user_id: int):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(
            f"""
            SELECT id, content, created_at
            FROM text_notes
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

    def add_note(self, user_id: int, content: str) -> int:
        ph = db_manager.placeholder()
        now = db_manager.now_expr()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        cursor.execute(
            f"""
            INSERT INTO text_notes (user_id, content, created_at)
            VALUES ({ph}, {ph}, {now})
            """,
            (user_id, content),
        )
        conn.commit()
        note_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return note_id

    def delete_note(self, user_id: int, note_id: int) -> bool:
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        cursor.execute(
            f"""
            DELETE FROM text_notes
            WHERE id = {ph} AND user_id = {ph}
            """,
            (note_id, user_id),
        )
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        return affected > 0


text_service = TextService()
