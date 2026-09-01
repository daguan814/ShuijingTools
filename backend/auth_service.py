import uuid
from datetime import datetime, timedelta

from .database import db_manager


class AuthService:
    SESSION_DAYS = 7

    def public_user(self, user):
        if not user:
            return None
        return {
            "id": user["id"],
            "username": user["username"],
        }

    def login(self, username: str):
        return db_manager.find_user_by_username(username.strip())

    def create_session(self, user_id: int) -> str:
        token = uuid.uuid4().hex + uuid.uuid4().hex
        expires_at = datetime.now() + timedelta(days=self.SESSION_DAYS)
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        ph = db_manager.placeholder()
        now = db_manager.now_expr()
        cursor.execute(
            f"""
            INSERT INTO user_sessions (token, user_id, created_at, expires_at)
            VALUES ({ph}, {ph}, {now}, {ph})
            """,
            (token, user_id, expires_at),
        )
        conn.commit()
        cursor.close()
        conn.close()
        return token

    def get_user_by_token(self, token: str):
        if not token:
            return None
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn, dictionary=True)
        ph = db_manager.placeholder()
        now = db_manager.now_expr()
        cursor.execute(
            f"""
            SELECT u.id, u.username, u.storage_key
            FROM user_sessions s
            JOIN storage_users u ON u.id = s.user_id
            WHERE s.token = {ph} AND s.expires_at > {now}
            LIMIT 1
            """,
            (token,),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                f"UPDATE user_sessions SET last_seen_at = {now} WHERE token = {ph}",
                (token,),
            )
            conn.commit()
        cursor.close()
        conn.close()
        return row

    def revoke_session(self, token: str):
        if not token:
            return
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        ph = db_manager.placeholder()
        cursor.execute(f"DELETE FROM user_sessions WHERE token = {ph}", (token,))
        conn.commit()
        cursor.close()
        conn.close()


auth_service = AuthService()
