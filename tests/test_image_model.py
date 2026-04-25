import pytest
from PyQt6.QtWidgets import QApplication
from PIL import Image
from image_viewer.config import Config
from image_viewer.core.image_model import ImageModel

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def model(qapp):
    config = Config()
    config.MAX_UNDO_STEPS = 3
    return ImageModel(config)

def test_initial_state(model):
    assert model.image is None
    assert model.current_path is None
    assert model.scale == 1.0
    assert not model.has_unsaved_changes
    assert len(model.undo_stack) == 0

def test_load_new_image(model):
    img = Image.new('RGB', (100, 100))
    model.load_new_image(img, "test.png")
    
    assert model.image is not None
    assert model.image.size == (100, 100)
    assert model.current_path == "test.png"
    assert model.scale == 1.0
    assert not model.has_unsaved_changes

def test_scale_clamping(model):
    model.scale = 20.0
    assert model.scale == 10.0 # MAX clamp
    
    model.scale = 0.001
    assert model.scale == 0.01 # MIN clamp

def test_undo_stack_limit_and_operation(model):
    img1 = Image.new('RGB', (100, 100))
    img2 = Image.new('RGB', (200, 200))
    img3 = Image.new('RGB', (300, 300))
    img4 = Image.new('RGB', (400, 400))
    
    model.load_new_image(img1, "test.png")
    
    # Push 3 times (MAX is 3)
    model.push_undo()
    model.set_image(img2)
    model.push_undo()
    model.set_image(img3)
    model.push_undo()
    model.set_image(img4)
    
    assert len(model.undo_stack) == 3
    
    # Push one more time, oldest should be evicted
    model.push_undo()
    img5 = Image.new('RGB', (500, 500))
    model.set_image(img5)
    
    assert len(model.undo_stack) == 3
    # img2 is now the oldest. Since we store paths, open it to check size.
    with Image.open(model.undo_stack[0]) as oldest_img:
        assert oldest_img.size == (200, 200)
    
    # Test undo
    assert model.undo() is True
    assert model.image.size == (400, 400) # img4
    assert len(model.undo_stack) == 2

def test_clear(model):
    img = Image.new('RGB', (100, 100))
    model.load_new_image(img, "test.png")
    model.scale = 2.0
    model.push_undo()
    
    model.clear()
    
    assert model.image is None
    assert model.current_path is None
    assert model.scale == 1.0
    assert not model.has_unsaved_changes
    assert len(model.undo_stack) == 0


def test_gallery_sync_and_navigation(model):
    image_list = ["a.png", "b.png", "c.png"]
    model.current_path = "b.png"
    model.update_gallery(image_list)

    assert model.current_index == 1
    assert model.get_prev_image_path() == "a.png"
    assert model.get_next_image_path() == "c.png"


def test_gallery_sync_missing_path(model):
    model.current_path = "missing.png"
    model.update_gallery(["a.png", "b.png"])

    assert model.current_index == -1
    assert model.get_prev_image_path() is None
    assert model.get_next_image_path() is None
