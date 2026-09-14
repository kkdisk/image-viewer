from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from image_viewer.core.video_thumbnailer import VideoThumbnailer


def test_create_thumbnail_preserves_target_size_and_adds_overlay():
    source = QImage(320, 180, QImage.Format.Format_RGB32)
    source.fill(QColor("red"))
    target_size = QSize(128, 128)

    thumbnail = VideoThumbnailer.create_thumbnail(source, target_size)

    assert not thumbnail.isNull()
    assert thumbnail.size() == target_size
    assert thumbnail.pixelColor(0, 0) == QColor("#1e1e1e")
    assert thumbnail.pixelColor(64, 64) != QColor("red")


def test_create_thumbnail_handles_portrait_frame():
    source = QImage(90, 160, QImage.Format.Format_RGB32)
    source.fill(QColor("blue"))

    thumbnail = VideoThumbnailer.create_thumbnail(source, QSize(120, 80))

    assert thumbnail.size() == QSize(120, 80)
    assert thumbnail.pixelColor(0, 40) == QColor("#1e1e1e")


def test_failed_request_emits_error_and_clears_current(qtbot):
    thumbnailer = VideoThumbnailer(QSize(128, 128))
    errors = []
    thumbnailer.thumbnail_error.connect(
        lambda path, generation: errors.append((path, generation))
    )
    thumbnailer._current = ("bad.mp4", 3)

    thumbnailer._fail_current()

    assert errors == [("bad.mp4", 3)]
    assert thumbnailer._current is None
