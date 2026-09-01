import io
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .config import STORAGE_ROOT


def format_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


class FileService:
    """Filesystem storage scoped to one user's storage directory."""

    def ensure_user_root(self, user):
        root = STORAGE_ROOT / user["storage_key"]
        root.mkdir(parents=True, exist_ok=True)
        return root

    def user_root(self, user) -> Path:
        return self.ensure_user_root(user).resolve()

    @staticmethod
    def normalize_relative_path(raw: str) -> str:
        if raw is None:
            raw = ""
        text = str(raw).replace("\\", "/")
        if "\x00" in text:
            raise ValueError("invalid path")
        if text.startswith("/") or PurePosixPath(text).is_absolute():
            raise ValueError("absolute paths are not allowed")

        parts = []
        for part in text.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                raise ValueError("parent traversal is not allowed")
            parts.append(part)
        return "/".join(parts)

    @staticmethod
    def normalize_name(raw: str) -> str:
        if raw is None:
            raise ValueError("name is required")
        name = str(raw).strip()
        if not name or name in (".", ".."):
            raise ValueError("invalid name")
        if "/" in name or "\\" in name or "\x00" in name:
            raise ValueError("invalid name")
        return name

    def resolve_user_path(self, user, relative_path: str) -> Path:
        root = self.user_root(user)
        rel = self.normalize_relative_path(relative_path)
        target = (root / rel).resolve() if rel else root
        if target != root and root not in target.parents:
            raise ValueError("path escapes user storage")
        return target

    def relative_path(self, user, absolute: Path) -> str:
        root = self.user_root(user)
        absolute = Path(absolute)
        if absolute == root:
            return ""
        return str(absolute.relative_to(root)).replace("\\", "/")

    @staticmethod
    def _directory_size(path: Path) -> int:
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                try:
                    if not file_path.is_symlink():
                        total += file_path.stat().st_size
                except OSError:
                    continue
        return total

    def _entry_info(self, user, absolute: Path, relative_path: str) -> dict:
        stat = absolute.stat()
        is_dir = absolute.is_dir()
        size = self._directory_size(absolute) if is_dir else stat.st_size
        return {
            "name": absolute.name,
            "path": relative_path,
            "type": "folder" if is_dir else "file",
            "size": size,
            "size_display": format_size(size),
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        }

    def storage_usage(self, user) -> dict:
        root = self.user_root(user)
        total, _used, free = shutil.disk_usage(root)
        used_by_user = self._directory_size(root)
        return {
            "used": used_by_user,
            "used_display": format_size(used_by_user),
            "disk_total": total,
            "disk_total_display": format_size(total),
            "disk_free": free,
            "disk_free_display": format_size(free),
        }

    def list_entries(self, user, relative_path: str):
        target = self.resolve_user_path(user, relative_path)
        if not target.exists():
            raise FileNotFoundError(relative_path)
        if target.is_file():
            return []

        entries = []
        for child in target.iterdir():
            if child.name == ".DS_Store":
                continue
            child_rel = self.relative_path(user, child)
            entries.append(self._entry_info(user, child, child_rel))

        entries.sort(
            key=lambda item: (
                item["type"] != "folder",
                item["name"].casefold(),
            )
        )
        return entries

    def create_folder(self, user, parent_path: str, name: str):
        parent = self.resolve_user_path(user, parent_path)
        if not parent.exists() or not parent.is_dir():
            raise FileNotFoundError(parent_path)
        folder_name = self.normalize_name(name)
        target = (parent / folder_name).resolve()
        if target.exists():
            raise FileExistsError(folder_name)
        target.mkdir(parents=True, exist_ok=False)
        return self.relative_path(user, target)

    def upload_file(self, user, parent_path: str, relative_name: str, file_storage):
        parent_rel = self.normalize_relative_path(parent_path)
        file_rel = self.normalize_relative_path(relative_name)
        if not file_rel:
            raise ValueError("file path is required")

        full_rel = f"{parent_rel}/{file_rel}" if parent_rel else file_rel
        target = self.resolve_user_path(user, full_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_storage.save(str(target))
        return {
            "path": full_rel,
            "name": target.name,
            "size": target.stat().st_size,
            "size_display": format_size(target.stat().st_size),
        }

    def download_target(self, user, relative_path: str):
        target = self.resolve_user_path(user, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(relative_path)
        return target

    def delete(self, user, relative_path: str):
        rel = self.normalize_relative_path(relative_path)
        if not rel:
            raise ValueError("cannot delete user root")
        target = self.resolve_user_path(user, rel)
        if not target.exists():
            raise FileNotFoundError(rel)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def move_paths(self, user, paths, destination: str):
        dest_rel = self.normalize_relative_path(destination)
        destination_dir = self.resolve_user_path(user, dest_rel)
        if not destination_dir.exists() or not destination_dir.is_dir():
            raise FileNotFoundError(dest_rel)

        operations = []
        for raw_path in paths:
            rel = self.normalize_relative_path(raw_path)
            if not rel:
                raise ValueError("cannot move user root")
            source = self.resolve_user_path(user, rel)
            if not source.exists():
                raise FileNotFoundError(rel)

            target = (destination_dir / source.name).resolve()
            if target == source.resolve():
                continue
            if target.exists():
                raise FileExistsError(f"{source.name} already exists in destination")

            source_resolved = source.resolve()
            if source.is_dir() and source_resolved in target.parents:
                raise ValueError("cannot move a folder into itself")

            operations.append((source, target, rel))

        moved = []
        for source, target, rel in operations:
            shutil.move(str(source), str(target))
            moved.append(
                {
                    "path": rel,
                    "target": self.relative_path(user, target),
                }
            )
        return moved

    def delete_paths(self, user, paths):
        results = []
        for raw_path in paths:
            try:
                rel = self.normalize_relative_path(raw_path)
                if not rel:
                    raise ValueError("cannot delete user root")
                target = self.resolve_user_path(user, rel)
                if not target.exists():
                    results.append({"path": raw_path, "deleted": False, "error": "not found"})
                    continue
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                results.append({"path": rel, "deleted": True})
            except (FileNotFoundError, ValueError) as exc:
                results.append(
                    {
                        "path": raw_path,
                        "deleted": False,
                        "error": str(exc),
                    }
                )
        return results

    @staticmethod
    def _archive_name(relative_path: str, base_path: str) -> str:
        if not base_path:
            return relative_path
        prefix = f"{base_path}/"
        if relative_path == base_path:
            return ""
        if relative_path.startswith(prefix):
            return relative_path[len(prefix):]
        return relative_path

    def build_download_archive(self, user, paths, base_path: str):
        base_norm = self.normalize_relative_path(base_path)
        buffer = io.BytesIO()
        seen = set()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for raw_path in paths:
                rel = self.normalize_relative_path(raw_path)
                if not rel:
                    raise ValueError("cannot download user root")
                source = self.resolve_user_path(user, rel)
                if not source.exists():
                    continue

                if source.is_dir():
                    for child in source.rglob("*"):
                        if child.name == ".DS_Store":
                            continue
                        child_rel = self.relative_path(user, child)
                        arcname = self._archive_name(child_rel, base_norm)
                        if not arcname or arcname in seen:
                            continue
                        archive.write(str(child), arcname=arcname)
                        seen.add(arcname)
                else:
                    arcname = self._archive_name(rel, base_norm)
                    if arcname and arcname not in seen:
                        archive.write(str(source), arcname=arcname)
                        seen.add(arcname)

        buffer.seek(0)
        return buffer


file_service = FileService()
