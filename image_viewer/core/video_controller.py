"""Qt Multimedia 影片播放控制器。"""

import os

from PyQt6.QtCore import QObject, QSize, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer


class VideoController(QObject):
    """集中管理播放器生命週期，並同步播放控制元件。"""

    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    active_changed = pyqtSignal(bool)

    def __init__(
        self,
        video_widget,
        play_button,
        stop_button,
        position_slider,
        time_label,
        mute_button,
        volume_slider,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(video_widget)

        self.play_button = play_button
        self.stop_button = stop_button
        self.position_slider = position_slider
        self.time_label = time_label
        self.mute_button = mute_button
        self.volume_slider = volume_slider
        self.current_path: str | None = None
        self._video_size = QSize()
        self._duration_ms = 0
        self._display_state = "未載入"

        self.audio_output.setVolume(self.volume_slider.value() / 100.0)
        self.play_button.clicked.connect(self.toggle_playback)
        self.stop_button.clicked.connect(self.stop)
        self.position_slider.sliderMoved.connect(self.player.setPosition)
        self.mute_button.clicked.connect(self.toggle_muted)
        self.volume_slider.valueChanged.connect(self.set_volume)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.seekableChanged.connect(self._on_seekable_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)
        video_widget.videoSink().videoSizeChanged.connect(
            self._on_video_size_changed
        )

        self._reset_controls()

    @property
    def is_active(self) -> bool:
        return self.current_path is not None

    def open(self, path: str, autoplay: bool = True) -> None:
        self.player.stop()
        self.current_path = path
        self._video_size = QSize()
        self._duration_ms = 0
        self._display_state = "載入中"
        self._reset_controls()
        self.active_changed.emit(True)
        self._emit_status()
        self.player.setSource(QUrl.fromLocalFile(path))
        if autoplay:
            self.player.play()

    @pyqtSlot()
    def toggle_playback(self) -> None:
        if not self.is_active:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    @pyqtSlot()
    def stop(self) -> None:
        self.player.stop()

    def clear(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self.current_path = None
        self._video_size = QSize()
        self._duration_ms = 0
        self._display_state = "未載入"
        self._reset_controls()
        self.active_changed.emit(False)

    def seek_relative(self, offset_ms: int) -> None:
        if self.is_active and self.player.isSeekable():
            target = max(0, min(self.player.duration(), self.player.position() + offset_ms))
            self.player.setPosition(target)

    @pyqtSlot(int)
    def set_volume(self, value: int) -> None:
        self.audio_output.setVolume(max(0, min(100, value)) / 100.0)
        if value > 0 and self.audio_output.isMuted():
            self.audio_output.setMuted(False)
        self._update_mute_button()

    @pyqtSlot()
    def toggle_muted(self) -> None:
        self.audio_output.setMuted(not self.audio_output.isMuted())
        self._update_mute_button()

    def _reset_controls(self) -> None:
        self.position_slider.setRange(0, 0)
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        self.time_label.setText("00:00 / 00:00")
        self.play_button.setText("播放")
        self.play_button.setEnabled(self.is_active)
        self.stop_button.setEnabled(False)
        self._update_mute_button()

    def _on_position_changed(self, position: int) -> None:
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self._update_time_label(position, self.player.duration())

    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = max(0, duration)
        self.position_slider.setRange(0, max(0, duration))
        self.position_slider.setEnabled(duration > 0 and self.player.isSeekable())
        self._update_time_label(self.player.position(), duration)
        self._emit_status()

    def _on_seekable_changed(self, seekable: bool) -> None:
        self.position_slider.setEnabled(seekable and self.player.duration() > 0)

    def _on_playback_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("暫停" if playing else "播放")
        self.stop_button.setEnabled(self.is_active)
        if playing:
            self._display_state = "播放中"
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._display_state = "已暫停"
        elif self.player.mediaStatus() == QMediaPlayer.MediaStatus.LoadingMedia:
            self._display_state = "載入中"
        elif self.player.mediaStatus() != QMediaPlayer.MediaStatus.EndOfMedia:
            self._display_state = "已停止"
        self._emit_status()

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadingMedia:
            self._display_state = "載入中"
        elif status in (
            QMediaPlayer.MediaStatus.StalledMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
        ):
            self._display_state = "緩衝中"
        elif status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._display_state = "已載入"
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._display_state = "播放完畢"
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._display_state = "無法播放"
        self._emit_status()

    def _on_video_size_changed(self, size: QSize) -> None:
        self._video_size = size
        self._emit_status()

    def _on_error(self, error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self._display_state = "播放失敗"
            self._emit_status()
            self.error_occurred.emit(message or "無法播放此影片，格式或 codec 可能不受支援。")

    def _update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(
            f"{self.format_time(position)} / {self.format_time(duration)}"
        )

    def _update_mute_button(self) -> None:
        self.mute_button.setText("取消靜音" if self.audio_output.isMuted() else "靜音")

    def _emit_status(self) -> None:
        if not self.current_path:
            return
        if self._video_size.isValid():
            resolution = f"{self._video_size.width()}x{self._video_size.height()}"
        else:
            resolution = "讀取中"
        duration = (
            self.format_time(self._duration_ms)
            if self._duration_ms > 0
            else "--:--"
        )
        self.status_changed.emit(
            f"檔名: {os.path.basename(self.current_path)} | "
            f"尺寸: {resolution} | 長度: {duration} | "
            f"狀態: {self._display_state}"
        )

    @staticmethod
    def format_time(milliseconds: int) -> str:
        total_seconds = max(0, milliseconds) // 1000
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
