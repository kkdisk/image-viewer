import pytest
from PIL import Image

from image_viewer.config import Config
from image_viewer.core.comparison_controller import ComparisonController
from image_viewer.core.image_model import ImageModel
from image_viewer.ui.comparison_view import ComparisonView


@pytest.fixture
def comparison(qtbot):
    model = ImageModel(Config())
    model.load_new_image(Image.new("RGBA", (100, 80), "red"), "photo.png")
    view = ComparisonView()
    qtbot.addWidget(view)
    controller = ComparisonController(model, view, Config())
    controller.active = True
    controller.refresh()
    yield model, view, controller
    controller.shutdown()
    model.clear()


def test_original_and_result_are_independent(comparison):
    model, view, controller = comparison
    model.set_image(Image.new("RGBA", (100, 80), "blue"))
    controller.refresh()
    assert view.left.item.pixmap().toImage().pixelColor(0, 0).name() == "#ff0000"
    assert view.right.item.pixmap().toImage().pixelColor(0, 0).name() == "#0000ff"


def test_reference_is_read_only_and_survives_document_change(comparison, qtbot, tmp_path):
    model, view, controller = comparison
    path = tmp_path / "reference.png"
    Image.new("RGBA", (80, 120), "green").save(path)
    state = model.state_id
    controller.load_reference(str(path))
    qtbot.waitUntil(lambda: controller.reference_path is not None)
    assert model.state_id == state
    assert not model.has_unsaved_changes
    assert not model.undo_stack
    model.load_new_image(Image.new("RGBA", (40, 40), "blue"), "other.png")
    controller.refresh()
    assert view.left.item.pixmap().size().width() == 80
    assert view.right.item.pixmap().size().width() == 40
    controller.use_original()
    assert view.left.item.pixmap().size().width() == 40


def test_failed_reference_keeps_old_reference(comparison, qtbot, tmp_path):
    _, _, controller = comparison
    path = tmp_path / "reference.png"
    Image.new("RGB", (8, 8), "green").save(path)
    controller.load_reference(str(path))
    qtbot.waitUntil(lambda: controller.reference_path is not None)
    previous = controller.reference_path
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"invalid")
    with qtbot.waitSignal(controller.error_occurred):
        controller.load_reference(str(broken))
    assert controller.reference_path == previous


def test_latest_reference_wins(comparison, qtbot, tmp_path):
    _, _, controller = comparison
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.new("RGB", (20, 20), "red").save(first)
    Image.new("RGB", (40, 40), "blue").save(second)
    controller.load_reference(str(first))
    controller.load_reference(str(second))
    qtbot.waitUntil(lambda: controller.reference is not None and controller.reference.width == 40)
    assert controller.reference_path.endswith("second.png")


def test_reference_uses_exif_orientation(comparison, qtbot, tmp_path):
    _, _, controller = comparison
    path = tmp_path / "reference.jpg"
    source = Image.new("RGB", (40, 20), "red")
    exif = source.getexif()
    exif[274] = 6
    source.save(path, exif=exif)
    controller.load_reference(str(path))
    qtbot.waitUntil(lambda: controller.reference is not None)
    assert controller.reference.size == (20, 40)
