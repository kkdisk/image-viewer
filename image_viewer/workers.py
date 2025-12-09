# ==============================================================================
# workers.py - 背景 Worker 類別
# ==============================================================================
"""
包含所有背景執行緒工作者：EffectWorker、ThumbnailWorker、AsyncImageLoader
"""

import os
import logging
import traceback
from typing import Optional, Callable, Any
from functools import wraps

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QObject, QThread, pyqtSignal, QRunnable

from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.ImageQt import ImageQt

from .config import LANCZOS_RESAMPLE, BILINEAR_RESAMPLE


# ==============================================================================
# 裝飾器
# ==============================================================================
def requires_image(func: Callable) -> Callable:
    """裝飾器，檢查 self.image 是否存在"""
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        if self.image is None:
            QMessageBox.information(self, "操作提示", "請先載入圖片。")
            return None
        return func(self, *args, **kwargs)
    return wrapper


# ==============================================================================
# EffectWorker - 效果處理工作者
# ==============================================================================
class EffectWorker(QObject):
    result_ready = pyqtSignal(object, int)
    error_occurred = pyqtSignal(str, int)

    def __init__(self):
        super().__init__()
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    @pyqtSlot(object, object, int)
    def apply_effect(self, image: Image.Image, effect_func: Callable, effect_id: int) -> None:
        new_image: Optional[Image.Image] = None
        try:
            if self._stop_requested: return
            new_image = effect_func(image)
            if self._stop_requested:
                if new_image: new_image.close()
                return
            self.result_ready.emit(new_image, effect_id)
        except Exception as e:
            error_msg = f"套用效果時發生錯誤: {e}\n{traceback.format_exc()}"
            logging.error(error_msg)
            self.error_occurred.emit(error_msg, effect_id)
            if new_image is not None and new_image is not image:
                try: new_image.close()
                except Exception as close_err: logging.warning(f"關閉效果中產生的圖片時出錯: {close_err}")
        finally:
            if image:
                 try: image.close()
                 except Exception as close_err: logging.warning(f"關閉傳入效果執行緒的圖片副本時出錯: {close_err}")
            self._stop_requested = False


# ==============================================================================
# WorkerSignals - 縮圖信號
# ==============================================================================
class WorkerSignals(QObject):
    thumbnail_ready = pyqtSignal(QIcon, str, int)
    thumbnail_error = pyqtSignal(str, int)


# ==============================================================================
# ThumbnailWorker - 縮圖生成工作者
# ==============================================================================
class ThumbnailWorker(QRunnable):
    def __init__(self, path: str, size: QSize, generation: int):
        super().__init__()
        self.path, self.size, self.generation = path, size, generation
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            draft_size = (self.size.width() * 2, self.size.height() * 2)
            with Image.open(self.path) as img:
                try:
                    img.draft('RGB', draft_size)
                    logging.debug(f"Draft mode applied for {os.path.basename(self.path)} with size {draft_size}")
                except Exception as draft_err:
                    logging.warning(f"Applying draft mode failed for {self.path}: {draft_err}")
                if img.width > 1000 or img.height > 1000:
                    img.thumbnail((500, 500), BILINEAR_RESAMPLE)
                img.thumbnail(
                    (self.size.width(), self.size.height()),
                    LANCZOS_RESAMPLE
                )
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                final_img = img.convert("RGBA")
                # 使用 .copy() 切斷 ImageQt 對 PIL Image 的引用
                qimage = ImageQt(final_img.copy())
                pixmap = QPixmap.fromImage(qimage)
                self.signals.thumbnail_ready.emit(
                    QIcon(pixmap),
                    self.path,
                    self.generation
                )
        except Exception as e:
            logging.warning(f"無法為 {self.path} 生成縮圖: {e}\n{traceback.format_exc()}")
            self.signals.thumbnail_error.emit(self.path, self.generation)


# ==============================================================================
# AsyncImageLoader - 非同步圖片載入器
# ==============================================================================
class AsyncImageLoader(QObject):
    """在背景執行緒中非同步載入和預處理圖片。"""
    image_loaded = pyqtSignal(object, str)
    load_failed = pyqtSignal(str, str)
    load_progress = pyqtSignal(int)

    @pyqtSlot(str)
    def start_loading(self, path: str):
        independent_image: Optional[Image.Image] = None
        try:
            self.load_progress.emit(0)
            file_size = os.path.getsize(path)
            self.load_progress.emit(10)
            with Image.open(path) as img:
                self.load_progress.emit(40)
                processed_img = ImageOps.exif_transpose(img)
                self.load_progress.emit(70)
                final_image = processed_img.convert('RGBA')
                self.load_progress.emit(90)
                independent_image = final_image.copy()
                self.load_progress.emit(100)
            self.image_loaded.emit(independent_image, path)
        except FileNotFoundError:
            self.load_failed.emit("檔案不存在或路徑錯誤。", path)
        except PermissionError:
            self.load_failed.emit("沒有足夠的權限讀取檔案。", path)
        except UnidentifiedImageError:
            self.load_failed.emit("無法識別的圖片格式，檔案可能已損毀或不受支援。", path)
        except MemoryError:
            self.load_failed.emit("記憶體不足，無法載入此圖片。圖片可能過大。", path)
        except Exception as e:
            logging.error(f"載入圖片時發生未知錯誤 {path}: {e}\n{traceback.format_exc()}")
            self.load_failed.emit(f"發生未知錯誤: {e}", path)
