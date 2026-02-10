from datetime import datetime
from db.database import db_manager


class TrashService:
    def __init__(self):
        pass

    def get_connection(self):
        return db_manager.get_connection()

    def add_file(self, original_path, trash_path, size_bytes):
        conn = self.get_connection()
        c = conn.cursor()
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            'INSERT INTO file_trash (original_path, trash_path, size, deleted_at) '
            'VALUES (%s, %s, %s, %s)',
            (original_path, trash_path, int(size_bytes), local_time)
        )
        conn.commit()
        file_id = c.lastrowid
        conn.close()
        return file_id

    def list_files(self):
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT * FROM file_trash WHERE is_hidden = 0 ORDER BY id DESC')
        rows = c.fetchall()
        conn.close()
        return rows

    def get_file(self, file_id):
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT * FROM file_trash WHERE id = %s AND is_hidden = 0', (file_id,))
        row = c.fetchone()
        conn.close()
        return row

    def remove_file(self, file_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('UPDATE file_trash SET is_hidden = 1 WHERE id = %s AND is_hidden = 0', (file_id,))
        conn.commit()
        conn.close()

    def clear_files(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('UPDATE file_trash SET is_hidden = 1 WHERE is_hidden = 0')
        conn.commit()
        conn.close()


trash_service = TrashService()
