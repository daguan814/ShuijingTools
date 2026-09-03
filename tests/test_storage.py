import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path


class StorageIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        root = Path(cls.temp_dir.name)
        os.environ.update(
            {
                "DB_DRIVER": "sqlite",
                "SQLITE_DB_PATH": str(root / "test.db"),
                "STORAGE_ROOT": str(root / "storage"),
                "SECRET_KEY": "test-secret-key",
            }
        )
        from backend.app import create_app

        cls.app = create_app()
        cls.app.testing = True

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def login(self, username="shuijing"):
        response = self.client.post(
            "/api/auth/login", json={"username": username}
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json['token']}"}

    def setUp(self):
        self.client = self.app.test_client()

    def test_storage_uses_username_and_single_file_downloads_directly(self):
        headers = self.login()
        response = self.client.post(
            "/api/files/upload",
            headers=headers,
            data={
                "path": "",
                "files": (io.BytesIO(b"hello"), "hello.txt"),
                "relative_paths": "hello.txt",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)

        storage_root = Path(os.environ["STORAGE_ROOT"])
        self.assertEqual((storage_root / "shuijing" / "hello.txt").read_bytes(), b"hello")

        prepared = self.client.post(
            "/api/files/download/prepare",
            headers=headers,
            json={"paths": ["hello.txt"], "base": ""},
        )
        downloaded = self.client.get(prepared.json["url"])
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.data, b"hello")
        self.assertIn("hello.txt", downloaded.headers["Content-Disposition"])
        downloaded.close()

    def test_multiple_files_download_as_zip_and_users_are_isolated(self):
        headers = self.login()
        user_root = Path(os.environ["STORAGE_ROOT"]) / "shuijing"
        user_root.mkdir(parents=True, exist_ok=True)
        (user_root / "one.txt").write_text("one")
        (user_root / "two.txt").write_text("two")

        prepared = self.client.post(
            "/api/files/download/prepare",
            headers=headers,
            json={"paths": ["one.txt", "two.txt"], "base": ""},
        )
        downloaded = self.client.get(prepared.json["url"])
        self.assertEqual(downloaded.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(downloaded.data)) as archive:
            self.assertEqual(archive.read("one.txt"), b"one")
            self.assertEqual(archive.read("two.txt"), b"two")
        downloaded.close()

        txt_headers = self.login("txt")
        denied = self.client.post(
            "/api/files/download/prepare",
            headers=txt_headers,
            json={"paths": ["one.txt"], "base": ""},
        )
        self.assertEqual(denied.status_code, 404)

if __name__ == "__main__":
    unittest.main()
