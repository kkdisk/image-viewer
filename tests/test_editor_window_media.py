import os

from PIL import Image
from PyQt6.QtCore import Qt, QUrl

from image_viewer.config import Config
from image_viewer.core.editor_window import ImageEditorWindow


def _close_window(window):
    window.video_controller.clear()
    window.image_loader_thread.quit()
    window.image_loader_thread.wait(3000)
    window.close()


def _normalized(path):
    return os.path.normcase(os.path.normpath(str(path)))


def test_video_appears_in_mixed_filmstrip(qtbot, tmp_path):
    image_path = tmp_path / "01-photo.png"
    video_path = tmp_path / "02-clip.mp4"
    Image.new("RGB", (8, 8), "red").save(image_path)
    video_path.write_bytes(b"test-video-placeholder")

    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    window.model.current_path = str(image_path)
    window._update_file_list(rescan=True)

    try:
        assert window.model.media_list == [_normalized(image_path), _normalized(video_path)]
        assert _normalized(video_path) in window.filmstrip_item_map
        video_item = window.filmstrip_item_map[_normalized(video_path)]
        assert video_item.toolTip() == video_path.name
        assert video_item.data(Qt.ItemDataRole.UserRole + 1) == "video"
    finally:
        _close_window(window)


def test_load_video_switches_mode_and_disables_image_actions(
    qtbot, tmp_path, monkeypatch
):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"test-video-placeholder")
    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    opened_paths = []
    monkeypatch.setattr(window.video_controller, "open", opened_paths.append)

    window.load_media(str(video_path))

    try:
        assert opened_paths == [_normalized(video_path)]
        assert window.is_video_mode
        assert window.model.current_path == _normalized(video_path)
        assert window.central_stack.currentWidget() is window.video_page
        assert not window.save_action.isEnabled()
        assert not window.rotate_left_action.isEnabled()
    finally:
        _close_window(window)


def test_switching_from_video_to_image_restores_image_mode(
    qtbot, tmp_path, monkeypatch
):
    video_path = tmp_path / "clip.mp4"
    image_path = tmp_path / "photo.png"
    video_path.write_bytes(b"test-video-placeholder")
    Image.new("RGB", (8, 8), "red").save(image_path)
    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    monkeypatch.setattr(window.video_controller, "open", lambda path: None)

    window.load_media(str(video_path))
    window.load_media(str(image_path))
    qtbot.waitUntil(
        lambda: window.model.current_path == _normalized(image_path),
        timeout=3000,
    )

    try:
        assert not window.is_video_mode
        assert not window.video_controller.is_active
        assert window.central_stack.currentWidget() is window.scroll_area
        assert window.model.image is not None
        assert window.save_action.isEnabled()
    finally:
        _close_window(window)


def test_close_releases_video_controller(qtbot, monkeypatch):
    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    clear_calls = []
    original_clear = window.video_controller.clear

    def record_clear():
        clear_calls.append(True)
        original_clear()

    monkeypatch.setattr(window.video_controller, "clear", record_clear)

    window.close()

    assert clear_calls == [True]
    assert not window.image_loader_thread.isRunning()


def test_multi_file_drop_opens_first_supported_file(qtbot, tmp_path, monkeypatch):
    unsupported = tmp_path / "notes.txt"
    video = tmp_path / "clip.mp4"
    image = tmp_path / "photo.png"
    unsupported.write_text("notes", encoding="utf-8")
    video.write_bytes(b"video")
    image.write_bytes(b"image")

    class MimeData:
        @staticmethod
        def urls():
            return [
                QUrl.fromLocalFile(str(unsupported)),
                QUrl.fromLocalFile(str(video)),
                QUrl.fromLocalFile(str(image)),
            ]

    class DropEvent:
        accepted = False

        @staticmethod
        def mimeData():
            return MimeData()

        def acceptProposedAction(self):
            self.accepted = True

    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    loaded = []
    monkeypatch.setattr(window, "load_media", loaded.append)
    event = DropEvent()

    window.dropEvent(event)

    try:
        assert [_normalized(path) for path in loaded] == [_normalized(video)]
        assert event.accepted
    finally:
        _close_window(window)
