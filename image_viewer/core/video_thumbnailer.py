"""使用單一 Qt Multimedia 解碼器非同步產生影片縮圖。"""

import os
from collections import deque
from typing import Deque, Optional, Tuple

from PyQt6.QtCore import QObject, QPoint, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPolygon
from PyQt6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink


ThumbnailRequest = Tuple[str, int]


class VideoThumbnailer(QObject):
    """依序解碼影片第一個有效影格，避免同時建立大量播放器。"""

    thumbnail_ready = pyqtSignal(object, str, int)
    thumbnail_error = pyqtSignal(str, int)

    def __init__(
        self,
        size: QSize,
        timeout_ms: int = 8000,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.size = size
        self.timeout_ms = timeout_ms
        self._queue: Deque[ThumbnailRequest] = deque()
        self._current: Optional[ThumbnailRequest] = None

        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_video_frame)
        self._player.errorOccurred.connect(self._on_player_error)

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._fail_current)

    def enqueue(self, path: str, generation: int) -> None:
        request = (path, generation)
        if request == self._current or request in self._queue:
            return
        self._queue.append(request)
        self._start_next()

    def clear(self) -> None:
        self._queue.clear()
        self._current = None
        self._timeout.stop()
        self._player.stop()
        self._player.setSource(QUrl())

    def _start_next(self) -> None:
        if self._current is not None or not self._queue:
            return
        self._current = self._queue.popleft()
        path, _ = self._current
        self._player.setSource(QUrl.fromLocalFile(path))
        self._timeout.start(self.timeout_ms)
        self._player.play()

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        if self._current is None or not frame.isValid():
            return
        path, generation = self._current
        source_path = os.path.normcase(os.path.normpath(
            self._player.source().toLocalFile()
        ))
        expected_path = os.path.normcase(os.path.normpath(path))
        if source_path != expected_path:
            return

        image = frame.toImage()
        if image.isNull():
            return
        thumbnail = self.create_thumbnail(image, self.size)
        self.thumbnail_ready.emit(thumbnail, path, generation)
        self._finish_current()

    def _on_player_error(self, error, _message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self._fail_current()

    def _fail_current(self) -> None:
        if self._current is None:
            return
        path, generation = self._current
        self.thumbnail_error.emit(path, generation)
        self._finish_current()

    def _finish_current(self) -> None:
        self._timeout.stop()
        self._player.stop()
        self._player.setSource(QUrl())
        self._current = None
        QTimer.singleShot(0, self._start_next)

    @staticmethod
    def create_thumbnail(source: QImage, size: QSize) -> QImage:
        """縮放影格、置中補邊，並疊加一致的播放符號。"""
        target = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        target.fill(QColor("#1e1e1e"))

        scaled = source.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (size.width() - scaled.width()) // 2
        y = (size.height() - scaled.height()) // 2

        painter = QPainter(target)
        painter.drawImage(x, y, scaled)

        radius = max(12, min(size.width(), size.height()) // 6)
        center = QPoint(size.width() // 2, size.height() // 2)
        painter.setPen(QPen(QColor(255, 255, 255, 210), 2))
        painter.setBrush(QColor(0, 0, 0, 145))
        painter.drawEllipse(center, radius, radius)

        triangle_size = max(8, radius // 2)
        triangle = QPolygon([
            QPoint(center.x() - triangle_size // 2, center.y() - triangle_size),
            QPoint(center.x() - triangle_size // 2, center.y() + triangle_size),
            QPoint(center.x() + triangle_size, center.y()),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawPolygon(triangle)
        painter.end()
        return target
