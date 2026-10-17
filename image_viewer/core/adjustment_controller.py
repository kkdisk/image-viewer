"""調整預覽與正式編輯分離，僅在套用成功時建立歷史。"""

from PIL import ImageChops
from PyQt6.QtCore import QObject, pyqtSignal

from image_viewer.core.effect_controller import EffectController
from image_viewer.core.image_ops import build_fine_tune_effect, build_white_balance_effect


class AdjustmentController(QObject):
    changed = pyqtSignal()
    completed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.worker = EffectController(self)
        self.worker.result_ready.connect(self._result)
        self.worker.error_occurred.connect(self._error)
        self.worker.busy_changed.connect(self._idle)
        self.active = False
        self.pending = None
        self.applying = False
        self.ready = False
        self.version = -1

    def preview(self, parameters):
        if self.model.image is None or self.applying:
            return
        self.active = True
        self.ready = False
        self.version = self.model.document_version
        self.pending = tuple(parameters)
        self.worker.invalidate()
        self._start_pending()
        self.changed.emit()

    def _start_pending(self):
        if self.worker.is_busy or self.pending is None:
            return
        temp, tint, brightness, contrast, saturation = self.pending
        self.pending = None
        balance = build_white_balance_effect(temp, tint)
        fine = build_fine_tune_effect(brightness, contrast, saturation)

        def render(image):
            balanced = balance(image) if temp or tint else image.copy()
            try:
                result = fine(balanced)
                # 白平衡只處理色彩，透明度始終沿用基準圖。
                if image.mode == "RGBA":
                    result.putalpha(image.getchannel("A"))
                result.info.update(image.info)
                return result
            finally:
                balanced.close()

        source = self.model.image.copy()
        if not self.worker.start(source, render):
            source.close()

    def _result(self, image):
        if not self.active or self.version != self.model.document_version:
            image.close()
            return
        self.model.set_preview(image)
        self.ready = True

    def _idle(self, busy):
        if not busy:
            self._start_pending()
            if self.applying and not self.worker.is_busy:
                self._commit()
        self.changed.emit()

    def apply(self):
        if not self.active:
            self.completed.emit(True)
            return
        self.applying = True
        self.changed.emit()
        if not self.worker.is_busy:
            self._commit()

    def _commit(self):
        try:
            self._commit_ready()
        except Exception as error:
            self.applying = False
            self.error_occurred.emit(str(error))
            self.changed.emit()
            self.completed.emit(False)

    def _commit_ready(self):
        success = False
        if self.ready and self.version == self.model.document_version and self.model.preview_image is not None:
            difference = ImageChops.difference(self.model.image, self.model.preview_image)
            try:
                extrema = difference.getextrema()
                equal = all(high == 0 for low, high in extrema) if isinstance(extrema[0], tuple) else extrema[1] == 0
            finally:
                difference.close()
            if equal:
                success = True
            else:
                committed = self.model.preview_image.copy()
                if self.model.push_undo():
                    self.model.set_image(committed)
                    success = True
                else:
                    committed.close()
        self.applying = False
        if success:
            self.active = False
            self.model.set_preview(None)
        self.changed.emit()
        self.completed.emit(success)

    def _error(self, message):
        self.ready = False
        self.error_occurred.emit(message)

    def cancel(self):
        self.worker.invalidate()
        self.pending = None
        self.active = False
        self.ready = False
        was_applying = self.applying
        self.applying = False
        self.model.set_preview(None)
        self.changed.emit()
        if was_applying:
            self.completed.emit(False)

    def shutdown(self):
        self.cancel()
        return self.worker.stop()
