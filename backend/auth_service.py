import uuid
from datetime import datetime, timedelta

from .database import db_manager


class AuthService:
    SESSION_DAYS = 7
    MAX_LOGIN_FAILURES = 5
    LOGIN_BLOCK_HOURS = 5

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

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def login_attempt_status(self, device_key: str):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn, dictionary=True)
        cursor.execute(
            f"SELECT failed_count, blocked_until FROM login_attempts WHERE device_key = {ph}",
            (device_key,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return {"blocked": False, "failed_count": 0, "blocked_until": None}

        blocked_until = self._parse_datetime(row["blocked_until"])
        blocked = bool(blocked_until and blocked_until > datetime.now())
        if blocked_until and not blocked:
            self.clear_login_failures(device_key)
            return {"blocked": False, "failed_count": 0, "blocked_until": None}
        return {
            "blocked": blocked,
            "failed_count": int(row["failed_count"] or 0),
            "blocked_until": blocked_until,
        }

    def record_login_failure(self, device_key: str):
        status = self.login_attempt_status(device_key)
        if status["blocked"]:
            return status

        failed_count = status["failed_count"] + 1
        blocked_until = None
        if failed_count >= self.MAX_LOGIN_FAILURES:
            blocked_until = datetime.now() + timedelta(hours=self.LOGIN_BLOCK_HOURS)

        ph = db_manager.placeholder()
        now = db_manager.now_expr()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        cursor.execute(
            f"SELECT device_key FROM login_attempts WHERE device_key = {ph}",
            (device_key,),
        )
        if cursor.fetchone():
            cursor.execute(
                f"""
                UPDATE login_attempts
                SET failed_count = {ph}, blocked_until = {ph}, updated_at = {now}
                WHERE device_key = {ph}
                """,
                (failed_count, blocked_until, device_key),
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO login_attempts
                    (device_key, failed_count, blocked_until, updated_at)
                VALUES ({ph}, {ph}, {ph}, {now})
                """,
                (device_key, failed_count, blocked_until),
            )
        conn.commit()
        cursor.close()
        conn.close()
        return {
            "blocked": blocked_until is not None,
            "failed_count": failed_count,
            "blocked_until": blocked_until,
        }

    def clear_login_failures(self, device_key: str):
        ph = db_manager.placeholder()
        conn = db_manager.get_connection()
        cursor = db_manager.cursor(conn)
        cursor.execute(
            f"DELETE FROM login_attempts WHERE device_key = {ph}",
            (device_key,),
        )
        conn.commit()
        cursor.close()
        conn.close()


auth_service = AuthService()
