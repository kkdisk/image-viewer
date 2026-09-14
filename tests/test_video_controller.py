import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QSlider
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget

from image_viewer.core.video_controller import VideoController


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def controller(qapp):
    video_widget = QVideoWidget()
    play_button = QPushButton()
    stop_button = QPushButton()
    position_slider = QSlider(Qt.Orientation.Horizontal)
    time_label = QLabel()
    mute_button = QPushButton()
    volume_slider = QSlider(Qt.Orientation.Horizontal)
    volume_slider.setRange(0, 100)
    volume_slider.setValue(75)
    instance = VideoController(
        video_widget,
        play_button,
        stop_button,
        position_slider,
        time_label,
        mute_button,
        volume_slider,
    )
    yield instance
    instance.clear()


@pytest.mark.parametrize(
    ("milliseconds", "expected"),
    [(0, "00:00"), (65_000, "01:05"), (3_661_000, "01:01:01")],
)
def test_format_time(milliseconds, expected):
    assert VideoController.format_time(milliseconds) == expected


def test_initial_controls(controller):
    assert not controller.is_active
    assert controller.play_button.text() == "播放"
    assert controller.time_label.text() == "00:00 / 00:00"
    assert not controller.position_slider.isEnabled()


def test_volume_is_normalized(controller):
    controller.set_volume(25)
    assert controller.audio_output.volume() == pytest.approx(0.25)


def test_status_contains_filename_resolution_duration_and_state(controller):
    messages = []
    controller.status_changed.connect(messages.append)
    controller.current_path = "C:/videos/demo.mp4"
    controller._on_video_size_changed(QSize(1920, 1080))
    controller._on_duration_changed(65_000)
    controller._on_playback_state_changed(
        QMediaPlayer.PlaybackState.PlayingState
    )

    status = messages[-1]
    assert "demo.mp4" in status
    assert "1920x1080" in status
    assert "01:05" in status
    assert "播放中" in status
