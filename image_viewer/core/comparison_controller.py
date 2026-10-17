"""參考圖片以唯讀背景工作載入，不改變主文件。"""

import os

from PIL import Image, ImageOps
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from image_viewer.core.image_ops import normalize_and_validate_image_path, validate_image_dimensions


class ReferenceSignals(QObject):
    finished = pyqtSignal(object, str, int)


class ReferenceLoader(QRunnable):
    def __init__(self, path, generation, config):
        super().__init__()
        self.path = path
        self.generation = generation
        self.config = config
        self.signals = ReferenceSignals()

    def run(self):
        try:
            normalize_and_validate_image_path(self.path, self.config.MAX_IMAGE_FILE_SIZE)
            with Image.open(self.path) as source:
                validate_image_dimensions(source, self.config.MAX_IMAGE_PIXELS)
                oriented = ImageOps.exif_transpose(source)
                try:
                    image = oriented.convert("RGBA")
                finally:
                    oriented.close()
            self.signals.finished.emit(image, self.path, self.generation)
        except Exception as error:
            self.signals.finished.emit(None, str(error), self.generation)


class ComparisonController(QObject):
    error_occurred = pyqtSignal(str)

    def __init__(self, model, view, config, parent=None):
        super().__init__(parent)
        self.model, self.view, self.config = model, view, config
        self.active = False
        self.reference = None
        self.reference_path = None
        self.original_key = None
        self.right_state = None
        self.generation = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.tasks = {}
        view.original_requested.connect(self.use_original)

    def refresh(self):
        if not self.active or self.model.image is None:
            return
        snapshot = self.model.original_snapshot
        key = snapshot.path if snapshot else None
        if self.reference_path is None and key != self.original_key:
            try:
                original = self.model.get_original_image()
            except Exception as error:
                self.error_occurred.emit(str(error))
                return
            try:
                self.view.left.set_image(original)
                name = os.path.basename(self.model.current_path or "")
                self.view.left_label.setText(f"載入時原圖（唯讀） · {name} · {original.width}×{original.height}")
            finally:
                original.close()
            self.original_key = key
        image = self.model.display_image
        self.view.right.set_image(image)
        if self.right_state is not None:
            self.view.right.set_state(*self.right_state)
            self.right_state = None
        name = os.path.basename(self.model.current_path or "")
        role = "調整預覽" if self.model.preview_image is not None else "已套用結果"
        self.view.right_label.setText(f"{role} · {name} · {image.width}×{image.height}")

    def load_reference(self, path):
        if not path.lower().endswith(self.config.SUPPORTED_IMAGE_EXTENSIONS):
            self.error_occurred.emit("請選擇支援的靜態圖片。")
            return
        try:
            path = normalize_and_validate_image_path(path, self.config.MAX_IMAGE_FILE_SIZE)
        except Exception as error:
            self.error_occurred.emit(str(error))
            return
        self.generation += 1
        task = ReferenceLoader(path, self.generation, self.config)
        self.tasks[self.generation] = task
        task.signals.finished.connect(self._loaded)
        self.pool.start(task)

    def _loaded(self, image, path, generation):
        self.tasks.pop(generation, None)
        if generation != self.generation or not self.active:
            if image is not None:
                image.close()
            return
        if image is None:
            self.error_occurred.emit(path)
            return
        if self.reference is not None:
            self.reference.close()
        self.reference, self.reference_path = image, path
        self.view.left.set_image(image)
        self.view.left_label.setText(f"參考（唯讀） · {os.path.basename(path)} · {image.width}×{image.height}")

    def use_original(self):
        self.generation += 1
        if self.reference is not None:
            self.reference.close()
        self.reference = None
        self.reference_path = None
        self.original_key = None
        self.refresh()

    def clear(self):
        self.active = False
        self.right_state = None
        self.use_original()
        self.view.left.set_image(None)
        self.view.right.set_image(None)

    def deactivate(self):
        """隱藏頁面時釋放顯示快取，保留參考來源及右側視圖。"""
        self.generation += 1
        self.active = False
        self.right_state = self.view.right.state()
        self.original_key = None
        self.view.left.set_image(None)
        self.view.right.set_image(None)

    def activate(self):
        self.active = True
        if self.reference is not None:
            self.view.left.set_image(self.reference)
        self.refresh()

    def shutdown(self):
        self.clear()
        self.pool.clear()
        return self.pool.waitForDone(2000)
