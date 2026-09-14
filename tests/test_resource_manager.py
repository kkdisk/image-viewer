import os

from PyQt6.QtGui import QIcon

from image_viewer.core.resource_manager import ResourceManager


def test_thumbnail_cache_invalidates_when_file_changes(tmp_path):
    path = tmp_path / "media.bin"
    path.write_bytes(b"first")
    manager = ResourceManager()
    icon = QIcon()
    manager.add_thumbnail(str(path), icon)

    assert manager.get_thumbnail(str(path)) is icon

    path.write_bytes(b"changed-content")
    os.utime(path, None)

    assert manager.get_thumbnail(str(path)) is None


def test_thumbnail_cache_invalidates_when_file_is_removed(tmp_path):
    path = tmp_path / "media.bin"
    path.write_bytes(b"content")
    manager = ResourceManager()
    manager.add_thumbnail(str(path), QIcon())

    path.unlink()

    assert manager.get_thumbnail(str(path)) is None
