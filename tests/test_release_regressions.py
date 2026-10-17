"""v2.5 發布審查發現的關閉、載入競態與安全邊界。"""

import threading
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QIcon

from image_viewer.config import Config
from image_viewer.core.archive_manager import ArchiveManager
from image_viewer.core.comparison_controller import ReferenceLoader
from image_viewer.core.editor_window import ImageEditorWindow
from image_viewer.core.workers import AsyncImageLoader, ThumbnailWorker
from PyQt6.QtCore import QSize


@pytest.fixture
def window(qtbot):
    window = ImageEditorWindow(Config())
    window.model.load_new_image(Image.new("RGBA", (8, 8), "red"), "original.png")
    yield window
    window.adjustments.cancel()
    qtbot.waitUntil(lambda: not window.adjustments.worker.is_busy, timeout=5000)
    window.model.set_unsaved_changes(False)
    window.close()


def test_close_waits_for_cancelled_preview(window, qtbot, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def render(image):
        started.set()
        release.wait(5)
        return image.copy()

    window.show()
    window.adjustments.active = True
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    try:
        assert window.adjustments.worker.start(window.model.image.copy(), render)
        qtbot.waitUntil(started.is_set)
        assert not window.close()
        assert window._closing_requested
        assert window.isVisible()
        assert not window.isEnabled()
        assert window.image_loader_thread.isRunning()
    finally:
        release.set()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=4000)
    assert not window.adjustments.worker.is_busy
    assert not window.image_loader_thread.isRunning()
    assert window.model.image is None


def test_close_calls_reference_shutdown(window, monkeypatch):
    calls = []
    original = window.comparison.shutdown

    def shutdown():
        calls.append(True)
        return original()

    monkeypatch.setattr(window.comparison, "shutdown", shutdown)
    window.close()
    assert calls == [True]


def test_same_path_old_image_result_cannot_replace_latest_request(window):
    path = "reloaded.png"
    window._pending_image_path = path
    window._load_request_id = 2
    old = Image.new("RGBA", (8, 8), "blue")
    window._on_image_loaded(old, path, 1)
    assert window.model.current_path == "original.png"
    assert window._pending_image_path == path
    with pytest.raises(ValueError):
        old.getpixel((0, 0))
    window._on_image_loaded(Image.new("RGBA", (8, 8), "green"), path, 2)
    assert window.model.current_path == path
    assert window.model.image.getpixel((0, 0)) == (0, 128, 0, 255)


def test_same_path_old_error_is_ignored(window):
    window._pending_image_path = "reloaded.png"
    window._load_request_id = 2
    window._on_load_failed("outdated failure", "reloaded.png", 1)
    assert window._pending_image_path == "reloaded.png"
    window._pending_image_path = None


@pytest.mark.parametrize("kind", ["main", "reference", "thumbnail"])
def test_pixel_budget_rejects_image_before_decode(qapp, tmp_path, monkeypatch, kind):
    path = tmp_path / "large.png"
    Image.new("RGB", (12, 12)).save(path)
    config = Config()
    config.MAX_IMAGE_PIXELS = 100
    decoded = []
    original_load = Image.Image.load

    def record_load(image, *args, **kwargs):
        decoded.append(image.size)
        return original_load(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "load", record_load)
    errors = []
    if kind == "main":
        worker = AsyncImageLoader(config)
        worker.load_failed.connect(lambda *args: errors.append(args))
        worker.start_loading(str(path), 7)
        assert errors[0][2] == 7
    elif kind == "reference":
        worker = ReferenceLoader(str(path), 7, config)
        worker.signals.finished.connect(lambda *args: errors.append(args))
        worker.run()
        assert errors[0][0] is None
    else:
        worker = ThumbnailWorker(str(path), QSize(16, 16), 7, config)
        worker.signals.thumbnail_error.connect(lambda *args: errors.append(args))
        worker.run()
    assert errors
    assert not decoded


@pytest.mark.parametrize("name", [
    "dir/file.png:payload", "dir/CON.png", "NUL/file.png", "dir./file.png", "dir /file.png",
    "dir/LPT1.txt", "dir/CONIN$", "dir\\..\\outside.png",
])
def test_archive_rejects_windows_alias_and_stream_paths(name):
    archive = SimpleNamespace(list=lambda: [SimpleNamespace(filename=name, uncompressed=1)])
    with pytest.raises(ValueError):
        ArchiveManager()._validate_archive_entries(archive)


def test_image_pixel_budget_requires_positive_integer():
    config = Config()
    config.MAX_IMAGE_PIXELS = 0
    with pytest.raises(ValueError, match="MAX_IMAGE_PIXELS"):
        config.validate()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_toolbar_icons_distinguish_actions(window, theme):
    window.theme_manager.apply_theme(theme)
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
        undo = window.undo_action.icon().pixmap(24, 24, mode).toImage()
        redo = window.redo_action.icon().pixmap(24, 24, mode).toImage()
        compare = window.compare_action.icon().pixmap(24, 24, mode).toImage()
        fit = window.fit_to_window_action.icon().pixmap(24, 24, mode).toImage()
        assert not undo.isNull() and not redo.isNull() and undo != redo
        assert not compare.isNull() and not fit.isNull() and compare != fit
