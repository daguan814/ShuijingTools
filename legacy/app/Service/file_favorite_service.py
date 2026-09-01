from datetime import datetime

from app.db.database import db_manager


class FileFavoriteService:
    def get_connection(self):
        return db_manager.get_connection()

    def list_paths(self):
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT path, created_at FROM file_favorites ORDER BY created_at DESC')
        rows = c.fetchall()
        conn.close()
        return rows

    def set_favorite(self, path, enabled):
        conn = self.get_connection()
        c = conn.cursor()
        if enabled:
            local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                'INSERT INTO file_favorites (path, created_at) VALUES (%s, %s) '
                'ON DUPLICATE KEY UPDATE path = path',
                (path, local_time),
            )
        else:
            c.execute('DELETE FROM file_favorites WHERE path = %s', (path,))
        conn.commit()
        conn.close()

    def remove(self, path):
        self.set_favorite(path, False)


file_favorite_service = FileFavoriteService()
