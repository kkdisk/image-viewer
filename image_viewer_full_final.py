# ==============================================================================
# 增強型圖片瀏覽器 - v1.4.12 (修正 Magnifier 背景)
#
# 說明：
# 此版本基於 v1.4.11，修正了 MagnifierWindow 的視覺效果，
# 使其深色背景也顯示為圓形，與裁切後的圖片內容一致。
# - MagnifierWindow 的 QLabel 背景設為透明。
# - _create_circular_pixmap 使用 QPainter 繪製圓形背景、圖片和邊框。
#
# ==============================================================================

import sys
import os
import gc
import logging
import traceback
import re
from typing import Optional, List, Dict, Any, Callable, Tuple
from threading import Lock
from functools import wraps # [新增] 導入 wraps

# import base64 # [移除] 不再需要

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QFileDialog, QMessageBox, QScrollArea,
    QToolBar, QStatusBar, QPushButton, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QFormLayout, QDockWidget, QSizePolicy,
    QDialog, QDialogButtonBox, QCheckBox, QSpinBox, QListWidget, QListWidgetItem,
    QStyle, QSlider, QGroupBox, QDoubleSpinBox, QProgressBar # [優化建議 9]
)
from PyQt6.QtGui import (
    QPixmap, QImage, QAction, QIcon, QKeySequence, QPalette, QCursor, QPainter, QColor, QPen,
    QResizeEvent, QCloseEvent, QDragEnterEvent, QDropEvent, QKeyEvent, QWheelEvent, QMouseEvent,
    QRegion, QPainterPath, QBrush # [v1.4.12 新增] QBrush for background
)
from PyQt6.QtCore import (
    Qt, QSize, pyqtSlot, QObject, QThread, pyqtSignal, QEvent, QRunnable, QThreadPool, QTimer, QPoint,
    QRect, QRectF # [v1.4.10 修正] 導入 QRectF
)

from PIL import Image, ImageOps, ImageFilter, ImageEnhance, UnidentifiedImageError
from PIL.ImageQt import ImageQt
from PIL.ExifTags import TAGS

import psutil
import numpy as np

# 日誌設定 - [優化建議 8] 使用更詳細的日誌格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s] - %(message)s",
    handlers=[
        logging.FileHandler('image_viewer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Pillow 版本相容性處理
try:
    LANCZOS_RESAMPLE = Image.Resampling.LANCZOS
    BILINEAR_RESAMPLE = Image.Resampling.BILINEAR # [優化 1]
    NEAREST_RESAMPLE = Image.Resampling.NEAREST   # [優化 1]
except AttributeError:
    LANCZOS_RESAMPLE = Image.LANCZOS
    BILINEAR_RESAMPLE = Image.BILINEAR # [優化 1]
    NEAREST_RESAMPLE = Image.NEAREST   # [優化 1]


# HEIC 支援檢查
HEIC_SUPPORTED = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
    logging.info("pillow_heif 已註冊，HEIC 支援已啟用。")
except ImportError:
    logging.info("未安裝 pillow_heif，HEIC 支援已停用。")

# natsort 支援檢查 (自然排序)
NATSORT_ENABLED = False
try:
    import natsort
    NATSORT_ENABLED = True
    logging.info("找到 natsort 模組。")
except ImportError:
    logging.info("未找到 natsort 模組，將使用預設排序。")


# ==============================================================================
# 1. 設定類別 (Config)
# ==============================================================================
class Config:
    """集中管理應用程式的所有設定。"""
    BASE_WINDOW_TITLE: str = "增強型圖片瀏覽器 v1.4.12" # 版本更新
    DEFAULT_WINDOW_SIZE: Tuple[int, int] = (1200, 800)
    THUMBNAIL_SIZE: QSize = QSize(128, 128)
    MAX_UNDO_STEPS: int = 20
    ZOOM_IN_FACTOR: float = 1.25
    ZOOM_OUT_FACTOR: float = 0.8
    BLUR_RADIUS: int = 2
    MAX_IMAGE_FILE_SIZE: int = 500 * 1024 * 1024
    SUPPORTED_IMAGE_EXTENSIONS: Tuple[str, ...] = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')
    MEMORY_THRESHOLD_MB: int = 800
    MEMORY_CHECK_INTERVAL_MS: int = 30000
    HISTOGRAM_WIDTH: int = 280
    HISTOGRAM_HEIGHT: int = 150
    WHITE_BALANCE_TEMP_RANGE: Tuple[int, int] = (-100, 100)
    WHITE_BALANCE_TINT_RANGE: Tuple[int, int] = (-100, 100)
    MAGNIFIER_SIZE: int = 180
    MAGNIFIER_FACTOR_RANGE: Tuple[float, float] = (1.5, 8.0)
    MAGNIFIER_DEFAULT_FACTOR: float = 2.0
    ADJUSTMENT_RANGE: Tuple[int, int] = (0, 200)
    ADJUSTMENT_DEFAULT: int = 100

    # [新增][優化建議 6]
    @classmethod
    def validate(cls):
        """驗證配置的合理性"""
        assert cls.ZOOM_IN_FACTOR > 1.0, "ZOOM_IN_FACTOR 必須大於 1.0"
        assert 0 < cls.ZOOM_OUT_FACTOR < 1.0, "ZOOM_OUT_FACTOR 必須在 0 和 1 之間"
        assert cls.MAX_UNDO_STEPS > 0, "MAX_UNDO_STEPS 必須為正數"
        assert cls.MAX_IMAGE_FILE_SIZE > 0, "MAX_IMAGE_FILE_SIZE 必須為正數"

if HEIC_SUPPORTED:
    Config.SUPPORTED_IMAGE_EXTENSIONS += ('.heic',)


# ==============================================================================
# 2. 資源與快取管理器
# ==============================================================================
class ResourceManager:
    """統一管理應用程式資源，如縮圖快取。"""
    def __init__(self):
        self._thumbnail_cache: Dict[str, QIcon] = {}
        logging.info("ResourceManager 初始化完畢。")

    def get_thumbnail(self, path: str) -> Optional[QIcon]:
        return self._thumbnail_cache.get(path)

    def add_thumbnail(self, path: str, icon: QIcon) -> None:
        self._thumbnail_cache[path] = icon

    def clear_caches(self) -> None:
        self._thumbnail_cache.clear()
        logging.info("所有資源快取已清空。")

# ==============================================================================
# 3. 背景工作者 (Workers)
# ==============================================================================
def requires_image(func: Callable) -> Callable:
    """裝飾器，檢查 self.image 是否存在"""
    @wraps(func) # [v1.4.6 新增] 使用 @wraps 保留元數據
    def wrapper(self: 'ImageEditorWindow', *args, **kwargs) -> Any:
        # [v1.4.4 修正] 檢查 self.image 是否為 None
        if self.image is None:
            QMessageBox.information(self, "操作提示", "請先載入圖片。")
            return None
        return func(self, *args, **kwargs)
    return wrapper

class EffectWorker(QObject):
    result_ready = pyqtSignal(object, int)
    error_occurred = pyqtSignal(str, int)
    _stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    @pyqtSlot(object, object, int)
    def apply_effect(self, image: Image.Image, effect_func: Callable, effect_id: int) -> None:
        new_image: Optional[Image.Image] = None # 確保 new_image 被定義
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
            # 如果效果函數內部產生 new_image 但後續出錯，也要關閉
            if new_image is not None and new_image is not image:
                try:
                    new_image.close()
                except Exception as close_err:
                     logging.warning(f"關閉效果中產生的圖片時出錯: {close_err}")
        finally:
            if image:
                 try:
                     image.close() # 關閉傳入的副本
                 except Exception as close_err:
                     logging.warning(f"關閉傳入效果執行緒的圖片副本時出錯: {close_err}")
            self._stop_requested = False

class WorkerSignals(QObject):
    thumbnail_ready = pyqtSignal(QIcon, str, int)
    thumbnail_error = pyqtSignal(str, int)

class ThumbnailWorker(QRunnable):
    def __init__(self, path: str, size: QSize, generation: int):
        super().__init__()
        self.path, self.size, self.generation = path, size, generation
        self.signals = WorkerSignals()
        self.setAutoDelete(True) # [優化建議 4B]

    @pyqtSlot()
    def run(self):
        try:
            # [優化 1] 使用 draft 模式快速載入
            # 計算 draft 尺寸，避免載入過大
            draft_size = (self.size.width() * 2, self.size.height() * 2) # 略大於目標尺寸

            with Image.open(self.path) as img:
                try:
                    # draft 模式可以大幅提升載入速度
                    img.draft('RGB', draft_size)
                    logging.debug(f"Draft mode applied for {os.path.basename(self.path)} with size {draft_size}")
                except Exception as draft_err:
                    logging.warning(f"Applying draft mode failed for {self.path}: {draft_err}")
                    # draft 失敗，繼續正常處理

                # 對於大圖,先快速縮小
                if img.width > 1000 or img.height > 1000:
                    # 使用更快的演算法進行初步縮放
                    img.thumbnail((500, 500), BILINEAR_RESAMPLE) # 使用 Bilinear 或 Nearest

                # 最終縮放使用高品質
                img.thumbnail(
                    (self.size.width(), self.size.height()),
                    LANCZOS_RESAMPLE
                )

                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')

                # 確保轉換為 RGBA 以創建 QPixmap
                final_img = img.convert("RGBA")
                qimage = ImageQt(final_img)
                pixmap = QPixmap.fromImage(qimage)

                self.signals.thumbnail_ready.emit(
                    QIcon(pixmap),
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
    load_progress = pyqtSignal(int) # [優化 3] 新增進度信號

    # [Review 問題 4 修正]
    @pyqtSlot(str)
    def start_loading(self, path: str):
        independent_image: Optional[Image.Image] = None # 確保定義
        try:
            # 可以在打開前發送 0%
            self.load_progress.emit(0)
            file_size = os.path.getsize(path) # 獲取大小以便更精確回報？ (暫時不用)
            self.load_progress.emit(10)  # 開始載入

            with Image.open(path) as img:
                self.load_progress.emit(40)  # 圖片已打開

                processed_img = ImageOps.exif_transpose(img)
                self.load_progress.emit(70)  # EXIF 處理完成

                final_image = processed_img.convert('RGBA')
                self.load_progress.emit(90)  # 轉換完成

                # 創建一個完全獨立的副本, 確保不依賴原始檔案
                independent_image = final_image.copy()
                self.load_progress.emit(100) # 完成

            # 在 with 區塊外發送,確保檔案已關閉
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

# ==============================================================================
# 4. 自訂 Widgets
# ==============================================================================
class HistogramWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(Config.HISTOGRAM_WIDTH, Config.HISTOGRAM_HEIGHT)
        self.hist_data: Dict[str, List[int]] = {'r': [], 'g': [], 'b': [], 'lum': []}
        self.max_val = 1
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Base))
        if not self.hist_data or self.max_val == 0: return
        width, height = self.width(), self.height()
        bar_width = width / 256.0
        channels = [('r', QColor(255, 0, 0, 150)), ('g', QColor(0, 255, 0, 150)),
                    ('b', QColor(0, 0, 255, 150)), ('lum', QColor(200, 200, 200, 200))]
        for channel_name, color in channels:
            painter.setPen(QPen(color))
            hist_values = self.hist_data.get(channel_name, [0]*256)
            for i, val in enumerate(hist_values):
                x = int(i * bar_width)
                bar_height = int((val / self.max_val) * height)
                painter.drawLine(x, height, x, height - bar_height)
        painter.end()
    def update_histogram(self, image: Optional[Image.Image]) -> None:
        if image is None:
            self.hist_data = {k: [0]*256 for k in self.hist_data}
            self.max_val = 1
        else:
            try:
                img_for_hist = image.convert('RGB') if image.mode not in ('RGB', 'L') else image
                hist = img_for_hist.histogram()
                if img_for_hist.mode == 'L':
                    self.hist_data = {'r': [0]*256, 'g': [0]*256, 'b': [0]*256, 'lum': hist}
                    self.max_val = max(hist) if hist else 1
                else:
                    self.hist_data['r'], self.hist_data['g'], self.hist_data['b'] = hist[0:256], hist[256:512], hist[512:768]
                    self.hist_data['lum'] = img_for_hist.convert('L').histogram()
                    self.max_val = max(max(h) for h in self.hist_data.values() if h) if any(self.hist_data.values()) else 1
            except Exception as e:
                logging.error(f"更新直方圖時出錯: {e}")
                self.hist_data = {k: [0]*256 for k in self.hist_data}
                self.max_val = 1
        self.update()

class ResizeDialog(QDialog):
    def __init__(self, original_size: QSize, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("調整尺寸")
        self.original_width, self.original_height = original_size.width(), original_size.height()
        self.aspect_ratio = self.original_width / self.original_height if self.original_height > 0 else 1.0
        layout, form_layout = QVBoxLayout(self), QFormLayout()
        self.width_spinbox, self.height_spinbox = QSpinBox(), QSpinBox()
        self.width_spinbox.setRange(1, 16000); self.width_spinbox.setValue(self.original_width)
        self.height_spinbox.setRange(1, 16000); self.height_spinbox.setValue(self.original_height)
        self.aspect_ratio_checkbox = QCheckBox("維持長寬比"); self.aspect_ratio_checkbox.setChecked(True)
        form_layout.addRow("寬度 (px):", self.width_spinbox); form_layout.addRow("高度 (px):", self.height_spinbox)
        layout.addLayout(form_layout); layout.addWidget(self.aspect_ratio_checkbox)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.width_spinbox.valueChanged.connect(self.on_width_changed)
        self.height_spinbox.valueChanged.connect(self.on_height_changed)
    def on_width_changed(self, new_width: int):
        if self.aspect_ratio_checkbox.isChecked():
            # 避免觸發遞迴更新
            is_blocked = self.height_spinbox.signalsBlocked()
            self.height_spinbox.blockSignals(True)
            new_height = int(new_width / self.aspect_ratio) if self.aspect_ratio != 0 else 1
            self.height_spinbox.setValue(max(1, new_height)) # 確保不為0
            self.height_spinbox.blockSignals(is_blocked)
    def on_height_changed(self, new_height: int):
        if self.aspect_ratio_checkbox.isChecked():
            is_blocked = self.width_spinbox.signalsBlocked()
            self.width_spinbox.blockSignals(True)
            new_width = int(new_height * self.aspect_ratio)
            self.width_spinbox.setValue(max(1, new_width)) # 確保不為0
            self.width_spinbox.blockSignals(is_blocked)
    def get_dimensions(self) -> Optional[QSize]:
        return QSize(self.width_spinbox.value(), self.height_spinbox.value()) if self.exec() == QDialog.DialogCode.Accepted else None

# [v1.4.9 修正] 改用 QPainter 繪製圓形和邊框
class MagnifierWindow(QDialog):
    def __init__(self, parent: 'ImageEditorWindow'):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(Config.MAGNIFIER_SIZE, Config.MAGNIFIER_SIZE)

        self.magnifier_label = QLabel(self)
        self.magnifier_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # [v1.4.12 修正] QLabel 背景設為透明
        self.magnifier_label.setStyleSheet("background-color: transparent;")
        # 確保 label 大小與窗口一致
        self.magnifier_label.setFixedSize(Config.MAGNIFIER_SIZE, Config.MAGNIFIER_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.magnifier_label)

        self._source_image: Optional[Image.Image] = None
        self._main_image_display_scale: float = 1.0
        self._magnifier_factor: float = Config.MAGNIFIER_DEFAULT_FACTOR

    def set_magnifier_params(self, source_image: Image.Image, main_image_display_scale: float, magnifier_factor: float):
        self._source_image, self._main_image_display_scale, self._magnifier_factor = source_image, main_image_display_scale, magnifier_factor
        self.magnifier_label.clear()

    # [修正 Bug 1 & 2]
    def update_magnified_view(self, cursor_pos_on_label: QPoint):
        if self._source_image is None or self._main_image_display_scale <= 0: return

        main_label = self.parent().image_label
        current_pixmap = main_label.pixmap()
        if not current_pixmap or current_pixmap.isNull():
            return

        magnifier_w, magnifier_h = self.width(), self.height()
        sample_w = int(magnifier_w / self._magnifier_factor)
        sample_h = int(magnifier_h / self._magnifier_factor)
        if sample_w <= 0 or sample_h <= 0: return

        label_size = main_label.size()
        pixmap_size = current_pixmap.size()
        scaled_pixmap_size = pixmap_size.scaled(label_size, Qt.AspectRatioMode.KeepAspectRatio)

        offset_x = (label_size.width() - scaled_pixmap_size.width()) / 2
        offset_y = (label_size.height() - scaled_pixmap_size.height()) / 2

        adjusted_x = cursor_pos_on_label.x() - offset_x
        adjusted_y = cursor_pos_on_label.y() - offset_y

        if adjusted_x < 0 or adjusted_y < 0 or \
           adjusted_x >= scaled_pixmap_size.width() or \
           adjusted_y >= scaled_pixmap_size.height():
            # 如果游標在 Label 上但在 Pixmap 外 (邊緣空白處)，也隱藏放大鏡
            self.hide()
            return

        pil_x = int(adjusted_x / scaled_pixmap_size.width() * self._source_image.width)
        pil_y = int(adjusted_y / scaled_pixmap_size.height() * self._source_image.height)

        pil_x = max(0, min(pil_x, self._source_image.width - 1))
        pil_y = max(0, min(pil_y, self._source_image.height - 1))

        left = max(0, min(pil_x - sample_w // 2, self._source_image.width - sample_w))
        top = max(0, min(pil_y - sample_h // 2, self._source_image.height - sample_h))
        right = left + sample_w
        bottom = top + sample_h

        cropped_image: Optional[Image.Image] = None
        magnified_pil: Optional[Image.Image] = None
        try:
            cropped_image = self._source_image.crop((left, top, right, bottom))
            magnified_pil = cropped_image.resize((magnifier_w, magnifier_h), LANCZOS_RESAMPLE)

            qimage = ImageQt(magnified_pil.convert('RGBA'))
            pixmap = QPixmap.fromImage(qimage)

            # [v1.4.9 修正] 使用 QPainter 創建帶邊框的圓形 Pixmap
            circular_pixmap = self._create_circular_pixmap(pixmap, magnifier_w)
            self.magnifier_label.setPixmap(circular_pixmap)

        except Exception as e:
            logging.error(f"更新放大鏡時出錯: {e}\n{traceback.format_exc()}")
        finally:
            # [修正 Bug 2] 確保關閉中間產生的 PIL Image 物件
            if cropped_image:
                try: cropped_image.close()
                except Exception as e_close: logging.warning(f"關閉 cropped_image 出錯: {e_close}")
            if magnified_pil:
                try: magnified_pil.close()
                except Exception as e_close: logging.warning(f"關閉 magnified_pil 出錯: {e_close}")

    # [v1.4.12 修正] 加入繪製圓形背景
    def _create_circular_pixmap(self, source_pixmap: QPixmap, size: int) -> QPixmap:
        """創建帶平滑邊緣、邊框和背景的圓形 QPixmap"""
        target = QPixmap(size, size)
        target.fill(Qt.GlobalColor.transparent) # 填充透明背景

        painter = QPainter(target)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True) # 抗鋸齒
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True) # 平滑縮放

            # 圓形區域 (留一點邊距給邊框)
            margin = 1 # 邊框寬度的一半
            content_rect_f = QRectF(margin, margin, size - 2*margin, size - 2*margin)

            # 1. 繪製圓形背景
            painter.setPen(Qt.PenStyle.NoPen) # 不需要邊框
            painter.setBrush(QBrush(QColor(0, 0, 0, 180))) # 深色半透明背景
            painter.drawEllipse(content_rect_f)

            # 2. 設置圓形裁切路徑
            path = QPainterPath()
            path.addEllipse(content_rect_f)
            painter.setClipPath(path)

            # 3. 繪製源圖像 (縮放到裁切區域)
            source_rect = QRectF(source_pixmap.rect())
            painter.drawPixmap(content_rect_f, source_pixmap, source_rect)

            # 4. 重置裁切以繪製邊框
            painter.setClipping(False)

            # 5. 繪製邊框
            pen = QPen(QColor("#0078d7"), 2) # 2px 寬度
            pen.setCosmetic(True) # 確保邊框寬度不受縮放影響
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush) # 確保邊框是空心的
            painter.drawEllipse(content_rect_f) # 繪製在裁切路徑的位置

        finally:
            painter.end() # 確保 painter 被結束

        return target


# ==============================================================================
# 5. 主視窗 (ImageEditorWindow)
# ==============================================================================
class ImageEditorWindow(QMainWindow):
    """圖片編輯器的主視窗。"""
    request_load_image = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.image: Optional[Image.Image] = None
        self.current_path: Optional[str] = None
        self.undo_stack: List[Image.Image] = []
        self.image_list: List[str] = []
        self.current_index: int = -1
        self.scale: float = 1.0

        # [優化建議 4A & 優化 2] LRU 快取相關屬性
        self._cached_pixmaps: Dict[float, QPixmap] = {}
        # 根據可用記憶體動態調整快取大小
        try:
            available_memory = psutil.virtual_memory().available / (1024 * 1024)  # MB
            self._cache_max_size = min(20, max(5, int(available_memory / 100)))
            logging.info(f"可用記憶體: {available_memory:.0f} MB, 動態設置快取大小為: {self._cache_max_size}")
        except Exception as e:
            logging.warning(f"無法獲取可用記憶體，使用預設快取大小 10: {e}")
            self._cache_max_size = 10 # Fallback
        self._cache_access_order: List[float] = []  # LRU 追蹤
        self._cache_hits = 0
        self._cache_misses = 0

        self._base_pixmap: Optional[QPixmap] = None
        self.is_panning: bool = False
        self.pan_start_pos: Optional[QPoint] = None
        self.is_fit_to_window_mode: bool = True
        self.has_unsaved_changes: bool = False
        self._is_programmatic_selection: bool = False
        self._base_image_for_effects: Optional[Image.Image] = None
        self.magnifier_enabled: bool = False
        self.magnifier_factor: float = Config.MAGNIFIER_DEFAULT_FACTOR
        self.magnifier_window: Optional[MagnifierWindow] = None
        self.filmstrip_item_map: Dict[str, QListWidgetItem] = {}

        self.resource_manager = ResourceManager()

        self.effect_thread: Optional[QThread] = None
        self.effect_worker: Optional[EffectWorker] = None
        self.thread_pool = QThreadPool()
        self.filmstrip_generation = 0
        self._is_effect_processing = False # [Review 問題 1 修正] 使用 flag
        self._current_effect_id = 0

        self.image_loader_thread = QThread()
        self.image_loader = AsyncImageLoader()
        self.image_loader.moveToThread(self.image_loader_thread)
        self.image_loader.image_loaded.connect(self._on_image_loaded)
        self.image_loader.load_failed.connect(self._on_load_failed)
        self.request_load_image.connect(self.image_loader.start_loading)
        self.image_loader.load_progress.connect(self._update_load_progress) # [優化 3] 連接進度信號
        self.image_loader_thread.start()

        self.setWindowTitle(Config.BASE_WINDOW_TITLE)
        self.setGeometry(100, 100, *Config.DEFAULT_WINDOW_SIZE)
        self.setAcceptDrops(True)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.ui_manager = UIManager(self)
        self.ui_manager.setup_ui()
        self.ui_manager.create_actions()
        self.ui_manager.create_docks()
        self.ui_manager.create_menus()
        self.ui_manager.create_toolbars()

        self.image_label.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)

        self.theme_manager = ThemeManager(QApplication.instance())
        self.theme_manager.toggle_theme(is_dark=True)

        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._check_memory_usage)
        self._memory_timer.start(Config.MEMORY_CHECK_INTERVAL_MS)

        self.status_bar.showMessage("準備就緒。請開啟一張圖片。", 0)
        self._update_ui_state()

    def load_image(self, path: str) -> None:
        self._stop_effect_thread()
        if self.magnifier_window: self.magnifier_window.hide()

        # [優化建議 3] 增強的錯誤處理
        try:
            normalized_path = os.path.normcase(os.path.normpath(path))

            # 更詳細的驗證
            if not os.path.exists(normalized_path):
                raise FileNotFoundError(f"檔案不存在: {normalized_path}")

            if not os.path.isfile(normalized_path):
                raise ValueError(f"不是有效的檔案: {normalized_path}")

            file_size = os.path.getsize(normalized_path)
            if file_size > Config.MAX_IMAGE_FILE_SIZE:
                raise ValueError(
                    f"檔案過大 ({file_size / (1024*1024):.1f} MB), "
                    f"超過限制 ({Config.MAX_IMAGE_FILE_SIZE / (1024*1024):.0f} MB)"
                )

            if file_size == 0:
                raise ValueError("檔案為空")

        except FileNotFoundError as e:
            self._handle_load_error("檔案不存在", str(e), path)
            return
        except ValueError as e:
            self._handle_load_error("無效的檔案", str(e), path)
            return
        except Exception as e:
            self._handle_load_error("錯誤", f"處理檔案時發生錯誤: {e}", path)
            return

        # [優化建議 9 & 優化 3] 添加/重置進度指示
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
             self._remove_progress_bar() # 使用輔助函數

        self.progress_bar = QProgressBar(self.status_bar)
        self.progress_bar.setRange(0, 100) # [優化 3] 設定範圍
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False) # 可以隱藏百分比文字
        self.status_bar.addPermanentWidget(self.progress_bar)

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.status_bar.showMessage(f"正在載入 {os.path.basename(normalized_path)}...", 0)

        self.request_load_image.emit(normalized_path)

    # [優化 3] 更新載入進度
    @pyqtSlot(int)
    def _update_load_progress(self, value: int):
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self.progress_bar.setValue(value)

    @pyqtSlot(object, str)
    def _on_image_loaded(self, new_image: Image.Image, path: str):
        # [優化建議 9 & 優化 3] 移除進度條
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self.progress_bar.setValue(100) # 確保顯示完成
            # 可以稍微延遲移除，讓使用者看到 100%
            QTimer.singleShot(500, self._remove_progress_bar)

        # [優化建議 1] 統一的資源清理
        self._cleanup_image_resources()

        self.image = new_image
        self._base_image_for_effects = self.image.copy() # 為了效果調整的基礎
        self.current_path = path

        self._reset_image_state()
        self._update_file_list()

        try:
            exif_data = self.image.getexif()
            self._display_exif_data(exif_data)
        except Exception as e:
            logging.warning(f"讀取 EXIF 時發生錯誤: {e}")
            self._display_exif_data(None) # 顯示無資訊

        self.histogram_widget.update_histogram(self.image)

        if self.is_fit_to_window_mode: self.fit_to_window()
        else: self.set_scale(1.0, is_manual_zoom=False)

        logging.info(f"成功載入圖片: {self.current_path}")
        QApplication.restoreOverrideCursor()
        self.update_status_bar()
        self._update_ui_state()

    @pyqtSlot(str, str)
    def _on_load_failed(self, error_message: str, path: str):
        # [優化建議 9 & 優化 3] 移除進度條
        self._remove_progress_bar()

        self._handle_load_error(f"載入失敗: {os.path.basename(path)}", error_message, path)
        QApplication.restoreOverrideCursor()
        self.status_bar.showMessage(f"載入失敗: {os.path.basename(path)}", 5000)
        self._update_ui_state()

    # [Review 問題 5 修正] 使用輔助函數移除進度條
    def _remove_progress_bar(self):
        """輔助函數，用於移除進度條"""
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            try:
                self.status_bar.removeWidget(self.progress_bar)
                self.progress_bar.deleteLater()
                self.progress_bar = None # 設為 None
            except RuntimeError as e:
                # Widget 可能已被刪除
                logging.debug(f"移除進度條時出現預期錯誤: {e}")
                self.progress_bar = None


    # [優化建議 1] 新增統一的資源清理方法
    def _cleanup_image_resources(self):
        """統一的資源清理方法"""
        if self.image:
            try:
                self.image.close()
            except Exception as e:
                logging.warning(f"關閉主圖片時出錯: {e}")
            self.image = None
        if self._base_image_for_effects:
            try:
                self._base_image_for_effects.close()
            except Exception as e:
                logging.warning(f"關閉效果基礎圖片時出錯: {e}")
            self._base_image_for_effects = None

        # 清理快取
        self._cached_pixmaps.clear()
        self._cache_access_order.clear()
        self._base_pixmap = None

        # 清理 undo stack 中的圖片資源
        for img in self.undo_stack:
            try:
                img.close()
            except Exception as e:
                logging.warning(f"關閉復原堆疊圖片時出錯: {e}")
        self.undo_stack.clear()

        gc.collect() # 提示進行垃圾回收

    # [v1.4.4 修正] 增加 checked 參數
    @pyqtSlot()
    def open_file_dialog(self, checked: bool = False):
        if not self._prompt_to_save_if_needed(): return
        exts_str = " ".join([f"*{ext}" for ext in Config.SUPPORTED_IMAGE_EXTENSIONS])
        path, _ = QFileDialog.getOpenFileName(self, "開啟圖片", os.path.dirname(self.current_path) if self.current_path else "", f"圖片 ({exts_str});;所有檔案 (*.*)")
        if path:
            self.load_image(path)

    # [v1.4.4 修正] 增加 checked 參數
    @requires_image
    def save_image(self, checked: bool = False) -> bool:
        return self._execute_save(self.current_path) if self.current_path else self.save_image_as()

    # [v1.4.4 修正] 增加 checked 參數
    @requires_image
    def save_image_as(self, checked: bool = False) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "圖片另存為", self.current_path or "", "PNG (*.png);;JPEG (*.jpg *.jpeg);;All Files (*)")
        return self._execute_save(path) if path else False

    @requires_image
    def push_undo(self) -> None:
        try:
            if len(self.undo_stack) >= Config.MAX_UNDO_STEPS:
                self.undo_stack.pop(0).close()
            self.undo_stack.append(self.image.copy())
            self._update_ui_state()
        except Exception as e:
            logging.error(f"壓入復原堆疊時出錯: {e}")
            QMessageBox.warning(self, "錯誤", "無法儲存復原狀態，可能是記憶體不足。")

    # [v1.4.4 修正] 增加 checked 參數，並將 is_effect_failure 設為關鍵字參數
    def undo(self, *, is_effect_failure: bool = False, checked: bool = False) -> None:
        # 處理來自 QAction 的 checked=False
        if checked is not False:
             is_effect_failure = False

        if not self.undo_stack:
            self.status_bar.showMessage("沒有更多操作可以復原。", 2000)
            return

        if self.image: self.image.close()
        self.image = self.undo_stack.pop()

        if self._base_image_for_effects: self._base_image_for_effects.close()

        try:
            self._base_image_for_effects = self.image.copy()
        except Exception as e:
            logging.error(f"復原時複製基礎圖片失敗: {e}")
            QMessageBox.critical(self, "復原失敗", f"無法複製圖片狀態: {e}")
            self._cleanup_image_resources() # 嚴重錯誤，清理資源
            self._update_ui_state()
            return

        self._cached_pixmaps.clear()
        self._cache_access_order.clear()
        self._base_pixmap = None

        self._display_image()
        self.histogram_widget.update_histogram(self.image)
        self.ui_manager.reset_adjustment_sliders()

        if not is_effect_failure:
            self.set_unsaved_changes(True)
            self.status_bar.showMessage("已復原上一個操作。", 2000)

        self._update_ui_state()

    # [Review 問題 1 修正] 使用 flag 替代鎖
    @requires_image
    def _apply_effect(self, effect_func: Callable) -> None:
        if not self._base_image_for_effects:
            logging.warning("_apply_effect: _base_image_for_effects 為 None。")
            return

        if self._is_effect_processing:
            self.status_bar.showMessage("正在處理效果，請稍候...", 2000)
            return

        self._is_effect_processing = True # 設定 flag

        try:
            self._stop_effect_thread()
            self.push_undo() # 在執行緒啟動前推入 undo
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

            self._current_effect_id += 1

            # 效果應該基於 _base_image_for_effects
            # 確保傳遞給執行緒的是一個副本
            copied_image = self._base_image_for_effects.copy()

            self.effect_thread = QThread()
            self.effect_worker = EffectWorker()
            self.effect_worker.moveToThread(self.effect_thread)

            self.effect_worker.result_ready.connect(self._handle_effect_result)
            self.effect_worker.error_occurred.connect(self._handle_effect_error)

            # 使用 lambda 確保傳遞的是當前的 effect_id
            self.effect_thread.started.connect(
                lambda: self.effect_worker.apply_effect(copied_image, effect_func, self._current_effect_id)
            )
            self.effect_thread.finished.connect(self._cleanup_thread)
            self.effect_thread.start()

        except Exception as e:
            # 捕獲啟動執行緒或複製圖像時的錯誤
            logging.error(f"啟動效果執行緒時出錯: {e}")
            QApplication.restoreOverrideCursor()
            self.undo(is_effect_failure=True) # 復原 push_undo
            self._is_effect_processing = False # 重設 flag

    def _display_image(self) -> None:
        if not self.image:
            self.image_label.clear()
            return

        try:
            pixmap = self._get_scaled_pixmap(self.scale)
            self.image_label.setPixmap(pixmap)

            if self.magnifier_enabled and self.magnifier_window:
                self.magnifier_window.set_magnifier_params(self.image, self.scale, self.magnifier_factor)
                if self.image_label.underMouse():
                    self.update_magnifier_position_and_content(self.image_label.mapFromGlobal(QCursor.pos()))
        except Exception as e:
            logging.error(f"顯示圖片時出錯: {e}")
            QMessageBox.critical(self, "顯示錯誤", f"無法顯示圖片: {e}")
            self._cleanup_image_resources()
            self._update_ui_state()


    # [優化建議 4A & 優化 2] LRU 快取策略 + 命中率統計
    def _get_scaled_pixmap(self, scale: float) -> QPixmap:
        # 四捨五入到小數點後2位,減少快取項目
        scale = round(scale, 2)

        if scale in self._cached_pixmaps:
            self._cache_hits += 1 # [優化 2]
            # 更新訪問順序 (LRU)
            if scale in self._cache_access_order:
                self._cache_access_order.remove(scale)
            self._cache_access_order.append(scale)
            return self._cached_pixmaps[scale]

        self._cache_misses += 1 # [優化 2]

        # [優化 2] 記錄快取效率 (每 50 次 miss 記錄一次)
        if self._cache_misses > 0 and self._cache_misses % 50 == 0:
            total_access = self._cache_hits + self._cache_misses
            if total_access > 0:
                hit_rate = self._cache_hits / total_access
                logging.info(f"快取統計: Hits={self._cache_hits}, Misses={self._cache_misses}, Hit Rate={hit_rate:.2%}")


        if not self.image:
            return QPixmap()

        if self._base_pixmap is None:
            try:
                # 確保 self.image 在轉換前是有效的
                if self.image is None: return QPixmap()
                self._base_pixmap = QPixmap.fromImage(ImageQt(self.image))
            except Exception as e:
                logging.error(f"從 PIL Image 創建 QPixmap 失敗: {e}")
                return QPixmap() # 返回空的 Pixmap

        w, h = self._base_pixmap.size().width(), self._base_pixmap.size().height()
        scaled_pixmap = self._base_pixmap.scaled(
            max(1, int(w * scale)),
            max(1, int(h * scale)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # LRU 快取淘汰
        if len(self._cached_pixmaps) >= self._cache_max_size:
            oldest_scale = self._cache_access_order.pop(0)
            if oldest_scale in self._cached_pixmaps:
                del self._cached_pixmaps[oldest_scale]

        self._cached_pixmaps[scale] = scaled_pixmap
        self._cache_access_order.append(scale)

        return scaled_pixmap

    def fit_to_window(self) -> None:
        if not self.image: return
        vp_size = self.scroll_area.viewport().size()
        if vp_size.width() <= 0 or vp_size.height() <= 0: return
        img_size = self.image.size
        if img_size[0] == 0 or img_size[1] == 0: return
        w_scale, h_scale = vp_size.width() / img_size[0], vp_size.height() / img_size[1]
        self.set_scale(min(w_scale, h_scale), is_manual_zoom=False)

    def set_scale(self, new_scale: float, is_manual_zoom: bool = True) -> None:
        if not self.image: return
        self.scale = max(0.01, min(new_scale, 10.0))
        if is_manual_zoom and self.is_fit_to_window_mode: self.toggle_fit_to_window_mode(False)
        self._display_image(); self.update_status_bar()

    def update_status_bar(self) -> None:
        if not self.image or not self.current_path:
            self.status_bar.clearMessage()
            if hasattr(self, 'zoom_entry'): self.zoom_entry.setText("")
            return
        w, h = self.image.size
        filename = os.path.basename(self.current_path)
        status_text = f"檔名: {filename} | 尺寸: {w}x{h} | 縮放: {self.scale * 100:.1f}%"
        self.status_bar.showMessage(status_text)
        if hasattr(self, 'zoom_entry'):
            # 更新 zoom_entry 時格式化為百分比
            if not self.zoom_entry.hasFocus(): # 僅在使用者未編輯時更新
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%")

    def set_unsaved_changes(self, has_changes: bool) -> None:
        if self.has_unsaved_changes == has_changes: return
        self.has_unsaved_changes = has_changes
        title = Config.BASE_WINDOW_TITLE
        self.setWindowTitle(f"*{title}" if has_changes else title)

    # [優化建議 7] 記憶體洩漏預防 (強化的 closeEvent)
    def closeEvent(self, event: QCloseEvent) -> None:
        if self._prompt_to_save_if_needed():
            logging.info("開始關閉應用程式...")
            # 停止所有背景任務
            self._stop_effect_thread()

            # 停止載入器執行緒
            if self.image_loader_thread and self.image_loader_thread.isRunning():
                logging.info("正在停止圖片載入執行緒...")
                self.image_loader_thread.quit()
                if not self.image_loader_thread.wait(3000):
                     logging.warning("圖片載入執行緒未在3秒內停止。")

            # 等待執行緒池完成
            logging.info("正在等待縮圖執行緒池完成...")
            self.thread_pool.clear() # 清除佇列
            if not self.thread_pool.waitForDone(2000): # 等待當前任務完成
                 logging.warning("縮圖執行緒池未在2秒內完成。")

            # 清理圖片資源 (包含 undo stack)
            logging.info("正在清理圖片資源...")
            self._cleanup_image_resources()

            # 清理快取
            logging.info("正在清理資源管理器快取...")
            self.resource_manager.clear_caches()

            # 關閉放大鏡
            if self.magnifier_window:
                logging.info("正在關閉放大鏡視窗...")
                self.magnifier_window.close()
                self.magnifier_window = None

            # 停止計時器
            if hasattr(self, '_memory_timer'):
                logging.info("正在停止記憶體檢查計時器...")
                self._memory_timer.stop()

            # 強制垃圾回收
            logging.info("正在執行垃圾回收...")
            gc.collect()

            logging.info("應用程式關閉完成。")
            event.accept()
        else:
            logging.info("使用者取消關閉。")
            event.ignore()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.image and self.is_fit_to_window_mode: self.fit_to_window()
        # [Review 問題 6] 更新 startup_label 位置
        if hasattr(self, 'startup_container') and self.startup_label.isVisible():
            self.startup_container.setGeometry(self.scroll_area.viewport().rect())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key_map = {Qt.Key.Key_Left: self.prev_image, Qt.Key.Key_Right: self.next_image}
        if event.key() in key_map: key_map[event.key()]()
        else: super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.image and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        try:
            if source == self.image_label:
                if event.type() == QEvent.Type.MouseMove and self.magnifier_enabled:
                    self.update_magnifier_position_and_content(event.pos())
                    return True
                elif event.type() in (QEvent.Type.Leave, QEvent.Type.Enter) and self.magnifier_window:
                    self.magnifier_window.setVisible(event.type() == QEvent.Type.Enter and self.magnifier_enabled)
                    return True
            elif source == self.scroll_area.viewport():
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = True
                    self.pan_start_pos = event.pos()
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return True
                elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = False
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    return True
                elif event.type() == QEvent.Type.MouseMove and self.is_panning and self.pan_start_pos:
                    delta = event.pos() - self.pan_start_pos
                    self.scroll_area.horizontalScrollBar().setValue(self.scroll_area.horizontalScrollBar().value() - delta.x())
                    self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value() - delta.y())
                    self.pan_start_pos = event.pos()
                    return True
                # [Review 問題 6] 處理 viewport resize
                elif event.type() == QEvent.Type.Resize:
                    if hasattr(self, 'startup_container') and self.startup_label.isVisible():
                         self.startup_container.setGeometry(self.scroll_area.viewport().rect())
                    # 重新計算 fit_to_window
                    if self.image and self.is_fit_to_window_mode:
                        self.fit_to_window()

        except Exception as e:
            logging.error(f"事件過濾器發生錯誤: {e}")

        return super().eventFilter(source, event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if (urls := event.mimeData().urls()) and os.path.isfile(path := urls[0].toLocalFile()):
            if self._prompt_to_save_if_needed(): self.load_image(path)

    # [優化建議 5] UI 響應性改進 (分批載入)
    def _populate_filmstrip(self) -> None:
        """分批載入縮圖,避免 UI 凍結"""
        self.thread_pool.clear()
        self.filmstrip_generation += 1
        self.filmstrip_widget.clear()
        self.filmstrip_item_map.clear()

        # 分批處理
        BATCH_SIZE = 20

        for i, path in enumerate(self.image_list):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)

            cached_icon = self.resource_manager.get_thumbnail(path)
            if cached_icon:
                item.setIcon(cached_icon)
            else:
                item.setIcon(self.style().standardIcon(
                    QStyle.StandardPixmap.SP_FileIcon # 使用通用檔案圖示作為預設
                ))

                worker = ThumbnailWorker(
                    path,
                    Config.THUMBNAIL_SIZE,
                    self.filmstrip_generation
                )
                worker.signals.thumbnail_ready.connect(self._update_thumbnail)
                worker.signals.thumbnail_error.connect(self._update_thumbnail_error)

                self.thread_pool.start(worker)

            self.filmstrip_widget.addItem(item)
            self.filmstrip_item_map[path] = item

            # 每批次後讓 UI 更新
            if (i + 1) % BATCH_SIZE == 0:
                QApplication.processEvents()

    @pyqtSlot(QIcon, str, int)
    def _update_thumbnail(self, icon: QIcon, path: str, generation: int):
        if generation == self.filmstrip_generation and path in self.filmstrip_item_map:
            self.filmstrip_item_map[path].setIcon(icon)
            self.resource_manager.add_thumbnail(path, icon)

    def _execute_save(self, path: str) -> bool:
        if not self.image: return False
        try:
            save_image = self.image.convert('RGB') if path.lower().endswith(('.jpg', '.jpeg')) and self.image.mode == 'RGBA' else self.image
            save_image.save(path)
            self.status_bar.showMessage(f"圖片已儲存至: {os.path.basename(path)}", 3000)
            if os.path.normcase(path) != os.path.normcase(self.current_path or ""):
                self.current_path = os.path.normcase(os.path.normpath(path))
                self._update_file_list(rescan=True) # 儲存到新位置後，重新掃描資料夾
            self.set_unsaved_changes(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", f"儲存圖片時發生錯誤: {e}")
            logging.error(f"儲存失敗: {e}")
            return False

    def _reset_image_state(self) -> None:
        # self.undo_stack.clear() # _cleanup_image_resources 已經處理
        self._cached_pixmaps.clear()
        self._cache_access_order.clear()
        self._base_pixmap = None
        self.set_unsaved_changes(False)
        self.ui_manager.reset_adjustment_sliders()

    def _update_file_list(self, rescan: bool = False) -> None:
        if not self.current_path: return

        try:
            new_folder = os.path.dirname(self.current_path)
            current_folder = os.path.dirname(self.image_list[0]) if self.image_list else None

            if rescan or new_folder != current_folder:
                if not os.path.isdir(new_folder): # 安全檢查
                    logging.warning(f"無法更新檔案列表，目錄不存在: {new_folder}")
                    self.image_list.clear()
                    self._populate_filmstrip()
                    return

                exts = Config.SUPPORTED_IMAGE_EXTENSIONS
                self.image_list = [os.path.normcase(os.path.normpath(os.path.join(new_folder, f))) for f in os.listdir(new_folder) if f.lower().endswith(exts) and os.path.isfile(os.path.join(new_folder, f))]
                self.image_list = natsort.natsorted(self.image_list) if NATSORT_ENABLED else sorted(self.image_list)
                self.resource_manager.clear_caches() # 清理舊資料夾的縮圖
                self._populate_filmstrip()

        except Exception as e:
            logging.error(f"更新檔案列表時出錯: {e}")
            self.image_list.clear()
            self._populate_filmstrip()

        try:
            self.current_index = self.image_list.index(self.current_path)
            if self.current_path in self.filmstrip_item_map:
                self._select_filmstrip_item(self.filmstrip_item_map[self.current_path])
        except ValueError:
            self.current_index = -1
            logging.warning(f"目前路徑 {self.current_path} 不在新的 image_list 中。")

    def _select_filmstrip_item(self, item_to_select: QListWidgetItem) -> None:
        self._is_programmatic_selection = True
        self.filmstrip_widget.setCurrentItem(item_to_select)
        self.filmstrip_widget.scrollToItem(item_to_select, QListWidget.ScrollHint.EnsureVisible)
        self._is_programmatic_selection = False

    # [v1.4.9 修正] 改進 EXIF 解碼
    def _display_exif_data(self, exif_data: Optional[Dict]) -> None:
        self.exif_tree.clear()
        if not exif_data:
            QTreeWidgetItem(self.exif_tree, ["無 EXIF 資訊", ""])
            return

        try:
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, f"Unknown ({tag_id})")

                # 簡化的類型處理
                if isinstance(value, bytes):
                    # 嘗試解碼 bytes
                    display_value = self._decode_exif_bytes(value)
                else:
                    display_value = str(value)

                # 限制長度
                if len(display_value) > 150:
                    display_value = display_value[:150] + '...'

                QTreeWidgetItem(self.exif_tree, [str(tag_name), display_value])

        except Exception as e:
            logging.error(f"解析 EXIF 標籤時出錯: {e}")
            self.exif_tree.clear()
            QTreeWidgetItem(self.exif_tree, ["解析 EXIF 時出錯", str(e)])

    # [v1.4.9 新增] 輔助函數解碼 EXIF bytes
    def _decode_exif_bytes(self, data: bytes) -> str:
        """嘗試解碼 EXIF bytes 數據"""
        if not data:
            return "[空數據]"

        # 移除結尾的空字節
        data = data.rstrip(b'\x00')

        # 嘗試常見編碼
        encodings = ['utf-8', 'latin-1', 'ascii']
        try:
            # 嘗試系統預設編碼
            encodings.append(sys.getdefaultencoding())
        except Exception:
            pass # 忽略獲取預設編碼的錯誤

        for encoding in encodings:
            try:
                decoded = data.decode(encoding, errors='strict') # 使用 strict 確保是有效編碼
                # 簡單檢查是否包含非可打印字符（不包含換行符等）
                if all(c.isprintable() or c.isspace() for c in decoded.strip()):
                     # 移除可能存在的 BOM (Byte Order Mark)
                    if decoded.startswith('\ufeff'):
                        decoded = decoded[1:]
                    return decoded.strip() # 返回去除首尾空白的結果
            except (UnicodeDecodeError, AttributeError):
                continue

        # 如果都失敗，返回十六進制表示（對於小數據）或長度信息
        if len(data) <= 20:
            return f"[Hex: {data.hex()}]"
        else:
            return f"[二進位資料, 長度 {len(data)} bytes]"

    def _prompt_to_save_if_needed(self) -> bool:
        if not self.has_unsaved_changes: return True
        ret = QMessageBox.question(self, "儲存變更", "您有未儲存的變更，要儲存嗎？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if ret == QMessageBox.StandardButton.Save: return self.save_image()
        return ret != QMessageBox.StandardButton.Cancel

    def _check_memory_usage(self) -> None:
        try:
            memory_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            logging.info(f"目前記憶體使用量: {memory_mb:.2f} MB")
            if memory_mb > Config.MEMORY_THRESHOLD_MB:
                logging.warning("記憶體用量超過閾值，開始清理快取。")
                self._cached_pixmaps.clear()
                self._cache_access_order.clear() # [優化建議 4A]
                self._base_pixmap = None
                gc.collect()
                self._display_image() # 清理後重繪
        except Exception as e: logging.error(f"檢查記憶體時出錯: {e}")

    @pyqtSlot(str, int)
    def _update_thumbnail_error(self, path: str, generation: int):
        if generation == self.filmstrip_generation and path in self.filmstrip_item_map:
            self.filmstrip_item_map[path].setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical))

    def _handle_load_error(self, title: str, msg: str, path: str):
        logging.error(f"載入失敗 (路徑: {path}): {title} - {msg}")
        QMessageBox.critical(self, title, msg)

    def _update_ui_state(self):
        """代理呼叫 UIManager 的 UI 狀態更新方法。"""
        self.ui_manager.update_ui_state()

    # [優化建議 10] 為關於對話框添加快捷鍵說明
    # [v1.4.4 修正] 增加 checked 參數
    def _show_about_dialog(self, checked: bool = False):
        """顯示關於對話框"""
        shortcuts_html = """
        <p><b>常用快捷鍵:</b></p>
        <ul style="list-style-type:none; padding-left:0;">
            <li><b>Ctrl+O</b>: 開啟檔案</li>
            <li><b>Ctrl+S</b>: 儲存</li>
            <li><b>Ctrl+Z</b>: 復原</li>
            <li><b>Ctrl+M</b>: 開啟/關閉放大鏡</li>
            <li><b>Ctrl+T</b>: 切換主題</li>
            <li><b>&larr; / &rarr;</b> (方向鍵): 上一張/下一張</li>
            <li><b>滑鼠滾輪</b>: 縮放</li>
        </ul>
        """

        QMessageBox.about(self, "關於", f"""
            <h3>{Config.BASE_WINDOW_TITLE}</h3>
            <p>一個使用 PyQt6 和 Pillow 打造的高效能圖片瀏覽與編輯工具。</p>
            {shortcuts_html}
        """)

    @pyqtSlot(QListWidgetItem)
    def on_filmstrip_item_selected(self, current: QListWidgetItem):
        if self._is_programmatic_selection or not current: return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path and path != self.current_path and self._prompt_to_save_if_needed(): self.load_image(path)

    # [v1.4.4 修正] 增加 checked 參數
    def prev_image(self, checked: bool = False):
        if self.current_index > 0 and self._prompt_to_save_if_needed(): self.load_image(self.image_list[self.current_index - 1])

    # [v1.4.4 修正] 增加 checked 參數
    def next_image(self, checked: bool = False):
        if self.current_index < len(self.image_list) - 1 and self._prompt_to_save_if_needed(): self.load_image(self.image_list[self.current_index + 1])

    # [v1.4.4 修正] 增加 checked 參數
    def zoom_in(self, checked: bool = False):
        self.set_scale(self.scale * Config.ZOOM_IN_FACTOR)

    # [v1.4.4 修正] 增加 checked 參數
    def zoom_out(self, checked: bool = False):
        self.set_scale(self.scale * Config.ZOOM_OUT_FACTOR)

    @pyqtSlot(bool)
    def toggle_fit_to_window_mode(self, checked: bool):
        self.is_fit_to_window_mode = checked
        self.fit_to_window_action.setChecked(checked)
        policy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff if checked else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        self.scroll_area.setHorizontalScrollBarPolicy(policy); self.scroll_area.setVerticalScrollBarPolicy(policy)
        if checked and self.image: self.fit_to_window()

    # [v1.4.9 修正] 加入狀態列提示
    @pyqtSlot(bool)
    def toggle_magnifier(self, checked: bool):
        if checked and not self.image:
            QMessageBox.information(self, "提示", "請先載入圖片以使用放大鏡。")
            self.toggle_magnifier_action.setChecked(False); return
        self.magnifier_enabled = checked
        if checked:
            if not self.magnifier_window: self.magnifier_window = MagnifierWindow(self)
            self.magnifier_window.set_magnifier_params(self.image, self.scale, self.magnifier_factor)
            # 顯示使用提示
            self.status_bar.showMessage("放大鏡已啟用 - 將滑鼠移到圖片上查看放大效果", 3000)
        elif self.magnifier_window:
            self.magnifier_window.hide()
            self.status_bar.showMessage("放大鏡已關閉", 2000)

        if hasattr(self, 'magnifier_factor_spinbox'):
            self.magnifier_factor_spinbox.setEnabled(checked)

    # [Review 問題 5 修正 & 優化 4] 更新白平衡演算法
    @requires_image
    def _on_white_balance_slider_released(self):
        if not self._base_image_for_effects:
            return

        temp, tint = self.temp_slider.value(), self.tint_slider.value()

        def white_balance_func(img: Image.Image) -> Image.Image:
            img_rgb = img.convert('RGB')
            img_np = np.array(img_rgb, dtype=np.float32) / 255.0

            r, g, b = img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2]

            # [優化 4] 改進的色溫調整演算法
            temp_factor = temp / 100.0
            if temp_factor > 0:  # 暖色調
                r *= 1.0 + temp_factor * 0.8 # 稍微降低紅色的影響
                b *= 1.0 - temp_factor * 0.5 # 藍色減少幅度小於紅色增加幅度
            else:  # 冷色調
                r *= 1.0 + temp_factor * 0.5 # 紅色減少幅度小於藍色增加幅度
                b *= 1.0 - temp_factor * 0.8 # 稍微降低藍色的影響

            # [優化 4] 改進的色調調整 (稍微影響 R/B 以補償綠色變化)
            tint_factor = tint / 100.0
            g *= 1.0 + tint_factor * 0.6 # 主要影響綠色
            # 輕微反向調整 R/B，避免過度偏色
            r *= 1.0 - tint_factor * 0.1
            b *= 1.0 - tint_factor * 0.1

            img_np = np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0) * 255.0
            return Image.fromarray(img_np.astype(np.uint8)).convert(img.mode)

        self._apply_effect(white_balance_func)

    # [v1.4.9 修正 Review 6] 加入範圍檢查
    @requires_image
    def _on_fine_tune_slider_released(self):
        if not self._base_image_for_effects: return

        try:
            b = self.brightness_slider.value() / Config.ADJUSTMENT_DEFAULT
            c = self.contrast_slider.value() / Config.ADJUSTMENT_DEFAULT
            s = self.saturation_slider.value() / Config.ADJUSTMENT_DEFAULT

            # 驗證值的合理性 (Pillow Enhancers 通常接受 > 0 的值，2.0 是一個合理的上限)
            if not all(x >= 0 for x in [b, c, s]):
                 logging.warning(f"細緻調整值出現負數: B={b}, C={c}, S={s}")
                 # 可以選擇重設或忽略，這裡選擇裁切到最小值 0
                 b = max(0, b)
                 c = max(0, c)
                 s = max(0, s)
            # 可以選擇性地加入上限裁切，例如 2.0
            b = min(b, 2.0)
            c = min(c, 2.0)
            s = min(s, 2.0)

            def fine_tune_func(img: Image.Image) -> Image.Image:
                img_proc = img.copy()
                enhancer = ImageEnhance.Brightness(img_proc)
                img_proc = enhancer.enhance(b)
                enhancer = ImageEnhance.Contrast(img_proc)
                img_proc = enhancer.enhance(c)
                enhancer = ImageEnhance.Color(img_proc)
                img_proc = enhancer.enhance(s)
                return img_proc

            self._apply_effect(fine_tune_func)

        except Exception as e:
            logging.error(f"細緻調整時發生錯誤: {e}")
            QMessageBox.warning(self, "調整失敗", f"無法應用調整: {e}")


    # [Review 問題 1 修正] 重設 flag
    @pyqtSlot(object, int)
    def _handle_effect_result(self, new_image: Image.Image, effect_id: int):
        # [Review 問題 2 建議邏輯] 只處理當前 ID
        if effect_id != self._current_effect_id:
            try:
                new_image.close()
            except Exception as e:
                logging.warning(f"關閉過時效果圖片失敗: {e}")
            logging.debug(f"忽略過時效果 ID: {effect_id} (當前: {self._current_effect_id})")
            return

        # 處理當前效果
        try:
            if self.image:
                self.image.close()
            self.image = new_image

            # 更新基礎圖像
            if self._base_image_for_effects:
                self._base_image_for_effects.close()

            self._base_image_for_effects = self.image.copy()

            # 清理快取
            self._cached_pixmaps.clear()
            self._cache_access_order.clear() # [優化建議 4A]
            self._base_pixmap = None

            # 顯示更新
            self._display_image()
            self.histogram_widget.update_histogram(self.image)
            self.set_unsaved_changes(True)

        except Exception as e:
            logging.critical(f"處理效果結果時複製基礎圖片失敗: {e}")
            QMessageBox.critical(self, "嚴重錯誤", f"無法更新圖片狀態: {e}。建議重新載入圖片。")
            self._cleanup_image_resources()
            self._update_ui_state()
        finally:
            # 無論成功或失敗，都重置處理狀態
            if self.effect_thread:
                self.effect_thread.quit() # 嘗試正常退出
            self._is_effect_processing = False # 重設 flag
            QApplication.restoreOverrideCursor() # 恢復游標


    # [Review 問題 1 修正] 重設 flag
    @pyqtSlot(str, int)
    def _handle_effect_error(self, error_msg: str, effect_id: int):
        # [Review 問題 2 建議邏輯] 只處理當前 ID
        if effect_id != self._current_effect_id:
            logging.debug(f"忽略過時效果錯誤 ID: {effect_id}")
            return

        QApplication.restoreOverrideCursor() # 確保游標恢復
        QMessageBox.critical(self, "效果套用失敗", error_msg)

        try:
            self.undo(is_effect_failure=True)
        except Exception as e:
            logging.error(f"效果失敗後復原時出錯: {e}")

        if self.effect_thread:
            self.effect_thread.quit()
        self._is_effect_processing = False # 重設 flag

    def _stop_effect_thread(self):
        if self.effect_thread and self.effect_thread.isRunning():
            logging.debug(f"正在停止效果執行緒 (ID: {self._current_effect_id})...")
            if self.effect_worker: self.effect_worker.request_stop()
            self.effect_thread.quit()
            if not self.effect_thread.wait(1000):
                logging.warning("效果執行緒未在1秒內結束，強制終止。")
                self.effect_thread.terminate()
            self._cleanup_thread_references_only()
            # 確保游標和 flag 被重設 (即使執行緒是外部停止的)
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
            self._is_effect_processing = False # 強制重設

    def _cleanup_thread(self):
        # 執行緒正常結束時調用
        logging.debug(f"效果執行緒 finished 信號觸發 (ID: {self._current_effect_id})")
        # 不需要恢復游標或重設 flag，因為 handle_result/error 會做
        self._cleanup_thread_references_only()

    def _cleanup_thread_references_only(self):
        self.effect_thread, self.effect_worker = None, None

    def update_magnifier_position_and_content(self, pos: QPoint):
        if not self.magnifier_window or not self.image: return

        # 確保 pos 在 image_label 範圍內
        if not self.image_label.rect().contains(pos):
             self.magnifier_window.hide()
             return

        self.magnifier_window.update_magnified_view(pos) # 呼叫修正後的放大鏡更新
        global_pos = self.image_label.mapToGlobal(pos)
        screen_rect = QApplication.primaryScreen().availableGeometry()

        x, y = global_pos.x() + 20, global_pos.y() + 20

        if x + self.magnifier_window.width() > screen_rect.right():
            x = global_pos.x() - self.magnifier_window.width() - 20
        if y + self.magnifier_window.height() > screen_rect.bottom():
            y = global_pos.y() - self.magnifier_window.height() - 20

        self.magnifier_window.move(x, y)
        if not self.magnifier_window.isVisible():
            self.magnifier_window.show()

    # [修正 Bug 3] 增強縮放輸入驗證
    def _on_zoom_entry_submit(self):
        """處理縮放輸入框的提交"""
        try:
            text = self.zoom_entry.text().strip()
            if not text:
                return

            # 移除非數字和小數點字符，允許百分號
            has_percent = '%' in text
            clean_text = re.sub(r'[^\d.]', '', text.replace('%',''))

            # 檢查是否為空、只有點、或多個點
            if not clean_text or clean_text == '.' or clean_text.count('.') > 1:
                self.status_bar.showMessage("無效的縮放值", 2000)
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%") # 恢復顯示
                return

            value = float(clean_text)

            # 增加負數和異常值檢查
            if value <= 0:
                self.status_bar.showMessage("縮放值必須大於 0", 2000)
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
                return

            if value > 10000:  # 防止極端值 (例如 10000%)
                self.status_bar.showMessage("縮放值過大 (上限 1000%)", 2000)
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
                return


            # 判斷是百分比還是倍數
            # 假設輸入時包含 '%' 或數字大於 10 (考慮到允許輸入 10 倍) 就視為百分比
            if has_percent or (value > 10 and '.' not in text): # 避免 1.5 被當作 150%
                scale = value / 100.0
            else: # 否則視為倍數
                scale = value

            # 限制縮放範圍 (0.01 to 10.0)
            scale = max(0.01, min(scale, 10.0))

            self.set_scale(scale)
            # 更新輸入框顯示，統一格式
            self.zoom_entry.setText(f"{self.scale * 100:.1f}%")

        except ValueError:
            self.status_bar.showMessage("無效的縮放值", 2000)
            logging.warning(f"無效的縮放輸入: {self.zoom_entry.text()}")
            # 恢復顯示當前縮放比例
            self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
        except Exception as e: # 捕獲其他潛在錯誤
            logging.error(f"處理縮放輸入時發生錯誤: {e}")
            self.status_bar.showMessage("處理縮放輸入時出錯", 2000)
            self.zoom_entry.setText(f"{self.scale * 100:.1f}%")


# ==============================================================================
# 6. UI 與主題管理器 (UIManager, ThemeManager)
# ==============================================================================
class UIManager:
    def __init__(self, main_window: ImageEditorWindow): self.win = main_window

    # [Review 問題 6 修正] 改進 startup_label 佈局
    def setup_ui(self):
        self.win.image_label = QLabel()
        self.win.image_label.setObjectName("imageLabel")
        self.win.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.win.image_label.setMouseTracking(True)
        # [優化 5] 添加工具提示
        self.win.image_label.setToolTip(
            "滑鼠滾輪: 縮放\n"
            "左鍵拖曳: 平移\n"
            "Ctrl+M: 開啟/關閉放大鏡"
        )


        self.win.scroll_area = QScrollArea()
        self.win.scroll_area.setObjectName("scrollArea")
        self.win.scroll_area.setWidget(self.win.image_label)
        self.win.scroll_area.setWidgetResizable(True)
        self.win.setCentralWidget(self.win.scroll_area)

        # 創建啟動提示容器 (使其能覆蓋 scroll_area)
        self.win.startup_container = QWidget(self.win.scroll_area.viewport()) # 父元件設為 viewport
        startup_layout = QVBoxLayout(self.win.startup_container)
        startup_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        startup_layout.setContentsMargins(0,0,0,0) # 無邊距

        self.win.startup_label = QLabel("拖曳圖片至此，或點擊左上角「開啟」")
        self.win.startup_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win.startup_label.setStyleSheet("""
            color: #888;
            font-size: 20px;
            padding: 20px;
            background-color: transparent;
        """)

        startup_layout.addWidget(self.win.startup_label)
        self.win.startup_container.setStyleSheet("background-color: transparent;")
        self.win.startup_container.lower() # 確保它在 image_label 下方 (如果 image_label 有內容)
        self.win.startup_container.setVisible(True) # 初始可見

        # 確保初始位置正確
        self.win.startup_container.setGeometry(self.win.scroll_area.viewport().rect())


    def create_actions(self):
        self.icon_map = {
            "document-open": QStyle.StandardPixmap.SP_DialogOpenButton,
            "document-save": QStyle.StandardPixmap.SP_DialogSaveButton,
            "document-save-as": QStyle.StandardPixmap.SP_DialogSaveButton,
            "application-exit": QStyle.StandardPixmap.SP_DialogCloseButton,
            "edit-undo": QStyle.StandardPixmap.SP_ArrowBack,
            "zoom-in": QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton,
            "zoom-out": QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton,
            "zoom-fit-best": QStyle.StandardPixmap.SP_DesktopIcon,
            "zoom-original": QStyle.StandardPixmap.SP_ComputerIcon,
            "go-previous": QStyle.StandardPixmap.SP_ArrowBack,
            "go-next": QStyle.StandardPixmap.SP_ArrowForward,
            "object-rotate-left": QStyle.StandardPixmap.SP_ArrowLeft,
            "object-rotate-right": QStyle.StandardPixmap.SP_ArrowRight,
            "help-about": QStyle.StandardPixmap.SP_MessageBoxInformation,
        }
        self.win.open_action = self._create_action("開啟...", "document-open", QKeySequence.StandardKey.Open, self.win.open_file_dialog)
        self.win.save_action = self._create_action("儲存", "document-save", QKeySequence.StandardKey.Save, self.win.save_image)
        self.win.save_as_action = self._create_action("另存為...", "document-save-as", QKeySequence.StandardKey.SaveAs, self.win.save_image_as)
        self.win.exit_action = self._create_action("離開", "application-exit", None, self.win.close)
        self.win.undo_action = self._create_action("復原", "edit-undo", QKeySequence.StandardKey.Undo, self.win.undo)
        self.win.zoom_in_action = self._create_action("放大", "zoom-in", QKeySequence.StandardKey.ZoomIn, self.win.zoom_in)
        self.win.zoom_out_action = self._create_action("縮小", "zoom-out", QKeySequence.StandardKey.ZoomOut, self.win.zoom_out)
        self.win.fit_to_window_action = self._create_action("最適化顯示", "zoom-fit-best", None, self.win.toggle_fit_to_window_mode, is_checkable=True, checked=True)
        self.win.toggle_magnifier_action = self._create_action("放大鏡", "zoom-original", "Ctrl+M", self.win.toggle_magnifier, is_checkable=True)
        self.win.toggle_theme_action = self._create_action("切換主題", "preferences-desktop-theme", "Ctrl+T", lambda: self.win.theme_manager.toggle_theme())
        self.win.prev_action = self._create_action("上一張", "go-previous", Qt.Key.Key_Left, self.win.prev_image)
        self.win.next_action = self._create_action("下一張", "go-next", Qt.Key.Key_Right, self.win.next_image)
        self.win.resize_action = self._create_action("調整尺寸...", "transform-scale", None, lambda: self._open_resize_dialog())

        # [優化建議 2] 效果 lambda 應基於 _base_image_for_effects
        self.win.rotate_left_action = self._create_action("向左旋轉", "object-rotate-left", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.ROTATE_90)))
        self.win.rotate_right_action = self._create_action("向右旋轉", "object-rotate-right", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.ROTATE_270)))
        self.win.flip_horizontal_action = self._create_action("水平翻轉", "object-flip-horizontal", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))
        self.win.flip_vertical_action = self._create_action("垂直翻轉", "object-flip-vertical", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)))
        self.win.about_action = self._create_action("關於", "help-about", None, self.win._show_about_dialog)

    def create_menus(self):
        mb = self.win.menuBar()
        mb.addMenu("&檔案").addActions([self.win.open_action, self.win.save_action, self.win.save_as_action, self.win.exit_action])
        edit_menu = mb.addMenu("&編輯"); edit_menu.addAction(self.win.undo_action); edit_menu.addSeparator()
        transform_menu = edit_menu.addMenu("變換"); transform_menu.addActions([self.win.resize_action, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action])
        view_menu = mb.addMenu("&檢視"); view_menu.addActions([self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action]); view_menu.addSeparator()
        view_menu.addAction(self.win.toggle_magnifier_action); view_menu.addSeparator()
        view_menu.addActions([self.win.exif_dock.toggleViewAction(), self.win.effects_dock.toggleViewAction(), self.win.filmstrip_dock.toggleViewAction(), self.win.histogram_dock.toggleViewAction()])
        view_menu.addSeparator(); view_menu.addAction(self.win.toggle_theme_action)
        help_menu = mb.addMenu("&說明")
        help_menu.addAction(self.win.about_action)

    def create_toolbars(self):
        self._create_toolbar("檔案", [self.win.open_action, self.win.save_action])
        view_tb = self._create_toolbar("檢視", [self.win.prev_action, self.win.next_action, None, self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action, None, self.win.toggle_magnifier_action])
        self.win.magnifier_factor_spinbox = QDoubleSpinBox(); self.win.magnifier_factor_spinbox.setRange(*Config.MAGNIFIER_FACTOR_RANGE)
        self.win.magnifier_factor_spinbox.setSingleStep(0.5); self.win.magnifier_factor_spinbox.setValue(self.win.magnifier_factor)
        self.win.magnifier_factor_spinbox.setPrefix("放大: "); self.win.magnifier_factor_spinbox.setSuffix("x")
        self.win.magnifier_factor_spinbox.valueChanged.connect(lambda v: setattr(self.win, 'magnifier_factor', v)); view_tb.addWidget(self.win.magnifier_factor_spinbox)
        self._create_toolbar("變換", [self.win.undo_action, None, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action])
    def create_docks(self):
        self.win.exif_tree = QTreeWidget(); self.win.exif_tree.setHeaderLabels(["標籤", "值"]); self.win.exif_tree.setColumnWidth(0, 150)
        self.win.exif_dock = self._create_dock("EXIF 資訊", Qt.DockWidgetArea.RightDockWidgetArea, self.win.exif_tree, visible=False)
        self.win.effects_dock = self._create_dock("效果與調整", Qt.DockWidgetArea.RightDockWidgetArea, self._create_effects_panel())
        self.win.histogram_widget = HistogramWidget(); self.win.histogram_dock = self._create_dock("直方圖", Qt.DockWidgetArea.RightDockWidgetArea, self.win.histogram_widget, visible=False)
        self.win.filmstrip_widget = QListWidget()
        self.win.filmstrip_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.win.filmstrip_widget.setFlow(QListWidget.Flow.LeftToRight)
        self.win.filmstrip_widget.setMovement(QListWidget.Movement.Static)
        self.win.filmstrip_widget.setIconSize(Config.THUMBNAIL_SIZE)
        self.win.filmstrip_widget.setSpacing(10)
        self.win.filmstrip_widget.setGridSize(QSize(Config.THUMBNAIL_SIZE.width() + 12, Config.THUMBNAIL_SIZE.height() + 12))
        self.win.filmstrip_widget.setWrapping(False)
        self.win.filmstrip_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.win.filmstrip_widget.currentItemChanged.connect(self.win.on_filmstrip_item_selected)
        self.win.filmstrip_dock = self._create_dock("預覽", Qt.DockWidgetArea.BottomDockWidgetArea, self.win.filmstrip_widget)
        self.win.filmstrip_dock.setFixedHeight(160)
    def update_ui_state(self):
        has_image = self.win.image is not None
        # [Review 問題 6] 控制 startup_container 的可見性
        self.win.startup_container.setVisible(not has_image)

        actions_to_toggle = [self.win.save_action, self.win.save_as_action, self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action, self.win.resize_action, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action, self.win.toggle_magnifier_action]
        for action in actions_to_toggle: action.setEnabled(has_image)
        self.win.undo_action.setEnabled(bool(self.win.undo_stack))
        self.win.prev_action.setEnabled(has_image and self.win.current_index > 0)
        self.win.next_action.setEnabled(has_image and self.win.current_index < len(self.win.image_list) - 1)
        if hasattr(self.win, 'effects_dock'): self.win.effects_dock.widget().setEnabled(has_image)
        if hasattr(self.win, 'magnifier_factor_spinbox'): self.win.magnifier_factor_spinbox.setEnabled(has_image and self.win.magnifier_enabled)

    # [Review 問題 3 修正] 使用 blockSignals
    def reset_adjustment_sliders(self):
        if not hasattr(self.win, 'temp_slider'):
            return

        sliders = [
            self.win.temp_slider,
            self.win.tint_slider,
            self.win.brightness_slider,
            self.win.contrast_slider,
            self.win.saturation_slider
        ]

        # 阻塞信號
        for slider in sliders:
            slider.blockSignals(True)

        # 重設值
        self.win.temp_slider.setValue(0)
        self.win.tint_slider.setValue(0)
        self.win.brightness_slider.setValue(Config.ADJUSTMENT_DEFAULT)
        self.win.contrast_slider.setValue(Config.ADJUSTMENT_DEFAULT)
        self.win.saturation_slider.setValue(Config.ADJUSTMENT_DEFAULT)

        # 更新 QLabel (因為 valueChanged 被阻塞了)
        if hasattr(self.win, 'temp_value_label'): self.win.temp_value_label.setText("0")
        if hasattr(self.win, 'tint_value_label'): self.win.tint_value_label.setText("0")
        if hasattr(self.win, 'brightness_value_label'): self.win.brightness_value_label.setText(f"{Config.ADJUSTMENT_DEFAULT}%")
        if hasattr(self.win, 'contrast_value_label'): self.win.contrast_value_label.setText(f"{Config.ADJUSTMENT_DEFAULT}%")
        if hasattr(self.win, 'saturation_value_label'): self.win.saturation_value_label.setText(f"{Config.ADJUSTMENT_DEFAULT}%")

        # 恢復信號
        for slider in sliders:
            slider.blockSignals(False)

    def _create_action(self, text, icon_name, shortcut, slot, is_checkable=False, checked=False):
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull() and icon_name in self.icon_map:
            icon = self.win.style().standardIcon(self.icon_map[icon_name])
        action = QAction(icon, text, self.win)
        if shortcut: action.setShortcut(shortcut)
        if slot: action.triggered.connect(slot)
        if is_checkable: action.setCheckable(True); action.setChecked(checked)
        return action
    def _create_toolbar(self, title, actions):
        toolbar = self.win.addToolBar(title); toolbar.setIconSize(QSize(22, 22))
        for action in actions:
            if action: toolbar.addAction(action)
            else: toolbar.addSeparator()
        return toolbar
    def _create_dock(self, title, area, widget, visible=True):
        dock = QDockWidget(title, self.win); dock.setWidget(widget)
        self.win.addDockWidget(area, dock); dock.setVisible(visible)
        return dock
    def _create_effects_panel(self) -> QWidget:
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        zoom_layout = QFormLayout(); self.win.zoom_entry = QLineEdit()
        self.win.zoom_entry.setFixedWidth(70)
        # [Review 問題 2 修正] 連接到新的處理方法
        self.win.zoom_entry.returnPressed.connect(self.win._on_zoom_entry_submit)
        zoom_layout.addRow("指定縮放:", self.win.zoom_entry); layout.addLayout(zoom_layout)

        self.win.fine_tune_group = self._create_slider_group("細緻調整", [("亮度", "brightness", self.win._on_fine_tune_slider_released), ("對比", "contrast", self.win._on_fine_tune_slider_released), ("飽和", "saturation", self.win._on_fine_tune_slider_released)], range=(Config.ADJUSTMENT_RANGE[0], Config.ADJUSTMENT_RANGE[1]), default=Config.ADJUSTMENT_DEFAULT, suffix="%")
        layout.addWidget(self.win.fine_tune_group)

        self.win.white_balance_group = self._create_slider_group("白平衡", [("色溫", "temp", self.win._on_white_balance_slider_released), ("色調", "tint", self.win._on_white_balance_slider_released)], range=(Config.WHITE_BALANCE_TEMP_RANGE[0], Config.WHITE_BALANCE_TINT_RANGE[1]), default=0)
        layout.addWidget(self.win.white_balance_group)

        filters_group = QGroupBox("濾鏡"); filters_layout = QVBoxLayout(filters_group)
        effect_configs = [
            {"name": "反轉圖片", "func": lambda img: ImageOps.invert(img.convert("RGB")).convert("RGBA")},
            {"name": "轉為灰階", "func": lambda img: img.convert("L").convert("RGBA")},
            {"name": "模糊", "func": lambda img: img.filter(ImageFilter.GaussianBlur(radius=Config.BLUR_RADIUS))},
            {"name": "銳化", "func": lambda img: img.filter(ImageFilter.SHARPEN)},
            {"name": "懷舊", "func": lambda img: ImageOps.colorize(img.convert("L"), "#704214", "#C0A080").convert("RGBA")}
        ]
        for config in effect_configs:
            btn = QPushButton(config["name"])
            btn.clicked.connect(lambda _, f=config["func"]: self.win._apply_effect(f))
            filters_layout.addWidget(btn)
        layout.addWidget(filters_group)
        return panel
    def _create_slider_group(self, title, sliders_config, range, default, suffix=""):
        group_box = QGroupBox(title); group_layout = QFormLayout(group_box)
        for label, name, slot in sliders_config:
            slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(*range); slider.setValue(default)
            slider.sliderReleased.connect(slot)
            value_label = QLabel(f"{default}{suffix}")
            value_label.setFixedWidth(40) # 固定寬度避免跳動
            slider.valueChanged.connect(lambda v, lbl=value_label, s=suffix: lbl.setText(f"{v}{s}"))
            row_layout = QHBoxLayout(); row_layout.addWidget(slider); row_layout.addWidget(value_label)
            group_layout.addRow(f"{label}:", row_layout)
            setattr(self.win, f"{name}_slider", slider); setattr(self.win, f"{name}_value_label", value_label)
        return group_box

    @requires_image
    def _open_resize_dialog(self):
        # [v1.4.4 修正] 確保 image 存在 (雖然 decorator 已經做了)
        if not self.win.image: return
        dialog = ResizeDialog(QSize(self.win.image.width, self.win.image.height), self.win)
        if new_size := dialog.get_dimensions():
            self.win._apply_effect(lambda img: img.resize((new_size.width(), new_size.height()), LANCZOS_RESAMPLE))

class ThemeManager:
    def __init__(self, app: QApplication): self.app = app; self.is_dark = False
    def toggle_theme(self, is_dark: Optional[bool] = None):
        self.is_dark = not self.is_dark if is_dark is None else is_dark
        if self.is_dark:
            self._apply_dark_palette()
            self.app.setStyleSheet(self._get_modern_dark_stylesheet())
        else:
            self.app.setPalette(self.app.style().standardPalette())
            self.app.setStyleSheet("")

    def _apply_dark_palette(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(37, 37, 37))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        self.app.setPalette(dark_palette)

    def _get_modern_dark_stylesheet(self) -> str:
        return """
        /* === General === */
        QWidget {
            color: #dcdcdc;
            font-family: 'Segoe UI', 'Microsoft JhengHei', 'Helvetica', sans-serif;
        }
        QMainWindow, QDialog {
            background-color: #252525;
        }

        /* === ScrollArea & Image Label === */
        QScrollArea#scrollArea {
            border: none;
            background-color: #1e1e1e;
        }
        QLabel#imageLabel {
            background-color: #1e1e1e; /* 更深的背景突顯圖片 */
        }

        /* === Docks & Panels === */
        QDockWidget {
            titlebar-close-icon: none; /* 隱藏原生按鈕 */
            titlebar-normal-icon: none;
        }
        QDockWidget::title {
            background-color: #333333;
            padding: 8px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            font-weight: bold;
        }
        QDockWidget > QWidget {
            border: 1px solid #3c3c3c;
            border-top: none;
        }
        
        /* === Lists & Trees (EXIF, Filmstrip) === */
        QTreeWidget, QListWidget {
            background-color: #2c2c2c;
            border: 1px solid #3c3c3c;
            padding: 5px;
            border-radius: 4px;
        }
        QListWidget::item {
            border-radius: 4px;
            padding: 4px;
        }
        QListWidget::item:hover {
            background-color: #383838;
        }
        QListWidget::item:selected {
            background-color: rgba(0, 120, 215, 0.5);
            border: 1px solid #0078d7;
            color: #ffffff;
        }
        QHeaderView::section {
            background-color: #383838;
            padding: 6px;
            border: none;
            border-bottom: 1px solid #454545;
        }

        /* === Buttons === */
        QPushButton {
            background-color: #3e3e3e;
            border: 1px solid #555555;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
            border-color: #6a6a6a;
        }
        QPushButton:pressed {
            background-color: #333333;
        }
        QPushButton:disabled {
            background-color: #303030;
            color: #777777;
            border-color: #444444;
        }
        
        /* === Sliders === */
        QSlider::groove:horizontal {
            height: 4px;
            background: #444444;
            margin: 2px 0;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #0078d7;
            border: 1px solid #0078d7;
            width: 18px;
            height: 18px;
            margin: -7px 0;
            border-radius: 9px;
        }

        /* === GroupBox === */
        QGroupBox {
            border: 1px solid #3c3c3c;
            border-radius: 6px;
            margin-top: 1ex;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
        }
        
        /* === Input Fields === */
        QLineEdit, QSpinBox, QDoubleSpinBox {
            background-color: #333333;
            padding: 6px;
            border: 1px solid #444444;
            border-radius: 4px;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border-color: #0078d7;
        }

        /* === ToolBar, MenuBar, StatusBar === */
        QToolBar {
            background-color: #2d2d2d;
            border: none;
            padding: 4px;
            spacing: 6px;
        }
        QStatusBar {
            background-color: #2d2d2d;
            border-top: 1px solid #3c3c3c;
        }
        QStatusBar QProgressBar {
            background-color: #3e3e3e;
            border: 1px solid #555;
            border-radius: 4px;
            text-align: center;
            color: #dcdcdc; /* 進度條文字顏色 */
        }
        QStatusBar QProgressBar::chunk {
            background-color: #0078d7;
            border-radius: 4px; /* 使填充部分也有圓角 */
        }
        
        QMenuBar {
            background-color: #2d2d2d;
        }
        QMenuBar::item:selected {
            background-color: #3e3e3e;
        }
        QMenu {
            background-color: #2c2c2c;
            border: 1px solid #444444;
            padding: 4px;
        }
        QMenu::item:selected {
            background-color: #0078d7;
        }
        
        /* === ScrollBar === */
        QScrollBar:vertical {
            border: none;
            background: #2c2c2c;
            width: 12px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #2c2c2c;
            height: 12px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #555555;
            min-height: 25px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal {
            background: #555555;
            min-width: 25px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
            background: #6a6a6a;
        }
        QScrollBar::add-line, QScrollBar::sub-line {
            height: 0px;
            width: 0px;
        }
        
        /* === Tooltip === */
        QToolTip {
            background-color: #1e1e1e;
            color: #dcdcdc;
            border: 1px solid #3c3c3c;
            padding: 5px;
            border-radius: 4px;
        }
        """

# ==============================================================================
# 7. 應用程式入口
# ==============================================================================
def main() -> None:
    """主函式，用於啟動應用程式。"""

    app = QApplication(sys.argv)

    # [修正] 將 validate 呼叫移至 QApplication 初始化之後
    # [優化建議 6] 在應用啟動時驗證
    try:
        Config.validate()
    except AssertionError as e:
        logging.critical(f"設定檔驗證失敗: {e}")
        # 現在可以安全地顯示 QMessageBox
        QMessageBox.critical(None, "設定錯誤", f"應用程式設定錯誤，無法啟動:\n{e}")
        sys.exit(1)

    # [移除] 移除了設定 Base64 圖示的相關程式碼

    window = ImageEditorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()

