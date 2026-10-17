"""編輯、復原與壓縮檔儲存的回歸測試。"""

import threading
from pathlib import Path

import py7zr
import pytest
from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from image_viewer.config import Config
from image_viewer.core.editor_window import ImageEditorWindow
from image_viewer.core.image_ops import build_fine_tune_effect, build_white_balance_effect


@pytest.fixture
def window(qtbot):
    win = ImageEditorWindow(Config())
    yield win
    qtbot.waitUntil(lambda: not win.effect_controller.is_busy, timeout=5000)
    win.model.set_unsaved_changes(False)
    win.close()
    win.model.clear()


def wait_effect(qtbot, window):
    qtbot.waitUntil(lambda: not window.effect_controller.is_busy, timeout=5000)


def open_archive_image(window, tmp_path):
    source = tmp_path / "photo.png"
    archive = tmp_path / "photos.7z"
    Image.new("RGB", (8, 8), "red").save(source)
    with py7zr.SevenZipFile(archive, "w") as handle:
        handle.write(source, "photo.png")
    success, root = window.archive_manager.extract_7z(str(archive))
    assert success
    extracted = Path(root) / "photo.png"
    with Image.open(extracted) as image:
        window.model.load_new_image(image.copy(), str(extracted))
    window.model.set_image(Image.new("RGB", (8, 8), "blue"))
    return archive, extracted


def test_archive_save_survives_cleanup(window, tmp_path, monkeypatch):
    archive, extracted = open_archive_image(window, tmp_path)
    destination = tmp_path / "edited.png"
    suggested_paths = []

    def choose_destination(parent, title, suggested, filters):
        suggested_paths.append(Path(suggested))
        return str(destination), "PNG (*.png)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_destination)
    assert window.save_image()
    assert suggested_paths == [tmp_path / "photo.png"]
    assert not window.model.has_unsaved_changes
    assert Path(window.model.current_path) == destination
    window.archive_manager.cleanup()
    assert not extracted.exists()
    with Image.open(destination) as saved:
        assert saved.getpixel((0, 0)) == (0, 0, 255)
    with py7zr.SevenZipFile(archive, "r") as handle:
        handle.extractall(tmp_path / "verify")
    with Image.open(tmp_path / "verify" / "photo.png") as original:
        assert original.getpixel((0, 0)) == (255, 0, 0)


def test_cancel_archive_save_keeps_dirty_state(window, tmp_path, monkeypatch):
    _, extracted = open_archive_image(window, tmp_path)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    assert not window.save_image()
    assert window.model.has_unsaved_changes
    assert Path(window.model.current_path) == extracted


def test_archive_save_rejects_temporary_destination(window, tmp_path, monkeypatch):
    _, extracted = open_archive_image(window, tmp_path)
    destination = extracted.parent / "edited.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    assert not window.save_image_as()
    assert warnings
    assert not destination.exists()
    assert window.model.has_unsaved_changes


def test_regular_save_does_not_prompt(window, tmp_path, monkeypatch):
    destination = tmp_path / "photo.png"
    window.model.load_new_image(Image.new("RGB", (8, 8), "blue"), str(destination))
    window.model.set_unsaved_changes(True)

    def unexpected_dialog(*args):
        pytest.fail("一般圖片儲存不應要求另存新檔")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", unexpected_dialog)
    assert window.save_image()
    with Image.open(destination) as saved:
        assert saved.getpixel((0, 0)) == (0, 0, 255)


def test_undo_waits_for_effect_and_then_restores_image(window, qtbot):
    window.model.load_new_image(Image.new("RGB", (8, 8), "red"), "photo.png")
    started = threading.Event()
    release = threading.Event()

    def delayed_effect(image):
        started.set()
        release.wait(5)
        return Image.new("RGB", image.size, "blue")

    try:
        window._apply_effect(delayed_effect)
        qtbot.waitUntil(started.is_set, timeout=3000)
        assert not window.undo_action.isEnabled()
        window.undo()
        assert len(window.model.undo_stack) == 1
    finally:
        release.set()
    wait_effect(qtbot, window)
    assert window.undo_action.isEnabled()
    assert window.model.image.getpixel((0, 0)) == (0, 0, 255)
    window.undo()
    assert window.model.image.getpixel((0, 0)) == (255, 0, 0)
    assert not window.model.undo_stack


@pytest.mark.parametrize("slider_name,handler_name,value", [
    ("brightness_slider", "_on_fine_tune_slider_released", 150),
    ("contrast_slider", "_on_fine_tune_slider_released", 150),
    ("saturation_slider", "_on_fine_tune_slider_released", 150),
    ("temp_slider", "_on_white_balance_slider_released", 30),
    ("tint_slider", "_on_white_balance_slider_released", 30),
])
def test_adjustment_returns_to_original(window, qtbot, slider_name, handler_name, value):
    source = Image.new("RGB", (8, 8), (80, 100, 120))
    source.putpixel((0, 0), (160, 60, 40))
    original = source.tobytes()
    window.model.load_new_image(source, "photo.png")
    slider = getattr(window, slider_name)
    neutral = slider.value()
    handler = getattr(window, handler_name)
    slider.setValue(value)
    handler()
    wait_effect(qtbot, window)
    assert window.model.image.tobytes() != original
    slider.setValue(neutral)
    handler()
    wait_effect(qtbot, window)
    assert window.model.image.tobytes() == original


def test_white_balance_and_brightness_are_combined(window, qtbot):
    source = Image.new("RGB", (8, 8), (80, 100, 120))
    window.model.load_new_image(source.copy(), "photo.png")
    window.temp_slider.setValue(20)
    window._on_white_balance_slider_released()
    wait_effect(qtbot, window)
    window.brightness_slider.setValue(150)
    window._on_fine_tune_slider_released()
    wait_effect(qtbot, window)
    balanced = build_white_balance_effect(20, 0)(source)
    expected = build_fine_tune_effect(1.5, 1.0, 1.0)(balanced)
    assert window.model.image.tobytes() == expected.tobytes()
    source.close()
    balanced.close()
    expected.close()


def test_discrete_effect_commits_adjustment_and_undo_resets_baseline(window, qtbot):
    window.model.load_new_image(Image.new("RGB", (8, 8), (100, 100, 100)), "photo.png")
    window.brightness_slider.setValue(150)
    window._on_fine_tune_slider_released()
    wait_effect(qtbot, window)
    window._apply_effect(lambda image: image.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
    wait_effect(qtbot, window)
    assert window.brightness_slider.value() == 100
    assert window.model.image.getpixel((0, 0)) == (150, 150, 150)
    window.brightness_slider.setValue(120)
    window._on_fine_tune_slider_released()
    wait_effect(qtbot, window)
    assert window.model.image.getpixel((0, 0)) == (180, 180, 180)
    window.undo()
    assert window.brightness_slider.value() == 100
    assert window.model.image.getpixel((0, 0)) == (150, 150, 150)
    window.brightness_slider.setValue(120)
    window._on_fine_tune_slider_released()
    wait_effect(qtbot, window)
    assert window.model.image.getpixel((0, 0)) == (180, 180, 180)
