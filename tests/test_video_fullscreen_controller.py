from PyQt6.QtCore import Qt

from image_viewer.config import Config
from image_viewer.core.editor_window import ImageEditorWindow


def _close_window(window):
    window.video_fullscreen_controller.exit()
    window.video_controller.clear()
    window.image_loader_thread.quit()
    window.image_loader_thread.wait(3000)
    window.close()


def test_fullscreen_hides_controls_and_restores_chrome(qtbot):
    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    window.show()
    window.is_video_mode = True
    window.central_stack.setCurrentWidget(window.video_page)
    controller = window.video_fullscreen_controller

    controller.enter()
    try:
        assert controller.is_active
        assert window.isFullScreen()
        assert window.video_controls.isVisible()

        controller.hide_delay_ms = 20
        controller.show_controls()
        qtbot.waitUntil(
            lambda: not window.video_controls.isVisible(),
            timeout=1000,
        )

        controller.show_controls()
        assert window.video_controls.isVisible()

        controller.exit()
        assert not controller.is_active
        assert not window.isFullScreen()
        assert window.video_controls.isVisible()
    finally:
        _close_window(window)


def test_double_click_toggles_video_fullscreen(qtbot):
    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)
    window.show()
    window.is_video_mode = True
    window.central_stack.setCurrentWidget(window.video_page)

    try:
        qtbot.mouseDClick(window.video_widget, Qt.MouseButton.LeftButton)
        assert window.video_fullscreen_controller.is_active

        qtbot.mouseDClick(window.video_widget, Qt.MouseButton.LeftButton)
        assert not window.video_fullscreen_controller.is_active
    finally:
        _close_window(window)


def test_fullscreen_is_ignored_outside_video_mode(qtbot):
    window = ImageEditorWindow(Config())
    qtbot.addWidget(window)

    try:
        window.video_fullscreen_controller.enter()
        assert not window.video_fullscreen_controller.is_active
        assert not window.isFullScreen()
    finally:
        _close_window(window)
