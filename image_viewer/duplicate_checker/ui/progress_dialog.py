"""掃描進度對話框。"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
)


class ProgressDialog(QDialog):
    """掃描進度對話框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cancelled = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("掃描進度")
        self.setFixedSize(420, 180)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._title_label = QLabel("🔍 正在掃描...")
        self._title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #64ffda;")
        layout.addWidget(self._title_label)

        self._message_label = QLabel("準備中...")
        self._message_label.setStyleSheet("color: #aaa;")
        layout.addWidget(self._message_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(0)  # 不確定模式
        layout.addWidget(self._progress_bar)

        self._cancel_btn = QPushButton("取消掃描")
        self._cancel_btn.setObjectName("dangerBtn")
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn)

    def update_progress(self, current: int, total: int, message: str) -> None:
        """更新進度。"""
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)
        self._message_label.setText(message)

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("正在取消...")
        self._message_label.setText("正在取消掃描...")

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def closeEvent(self, event) -> None:
        """防止使用者直接關閉對話框（需透過取消按鈕）。"""
        if not self._cancelled:
            event.ignore()
        else:
            super().closeEvent(event)
