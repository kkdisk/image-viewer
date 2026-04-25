import os
import traceback
import logging
import threading
from typing import Optional, Callable
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.ImageQt import ImageQt

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QRunnable, QSize

from image_viewer.config import Config, LANCZOS_RESAMPLE, BILINEAR_RESAMPLE

class EffectWorker(QObject):
    result_ready = pyqtSignal(object, int)
    error_occurred = pyqtSignal(str, int)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    @pyqtSlot(object, object, int)
    def apply_effect(self, image: Image.Image, effect_func: Callable, effect_id: int) -> None:
        self._stop_event.clear()  # 在新效果開始時重置停止旗標
        new_image: Optional[Image.Image] = None
        try:
            if self._stop_event.is_set(): return
            new_image = effect_func(image)
            if self._stop_event.is_set():
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

class WorkerSignals(QObject):
    thumbnail_ready = pyqtSignal(object, str, int)
    thumbnail_error = pyqtSignal(str, int)

class ThumbnailWorker(QRunnable):
    def __init__(self, path: str, size: QSize, generation: int, config: Optional[Config] = None):
        super().__init__()
        self.path, self.size, self.generation = path, size, generation
        self.config = config or Config() # Fallback to default if not provided
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            draft_factor = self.config.THUMBNAIL_DRAFT_FACTOR
            draft_size = (self.size.width() * draft_factor, self.size.height() * draft_factor)
            with Image.open(self.path) as img:
                try:
                    img.draft('RGB', draft_size)
                    logging.debug(f"Draft mode applied for {os.path.basename(self.path)} with size {draft_size}")
                except Exception as draft_err:
                    # draft mode is optional optimization
                    logging.warning(f"Applying draft mode failed for {self.path}: {draft_err}")
                
                max_dim = self.config.THUMBNAIL_MAX_DIMENSION_BEFORE_DOWNSCALE
                if img.width > max_dim or img.height > max_dim:
                    img.thumbnail(self.config.THUMBNAIL_INTERMEDIATE_SIZE, BILINEAR_RESAMPLE)
                
                img.thumbnail(
                    (self.size.width(), self.size.height()),
                    LANCZOS_RESAMPLE
                )
                
                # [Optimization] 直接轉換為 RGBA，避免先轉 RGB (如果支援)
                if img.mode != 'RGBA':
                     final_img = img.convert("RGBA")
                else:
                     final_img = img

                qimage = ImageQt(final_img)
                self.signals.thumbnail_ready.emit(
                    qimage,
                    self.path,
                    self.generation
                )
        except Exception as e:
            logging.warning(f"無法為 {self.path} 生成縮圖: {e}\n{traceback.format_exc()}")
            self.signals.thumbnail_error.emit(self.path, self.generation)

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
                img.load()  # [FIX] 強制載入像素資料，確保在 close() 之前完成 I/O
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
