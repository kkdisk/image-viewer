import pytest
from PIL import Image

from image_viewer.ui.comparison_view import ComparisonView


def test_sync_and_independent_zoom(qtbot):
    view = ComparisonView()
    qtbot.addWidget(view)
    view.resize(800, 500)
    view.left.set_image(Image.new("RGB", (1200, 1000)))
    view.right.set_image(Image.new("RGB", (2400, 2000)))
    view.show()
    view.right.set_state(2, 0.6, 0.4)
    view.right._notify()
    assert view.left.state()[0] == pytest.approx(2)
    assert view.left.state()[1] == pytest.approx(0.6, abs=0.01)
    assert view.left.state()[2] == pytest.approx(0.4, abs=0.01)
    view.sync.setChecked(False)
    view.right.set_state(3)
    view.right._notify()
    assert view.left.state()[0] == pytest.approx(2)
    view.sync.setChecked(True)
    assert view.left.state()[0] == pytest.approx(3)
    view.actual_size()
    assert view.left.state()[0] == view.right.state()[0] == 1
    view.fit_images()
    assert view.left.fit_mode and view.right.fit_mode
    assert view.left.state()[0] != view.right.state()[0]


def test_result_refresh_keeps_view_state(qtbot):
    view = ComparisonView()
    qtbot.addWidget(view)
    view.right.set_image(Image.new("RGBA", (1200, 1000), (20, 40, 60, 42)))
    view.right.set_state(2, 0.6, 0.4)
    before = view.right.state()
    view.right.set_image(Image.new("RGBA", (1200, 1000), "blue"))
    assert view.right.state() == pytest.approx(before, abs=0.01)
