import logging
import traceback
from typing import Dict, List, Optional
from PIL import Image
from PIL.ImageQt import ImageQt

from PyQt6.QtWidgets import (
    QWidget, QDialog, QSpinBox, QCheckBox, QFormLayout, QVBoxLayout, 
    QDialogButtonBox, QLabel
)
from PyQt6.QtGui import (
    QPainter, QPalette, QPen, QColor, QFont, QPixmap, QBrush, QPainterPath
)
from PyQt6.QtCore import Qt, QSize, QRectF, QPoint

from image_viewer.config import Config, LANCZOS_RESAMPLE

class HistogramWidget(QWidget):
    def __init__(self, config: Config, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.setFixedSize(self.config.HISTOGRAM_WIDTH, self.config.HISTOGRAM_HEIGHT)
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
        """更新直方圖數據 (NumPy 優化版本)"""
        if image is None:
            self.hist_data = {k: [0]*256 for k in self.hist_data}
            self.max_val = 1
        else:
            try:
                import numpy as np
                
                # 轉換為 RGB 模式並縮小圖片以加速直方圖計算 (256x256 的樣本數已足夠)
                if image.mode not in ('RGB', 'L'):
                    img_for_hist = image.convert('RGB')
                else:
                    img_for_hist = image.copy()
                
                img_for_hist.thumbnail((256, 256), Image.Resampling.NEAREST)
                
                # 使用 NumPy 計算直方圖 (比 PIL histogram() 更快)
                img_array = np.array(img_for_hist)
                
                if img_for_hist.mode == 'L':
                    # 灰階圖
                    lum_hist, _ = np.histogram(img_array.flatten(), bins=256, range=(0, 256))
                    self.hist_data = {
                        'r': [0]*256, 'g': [0]*256, 'b': [0]*256, 
                        'lum': lum_hist.tolist()
                    }
                    self.max_val = int(lum_hist.max()) if lum_hist.max() > 0 else 1
                else:
                    # RGB 圖 - 分別計算各通道
                    r_hist, _ = np.histogram(img_array[:,:,0].flatten(), bins=256, range=(0, 256))
                    g_hist, _ = np.histogram(img_array[:,:,1].flatten(), bins=256, range=(0, 256))
                    b_hist, _ = np.histogram(img_array[:,:,2].flatten(), bins=256, range=(0, 256))
                    
                    # 計算亮度直方圖 (使用 ITU-R BT.601 標準)
                    lum_array = (0.299 * img_array[:,:,0] + 0.587 * img_array[:,:,1] + 0.114 * img_array[:,:,2]).astype(np.uint8)
                    lum_hist, _ = np.histogram(lum_array.flatten(), bins=256, range=(0, 256))
                    
                    self.hist_data = {
                        'r': r_hist.tolist(),
                        'g': g_hist.tolist(),
                        'b': b_hist.tolist(),
                        'lum': lum_hist.tolist()
                    }
                    self.max_val = int(max(r_hist.max(), g_hist.max(), b_hist.max(), lum_hist.max()))
                    if self.max_val == 0:
                        self.max_val = 1
                        
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
            is_blocked = self.height_spinbox.signalsBlocked()
            self.height_spinbox.blockSignals(True)
            new_height = int(new_width / self.aspect_ratio) if self.aspect_ratio != 0 else 1
            self.height_spinbox.setValue(max(1, new_height))
            self.height_spinbox.blockSignals(is_blocked)
    def on_height_changed(self, new_height: int):
        if self.aspect_ratio_checkbox.isChecked():
            is_blocked = self.width_spinbox.signalsBlocked()
            self.width_spinbox.blockSignals(True)
            new_width = int(new_height * self.aspect_ratio)
            self.width_spinbox.setValue(max(1, new_width))
            self.width_spinbox.blockSignals(is_blocked)
    def get_dimensions(self) -> Optional[QSize]:
        return QSize(self.width_spinbox.value(), self.height_spinbox.value()) if self.exec() == QDialog.DialogCode.Accepted else None

class MagnifierWindow(QDialog):
    # 注意：這裡原本依賴 ImageEditorWindow 作為 parent，但為了避免循環依賴，我們將依賴抽象化
    # 實際上 parent 是 QWidget，但需要 access config 和 image_label 以及 image
    # 我們可以傳遞 config 和必要的參數
    
    def __init__(self, parent: QWidget, config: Config):
        super().__init__(parent)
        self.config = config
        
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setFixedSize(self.config.MAGNIFIER_SIZE, self.config.MAGNIFIER_SIZE)

        self.magnifier_label = QLabel(self)
        self.magnifier_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.magnifier_label.setStyleSheet("background-color: transparent;")
        self.magnifier_label.setFixedSize(self.config.MAGNIFIER_SIZE, self.config.MAGNIFIER_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.magnifier_label)

        self._source_image: Optional[Image.Image] = None
        self._main_image_display_scale: float = 1.0
        self._magnifier_factor: float = self.config.MAGNIFIER_DEFAULT_FACTOR

    def set_magnifier_params(self, source_image: Image.Image, main_image_display_scale: float, magnifier_factor: float):
        self._source_image, self._main_image_display_scale, self._magnifier_factor = source_image, main_image_display_scale, magnifier_factor
        self.magnifier_label.clear()

    def update_magnified_view(self, cursor_pos_on_label: QPoint, main_label_size: QSize, main_label_pixmap: QPixmap):
        if self._source_image is None or self._main_image_display_scale <= 0: return

        if not main_label_pixmap or main_label_pixmap.isNull():
            return

        magnifier_w, magnifier_h = self.width(), self.height()
        sample_w = int(magnifier_w / self._magnifier_factor)
        sample_h = int(magnifier_h / self._magnifier_factor)
        if sample_w <= 0 or sample_h <= 0: return

        pixmap_size = main_label_pixmap.size()
        scaled_pixmap_size = pixmap_size.scaled(main_label_size, Qt.AspectRatioMode.KeepAspectRatio)

        offset_x = (main_label_size.width() - scaled_pixmap_size.width()) / 2
        offset_y = (main_label_size.height() - scaled_pixmap_size.height()) / 2

        adjusted_x = cursor_pos_on_label.x() - offset_x
        adjusted_y = cursor_pos_on_label.y() - offset_y

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

            circular_pixmap = self._create_circular_pixmap(pixmap, magnifier_w)
            self.magnifier_label.setPixmap(circular_pixmap)

        except Exception as e:
            logging.error(f"更新放大鏡時出錯: {e}\n{traceback.format_exc()}")
        finally:
            if cropped_image:
                try: cropped_image.close()
                except Exception as e_close: logging.warning(f"關閉 cropped_image 出錯: {e_close}")
            if magnified_pil:
                try: magnified_pil.close()
                except Exception as e_close: logging.warning(f"關閉 magnified_pil 出錯: {e_close}")

    def _create_circular_pixmap(self, source_pixmap: QPixmap, size: int) -> QPixmap:
        """創建帶平滑邊緣、邊框、背景、十字線和倍率文字的圓形 QPixmap"""
        target = QPixmap(size, size)
        target.fill(Qt.GlobalColor.transparent)

        painter = QPainter(target)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            margin = 1
            content_rect_f = QRectF(margin, margin, size - 2*margin, size - 2*margin)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
            painter.drawEllipse(content_rect_f)

            path = QPainterPath()
            path.addEllipse(content_rect_f)
            painter.setClipPath(path)

            source_rect = QRectF(source_pixmap.rect())
            painter.drawPixmap(content_rect_f, source_pixmap, source_rect)

            center_x = size / 2
            center_y = size / 2
            crosshair_size = 10
            
            pen = QPen(QColor(255, 255, 255, 200), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            
            painter.drawLine(int(center_x), int(center_y - crosshair_size),
                            int(center_x), int(center_y + crosshair_size))
            painter.drawLine(int(center_x - crosshair_size), int(center_y),
                            int(center_x + crosshair_size), int(center_y))
            
            painter.setPen(QPen(QColor(255, 0, 0, 200), 2))
            painter.drawPoint(int(center_x), int(center_y))

            painter.setClipping(False)

            pen = QPen(QColor("#0078d7"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(content_rect_f)
            
            painter.setClipping(False)
            painter.setPen(QPen(QColor(255, 255, 255, 255)))
            
            font = QFont("Arial", 10, QFont.Weight.Bold)
            painter.setFont(font)
            
            text = f"{self._magnifier_factor:.1f}x"
            text_rect = QRectF(0, size - 20, size, 20)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        finally:
            painter.end()
        return target
