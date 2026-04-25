"""圖片預覽面板 — 顯示選中圖片的大圖與詳細資訊。"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QSizePolicy,
)
from image_viewer.duplicate_checker.core.utils import format_size


class PreviewPanel(QWidget):
    """圖片預覽面板。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        title = QLabel("🖼️ 圖片預覽")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        # 圖片顯示區域（可捲動）
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._image_label = QLabel("選擇圖片以預覽")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self._image_label.setMinimumHeight(200)
        self._image_label.setStyleSheet(
            "QLabel { background-color: #111; border-radius: 12px; "
            "color: #555; font-size: 14px; padding: 20px; border: 1px solid #222; }"
        )
        self._scroll.setWidget(self._image_label)
        layout.addWidget(self._scroll, 1)

        # 檔案資訊區域
        self._info_label = QLabel("")
        self._info_label.setObjectName("statsLabel")
        self._info_label.setWordWrap(True)
        self._info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._info_label.setStyleSheet(
            "QLabel { background-color: #1e1e1e; border: 1px solid #333; "
            "border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.8; color: #ccc; }"
        )
        layout.addWidget(self._info_label)

    def show_image(self, filepath: str) -> None:
        """顯示指定路徑的圖片。"""
        self._current_path = filepath
        path = Path(filepath)

        if not path.exists():
            self._image_label.setText("⚠️ 檔案不存在")
            self._info_label.setText("")
            return

        # 載入圖片並保存原圖
        self._original_pixmap = QPixmap(filepath)
        if self._original_pixmap.isNull():
            self._image_label.setText("⚠️ 無法載入圖片")
            self._info_label.setText("")
            return

        # 更新顯示
        self._update_preview()

        # 顯示檔案資訊
        try:
            stat = path.stat()
            mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            info_text = (
                f"📄 <b>檔案名稱:</b> {path.name}<br>"
                f"📂 <b>所在路徑:</b> {path.parent}<br>"
                f"📐 <b>圖片尺寸:</b> {self._original_pixmap.width()} × {self._original_pixmap.height()} 像素<br>"
                f"💾 <b>檔案大小:</b> {format_size(stat.st_size)}<br>"
                f"📅 <b>修改日期:</b> {mod_time}"
            )
            self._info_label.setText(info_text)
        except Exception:
            self._info_label.setText(f"📄 {path.name}")

    def _update_preview(self) -> None:
        """根據視窗可用空間重新縮放圖片。"""
        if not hasattr(self, "_original_pixmap") or self._original_pixmap.isNull():
            return

        # 使用 viewport 大小而非 label 大小，以避免無限放大迴圈
        viewport_size = self._scroll.viewport().size()
        
        # 扣除微小像素避免觸發捲動軸
        w = max(10, viewport_size.width() - 4)
        h = max(10, viewport_size.height() - 4)

        scaled = self._original_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def clear(self) -> None:
        """清除預覽。"""
        self._image_label.clear()
        self._image_label.setText("選擇圖片以預覽")
        self._info_label.setText("")
        self._current_path = ""
        self._original_pixmap = QPixmap()

    def resizeEvent(self, event) -> None:
        """視窗大小改變時重新縮放圖片。"""
        super().resizeEvent(event)
        self._update_preview()

