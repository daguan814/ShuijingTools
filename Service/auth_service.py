import uuid
from datetime import datetime, timedelta

from db.database import db_manager


class AuthService:
    MAX_FAILS = 10
    BAN_DAYS = 7
    SESSION_DAYS = 7

    def get_connection(self):
        return db_manager.get_connection()

    def verify_passcode(self, passcode: str) -> bool:
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT passcode FROM auth_config WHERE id = 1')
        row = c.fetchone()
        conn.close()
        if not row:
            return False
        return str(row[0]) == str(passcode)

    def verify_passcode_with_ip(self, passcode: str, client_ip: str) -> dict:
        ip = (client_ip or '').strip() or 'unknown'
        now = datetime.now()
        conn = self.get_connection()
        c = conn.cursor()

        c.execute('SELECT fail_count, banned_until FROM auth_ip_guard WHERE ip = %s', (ip,))
        guard = c.fetchone()
        fail_count = int(guard[0]) if guard and guard[0] is not None else 0
        banned_until = guard[1] if guard else None

        if banned_until and banned_until > now:
            conn.close()
            return {'ok': False, 'banned': True, 'banned_until': banned_until}

        if banned_until and banned_until <= now:
            fail_count = 0

        c.execute('SELECT passcode FROM auth_config WHERE id = 1')
        row = c.fetchone()
        valid = bool(row) and str(row[0]) == str(passcode)

        if valid:
            c.execute(
                """
                INSERT INTO auth_ip_guard (ip, fail_count, banned_until, updated_at)
                VALUES (%s, 0, NULL, NOW())
                ON DUPLICATE KEY UPDATE fail_count = 0, banned_until = NULL, updated_at = NOW()
                """,
                (ip,),
            )
            conn.commit()
            conn.close()
            return {'ok': True, 'banned': False}

        new_fail_count = fail_count + 1
        new_banned_until = now + timedelta(days=self.BAN_DAYS) if new_fail_count >= self.MAX_FAILS else None
        c.execute(
            """
            INSERT INTO auth_ip_guard (ip, fail_count, banned_until, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE fail_count = VALUES(fail_count), banned_until = VALUES(banned_until), updated_at = NOW()
            """,
            (ip, new_fail_count, new_banned_until),
        )
        conn.commit()
        conn.close()
        return {
            'ok': False,
            'banned': bool(new_banned_until),
            'banned_until': new_banned_until,
            'fail_count': new_fail_count,
        }

    def create_session(self, client_ip: str) -> str:
        token = uuid.uuid4().hex + uuid.uuid4().hex
        ip = (client_ip or '').strip() or None
        conn = self.get_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO auth_sessions (token, client_ip, is_active, created_at, expires_at)
            VALUES (%s, %s, 1, NOW(), DATE_ADD(NOW(), INTERVAL %s DAY))
            """,
            (token, ip, self.SESSION_DAYS),
        )
        conn.commit()
        conn.close()
        return token

    def verify_session(self, token: str) -> bool:
        if not token:
            return False
        conn = self.get_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT token FROM auth_sessions
            WHERE token = %s AND is_active = 1 AND expires_at > NOW()
            LIMIT 1
            """,
            (token,),
        )
        row = c.fetchone()
        conn.close()
        return bool(row)


auth_service = AuthService()
