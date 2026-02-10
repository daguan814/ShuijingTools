from db.database import db_manager


class AuthService:
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


auth_service = AuthService()
