from datetime import datetime
from app.db.database import db_manager


class TextService:
    def __init__(self):
        pass

    def get_connection(self):
        """Get database connection from db_manager."""
        return db_manager.get_connection()

    def get_all_texts(self):
        """Get all saved texts."""
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT * FROM texts WHERE is_active = 1 ORDER BY id DESC')
        texts = c.fetchall()
        conn.close()

        result = []
        for text in texts:
            result.append((
                text['id'],
                text['content'],
                text['created_at'],
                text.get('is_favorite', 0),
                text.get('favorite_group', 1)
            ))

        return result

    def get_favorite_texts(self):
        """Get active favorite texts."""
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT * FROM texts WHERE is_active = 1 AND is_favorite = 1 ORDER BY id DESC')
        texts = c.fetchall()
        conn.close()

        result = []
        for text in texts:
            result.append((
                text['id'],
                text['content'],
                text['created_at'],
                text.get('is_favorite', 0),
                text.get('favorite_group', 1)
            ))
        return result

    def get_deleted_texts(self):
        """Get deleted texts."""
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT * FROM texts WHERE is_active = 0 AND trash_hidden = 0 ORDER BY id DESC')
        texts = c.fetchall()
        conn.close()

        result = []
        for text in texts:
            result.append((text['id'], text['content'], text['created_at']))

        return result

    def add_text(self, content):
        """Add new text."""
        conn = self.get_connection()
        c = conn.cursor()
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('INSERT INTO texts (content, created_at) VALUES (%s, %s)', (content, local_time))
        conn.commit()
        text_id = c.lastrowid
        conn.close()
        return text_id

    def delete_text(self, text_id):
        """Delete a text."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute(
            'UPDATE texts SET is_active = 0, trash_hidden = 0, is_favorite = 0, favorite_group = 1 WHERE id = %s AND is_active = 1',
            (text_id,)
        )
        conn.commit()
        affected_rows = c.rowcount
        conn.close()
        return affected_rows > 0

    def toggle_favorite(self, text_id):
        """Toggle favorite status for an active text and return new state."""
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute('SELECT is_favorite, favorite_group FROM texts WHERE id = %s AND is_active = 1', (text_id,))
        row = c.fetchone()
        if row is None:
            conn.close()
            return None
        new_state = 0 if int(row.get('is_favorite', 0)) == 1 else 1
        favorite_group = int(row.get('favorite_group', 1) or 1)
        if favorite_group not in (1, 2, 3):
            favorite_group = 1
        c = conn.cursor()
        c.execute(
            'UPDATE texts SET is_favorite = %s, favorite_group = %s WHERE id = %s AND is_active = 1',
            (new_state, favorite_group, text_id)
        )
        conn.commit()
        conn.close()
        return new_state == 1

    def move_favorite_group(self, text_id, group_id):
        if group_id not in (1, 2, 3):
            return None
        conn = self.get_connection()
        c = conn.cursor(dictionary=True)
        c.execute(
            'SELECT id, favorite_group FROM texts WHERE id = %s AND is_active = 1 AND is_favorite = 1',
            (text_id,)
        )
        row = c.fetchone()
        if row is None:
            conn.close()
            return None

        # Same group should be treated as a successful no-op.
        if int(row.get('favorite_group', 1) or 1) == group_id:
            conn.close()
            return True

        c = conn.cursor()
        c.execute(
            'UPDATE texts SET favorite_group = %s WHERE id = %s AND is_active = 1 AND is_favorite = 1',
            (group_id, text_id)
        )
        conn.commit()
        conn.close()
        return True

    def restore_text(self, text_id):
        """Restore a deleted text."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute(
            'UPDATE texts SET is_active = 1, trash_hidden = 0 WHERE id = %s AND is_active = 0',
            (text_id,)
        )
        conn.commit()
        affected_rows = c.rowcount
        conn.close()
        return affected_rows > 0

    def purge_deleted_texts(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('UPDATE texts SET trash_hidden = 1 WHERE is_active = 0 AND trash_hidden = 0')
        conn.commit()
        hidden_rows = c.rowcount
        conn.close()
        return hidden_rows

    def purge_deleted_text(self, text_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('UPDATE texts SET trash_hidden = 1 WHERE id = %s AND is_active = 0 AND trash_hidden = 0', (text_id,))
        conn.commit()
        hidden_rows = c.rowcount
        conn.close()
        return hidden_rows > 0

    def add_log(self, action, text_id=None, content=None, client_ip=None):
        """Add an operation log entry."""
        conn = self.get_connection()
        c = conn.cursor()
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            'INSERT INTO operation_logs (action, text_id, content, client_ip, created_at) '
            'VALUES (%s, %s, %s, %s, %s)',
            (action, text_id, content, client_ip, local_time)
        )
        conn.commit()
        conn.close()


text_service = TextService()
