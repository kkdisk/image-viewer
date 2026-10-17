import pytest
from PIL import Image
from PyQt6.QtWidgets import QMessageBox

from image_viewer.config import Config
from image_viewer.core.editor_window import ImageEditorWindow


@pytest.fixture
def window(qtbot):
    window = ImageEditorWindow(Config())
    window.model.load_new_image(Image.new("RGBA", (600, 400), (100, 80, 60, 42)), "photo.png")
    yield window
    window.adjustments.cancel()
    qtbot.waitUntil(lambda: not window.adjustments.worker.is_busy and not window.effect_controller.is_busy)
    window.model.set_unsaved_changes(False)
    window.close()
    window.model.clear()


def preview(window, qtbot):
    window.brightness_slider.setValue(150)
    window._on_fine_tune_slider_released()
    qtbot.waitUntil(lambda: not window.adjustments.worker.is_busy)


def test_comparison_paints_large_rgb_and_rgba_images(window, qtbot):
    window.model.load_new_image(Image.new("RGB", (1200, 1000), "red"), "rgb.png")
    window.show()
    window.compare_action.setChecked(True)
    window.toggle_comparison(True)
    qtbot.waitExposed(window)
    window.repaint()
    assert window.central_stack.currentWidget() is window.comparison_view
    preview(window, qtbot)
    window.comparison_view.actual_size()
    window.repaint()
    window.cancel_adjustments()
    window.toggle_comparison(False)
    assert window.central_stack.currentWidget() is window.scroll_area
    assert not window.model.has_unsaved_changes


@pytest.mark.parametrize("answer", [
    QMessageBox.StandardButton.Apply, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Cancel,
])
def test_save_resolves_preview(window, qtbot, tmp_path, monkeypatch, answer):
    preview(window, qtbot)
    destination = tmp_path / "result.png"
    monkeypatch.setattr(QMessageBox, "question", lambda *args: answer)
    saved = window._execute_save(str(destination))
    if answer == QMessageBox.StandardButton.Cancel:
        assert not saved
        assert not destination.exists()
        assert window.adjustments.active
    else:
        assert saved
        assert not window.adjustments.active
        with Image.open(destination) as result:
            expected = (150, 120, 90, 42) if answer == QMessageBox.StandardButton.Apply else (100, 80, 60, 42)
            assert result.getpixel((0, 0)) == expected


def test_apply_during_render_uses_modal_completion(window, qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Apply)
    window.brightness_slider.setValue(150)
    window._on_fine_tune_slider_released()
    assert window._resolve_adjustments()
    assert window.model.image.getpixel((0, 0)) == (150, 120, 90, 42)
    assert len(window.model.undo_stack) == 1


def test_cancel_navigation_keeps_document_and_preview(window, qtbot, tmp_path, monkeypatch):
    preview(window, qtbot)
    destination = tmp_path / "other.png"
    Image.new("RGBA", (8, 8), "blue").save(destination)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.load_media(str(destination))
    assert window.model.current_path == "photo.png"
    assert window.adjustments.active


def test_undo_redo_actions_follow_adjustment_and_save(window, qtbot):
    preview(window, qtbot)
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    window.apply_adjustments()
    assert window.undo_action.isEnabled()
    window.model.set_unsaved_changes(False)
    window.undo()
    assert window.redo_action.isEnabled()
    assert window.model.has_unsaved_changes
    window.redo()
    assert not window.model.has_unsaved_changes
    assert window.model.image.getpixel((0, 0)) == (150, 120, 90, 42)
