"""圖片效果背景執行緒的生命週期控制。"""

import logging
from typing import Callable, Optional

from PIL import Image
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot

from image_viewer.core.workers import EffectWorker


class EffectController(QObject):
    """管理單一效果工作，並以 signals 將結果交回 UI。"""

    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)
    _trigger_apply = pyqtSignal(object, object, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[EffectWorker] = None
        self._effect_id = 0
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start(self, image: Image.Image, effect_func: Callable) -> bool:
        if self._busy or (self._thread and self._thread.isRunning()):
            return False

        self._effect_id += 1
        effect_id = self._effect_id
        thread = QThread(self)
        worker = EffectWorker()
        worker.moveToThread(thread)
        worker.result_ready.connect(self._handle_result)
        worker.error_occurred.connect(self._handle_error)
        self._trigger_apply.connect(
            worker.apply_effect,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.started.connect(
            lambda: self._trigger_apply.emit(image, effect_func, effect_id)
        )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        self._set_busy(True)
        thread.start()
        return True

    def stop(self, timeout_ms: int = 1000) -> bool:
        if not self._thread or not self._thread.isRunning():
            self._clear_references()
            self._set_busy(False)
            return True
        if self._worker:
            self._worker.request_stop()
        self._thread.quit()
        if not self._thread.wait(timeout_ms):
            logging.warning("效果執行緒未在期限內結束；將等待其安全完成。")
            return False
        self._clear_references()
        self._set_busy(False)
        return True

    @pyqtSlot(object, int)
    def _handle_result(self, image: Image.Image, effect_id: int) -> None:
        if effect_id != self._effect_id:
            image.close()
            return
        self.result_ready.emit(image)
        if self._thread:
            self._thread.quit()

    @pyqtSlot(str, int)
    def _handle_error(self, message: str, effect_id: int) -> None:
        if effect_id != self._effect_id:
            return
        self.error_occurred.emit(message)
        if self._thread:
            self._thread.quit()

    @pyqtSlot()
    def _on_thread_finished(self) -> None:
        self._clear_references()
        self._set_busy(False)

    def _clear_references(self) -> None:
        if self._worker:
            try:
                self._trigger_apply.disconnect(self._worker.apply_effect)
            except (TypeError, RuntimeError):
                pass
        self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        if self._busy != busy:
            self._busy = busy
            self.busy_changed.emit(busy)
