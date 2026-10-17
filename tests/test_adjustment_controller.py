import threading

import pytest
from PIL import Image

from image_viewer.config import Config
from image_viewer.core.adjustment_controller import AdjustmentController
from image_viewer.core.image_model import ImageModel


@pytest.fixture
def editor(qtbot):
    model = ImageModel(Config())
    model.load_new_image(Image.new("RGBA", (8, 8), (100, 80, 60, 42)), "photo.png")
    controller = AdjustmentController(model)
    yield model, controller
    controller.cancel()
    qtbot.waitUntil(lambda: not controller.worker.is_busy, timeout=5000)
    controller.shutdown()
    model.clear()


def wait(qtbot, controller):
    qtbot.waitUntil(lambda: not controller.worker.is_busy, timeout=5000)


def test_many_previews_commit_one_history_entry(editor, qtbot):
    model, controller = editor
    original = model.image.tobytes()
    for brightness in (1.1, 1.2, 1.5):
        controller.preview((0, 0, brightness, 1, 1))
    wait(qtbot, controller)
    assert model.image.tobytes() == original
    assert model.preview_image.getpixel((0, 0)) == (150, 120, 90, 42)
    assert not model.has_unsaved_changes
    assert not model.undo_stack
    controller.apply()
    assert len(model.undo_stack) == 1
    assert model.preview_image is None
    assert model.image.getpixel((0, 0)) == (150, 120, 90, 42)
    assert model.has_unsaved_changes
    assert model.undo()
    assert model.image.tobytes() == original
    assert not model.has_unsaved_changes
    assert model.undo(redo=True)
    assert model.image.getpixel((0, 0)) == (150, 120, 90, 42)


@pytest.mark.parametrize("dirty", [False, True])
def test_cancel_preserves_dirty_state(editor, qtbot, dirty):
    model, controller = editor
    model.set_unsaved_changes(dirty)
    original = model.image.tobytes()
    controller.preview((30, 20, 1.5, 1, 1))
    wait(qtbot, controller)
    assert model.preview_image.getchannel("A").getextrema() == (42, 42)
    controller.cancel()
    assert model.image.tobytes() == original
    assert model.preview_image is None
    assert model.has_unsaved_changes == dirty
    assert not model.undo_stack


def test_neutral_apply_creates_no_history(editor, qtbot):
    model, controller = editor
    controller.preview((0, 0, 1, 1, 1))
    wait(qtbot, controller)
    controller.apply()
    assert not model.undo_stack
    assert not model.has_unsaved_changes
    assert not controller.active


def test_apply_waits_for_latest_pending_preview(editor, qtbot):
    model, controller = editor
    controller.preview((0, 0, 1.1, 1, 1))
    controller.preview((0, 0, 1.8, 1, 1))
    with qtbot.waitSignal(controller.completed, timeout=5000) as result:
        controller.apply()
    assert result.args == [True]
    assert model.image.getpixel((0, 0)) == (180, 144, 108, 42)
    assert len(model.undo_stack) == 1


def test_cancel_invalidates_queued_result(editor, qtbot, monkeypatch):
    model, controller = editor
    started, release = threading.Event(), threading.Event()
    import image_viewer.core.adjustment_controller as module

    def build(*args):
        def render(image):
            started.set()
            release.wait(5)
            return Image.new("RGBA", image.size, "red")
        return render

    monkeypatch.setattr(module, "build_fine_tune_effect", build)
    try:
        controller.preview((0, 0, 1.5, 1, 1))
        qtbot.waitUntil(started.is_set)
        controller.cancel()
    finally:
        release.set()
    wait(qtbot, controller)
    assert model.preview_image is None
    assert model.image.getpixel((0, 0)) == (100, 80, 60, 42)
    assert not model.undo_stack


def test_document_change_rejects_previous_preview(editor, qtbot):
    model, controller = editor
    controller.preview((0, 0, 1.5, 1, 1))
    model.load_new_image(Image.new("RGBA", (8, 8), "blue"), "other.png")
    wait(qtbot, controller)
    assert model.preview_image is None
    assert model.image.getpixel((0, 0)) == (0, 0, 255, 255)


def test_preview_failure_keeps_committed_image_and_allows_cancel(editor, qtbot, monkeypatch):
    model, controller = editor
    import image_viewer.core.adjustment_controller as module

    def build(*args):
        def fail(image):
            raise ValueError("failed preview")
        return fail

    monkeypatch.setattr(module, "build_fine_tune_effect", build)
    with qtbot.waitSignal(controller.error_occurred):
        controller.preview((0, 0, 1.5, 1, 1))
    wait(qtbot, controller)
    with qtbot.waitSignal(controller.completed) as result:
        controller.apply()
    assert result.args == [False]
    assert model.image.getpixel((0, 0)) == (100, 80, 60, 42)
    assert not model.undo_stack
    controller.cancel()
    assert not controller.active


def test_failed_history_write_keeps_preview_and_committed_state(editor, qtbot, monkeypatch):
    model, controller = editor
    controller.preview((0, 0, 1.5, 1, 1))
    wait(qtbot, controller)

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(model.history, "write", fail)
    with qtbot.waitSignal(controller.completed) as result:
        controller.apply()
    assert result.args == [False]
    assert model.image.getpixel((0, 0)) == (100, 80, 60, 42)
    assert model.preview_image is not None
    assert controller.active
    assert not model.undo_stack


@pytest.mark.parametrize("accelerated", [False, True])
def test_adjustment_preserves_alpha_for_both_backends(editor, qtbot, monkeypatch, accelerated):
    import image_viewer.core.image_ops as operations
    if accelerated and not hasattr(operations, "image_viewer_rs"):
        pytest.skip("Rust extension unavailable")
    monkeypatch.setattr(operations, "HAS_RUST_EXT", accelerated)
    model, controller = editor
    controller.preview((30, -20, 1.2, 1.1, 0.9))
    wait(qtbot, controller)
    controller.apply()
    assert model.image.getchannel("A").getextrema() == (42, 42)
    assert model.image.getpixel((0, 0))[:3] != (100, 80, 60)
