import pytest
from PIL import Image

from image_viewer.config import Config
from image_viewer.core.edit_history import EditHistory
from image_viewer.core.image_model import ImageModel


@pytest.fixture
def model(qapp):
    model = ImageModel(Config())
    model.load_new_image(Image.new("RGBA", (4, 4), (20, 40, 60, 80)), "photo.png")
    yield model
    model.clear()


def edit(model, color):
    assert model.push_undo()
    model.set_image(Image.new("RGBA", (4, 4), color))


def test_undo_redo_tracks_saved_state(model):
    edit(model, "red")
    model.set_unsaved_changes(False)
    edit(model, "blue")
    assert model.has_unsaved_changes
    assert model.undo()
    assert model.image.getpixel((0, 0)) == (255, 0, 0, 255)
    assert not model.has_unsaved_changes
    assert model.undo(redo=True)
    assert model.image.getpixel((0, 0)) == (0, 0, 255, 255)
    assert model.has_unsaved_changes


def test_edit_after_undo_drops_redo(model):
    edit(model, "red")
    assert model.undo()
    edit(model, "green")
    assert not model.redo_stack
    assert not model.undo(redo=True)


def test_unique_snapshots_when_same_image_is_pushed_repeatedly(model):
    for _ in range(30):
        assert model.push_undo()
    assert len(model.undo_stack) == model.config.MAX_UNDO_STEPS
    assert len(set(model.undo_stack)) == len(model.undo_stack)
    for _ in range(model.config.MAX_UNDO_STEPS):
        assert model.undo()


def test_history_write_failure_preserves_redo(model, monkeypatch):
    edit(model, "red")
    model.undo()
    before = list(model.redo_stack)

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(model.history, "write", fail)
    assert not model.push_undo()
    assert model.redo_stack == before


def test_history_read_failure_preserves_entry(model, monkeypatch):
    edit(model, "red")
    before = list(model.undo_stack)

    def fail(*args):
        raise OSError("unreadable")

    monkeypatch.setattr(model.history, "read", fail)
    assert not model.undo()
    assert model.undo_stack == before
    assert model.image.getpixel((0, 0)) == (255, 0, 0, 255)


def test_original_survives_edit_and_save(model):
    original = model.image.tobytes()
    edit(model, "red")
    model.set_unsaved_changes(False)
    with model.get_original_image() as image:
        assert image.tobytes() == original


def test_failed_original_snapshot_preserves_document(model, monkeypatch):
    original = model.image.tobytes()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(EditHistory, "write", fail)
    assert not model.load_new_image(Image.new("RGB", (8, 8)), "other.png")
    assert model.image.tobytes() == original
    assert model.current_path == "photo.png"
