import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import mysql.connector
from mysql.connector import pooling

from .config import (
    DB_DRIVER,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    DEFAULT_USERS,
    SQLITE_DB_PATH,
)


class DatabaseManager:
    """Database manager supporting MySQL (default) and SQLite for local preview."""

    def __init__(self):
        self.driver = DB_DRIVER
        self.sqlite_path = Path(SQLITE_DB_PATH)
        self._pool = None

    @property
    def is_sqlite(self) -> bool:
        return self.driver == "sqlite"

    def placeholder(self) -> str:
        return "?" if self.is_sqlite else "%s"

    def now_expr(self) -> str:
        return "CURRENT_TIMESTAMP" if self.is_sqlite else "NOW()"

    def cursor(self, conn, dictionary=False):
        if self.is_sqlite:
            return conn.cursor()
        return conn.cursor(dictionary=dictionary)

    def init_pool(self, pool_size=5):
        if self.is_sqlite:
            return None
        if self._pool is not None:
            return self._pool
        self._pool = pooling.MySQLConnectionPool(
            pool_name="shuijing_storage_pool",
            pool_size=pool_size,
            pool_reset_session=True,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connection_timeout=5,
        )
        return self._pool

    def get_connection(self):
        if self.is_sqlite:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.sqlite_path), timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        return self.init_pool().get_connection()

    def _create_database(self):
        if self.is_sqlite:
            return
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            connection_timeout=5,
        )
        cursor = conn.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
        cursor.close()
        conn.close()

    def init_db(self):
        """Create the database, users, and session tables."""
        self._create_database()
        conn = self.get_connection()
        cursor = conn.cursor()

        if self.is_sqlite:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    storage_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
                ON user_sessions (user_id)
                """
            )
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(64) NOT NULL UNIQUE,
                    storage_key VARCHAR(64) NOT NULL UNIQUE,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token VARCHAR(128) PRIMARY KEY,
                    user_id INT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    last_seen_at DATETIME NULL,
                    INDEX idx_user_sessions_user_id (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        insert_sql = (
            """
            INSERT OR IGNORE INTO storage_users
                (username, storage_key, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """
            if self.is_sqlite
            else """
            INSERT IGNORE INTO storage_users
                (username, storage_key, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            """
        )
        for username in DEFAULT_USERS:
            storage_key = uuid.uuid4().hex
            cursor.execute(insert_sql, (username, storage_key, now, now))

        conn.commit()
        cursor.close()
        conn.close()

        # Ensure every configured user has a storage directory.
        from .file_service import file_service

        for username in DEFAULT_USERS:
            user = self.find_user_by_username(username)
            if user:
                file_service.ensure_user_root(user)

    def find_user_by_username(self, username: str):
        if not username:
            return None
        ph = self.placeholder()
        conn = self.get_connection()
        cursor = self.cursor(conn, dictionary=True)
        cursor.execute(
            f"SELECT id, username, storage_key FROM storage_users "
            f"WHERE username = {ph} LIMIT 1",
            (username,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row

    def find_user_by_id(self, user_id: int):
        ph = self.placeholder()
        conn = self.get_connection()
        cursor = self.cursor(conn, dictionary=True)
        cursor.execute(
            f"SELECT id, username, storage_key FROM storage_users "
            f"WHERE id = {ph} LIMIT 1",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row


db_manager = DatabaseManager()
