"""掃描設定面板 — 選擇資料夾、設定參數、啟動掃描。"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QComboBox, QSpinBox, QCheckBox, QListWidget,
    QListWidgetItem, QFileDialog,
)


class ScanPanel(QWidget):
    """掃描設定面板。

    Signals:
        scan_requested: 使用者點擊「開始掃描」時發出，帶有掃描參數字典。
    """

    scan_requested = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 標題
        title = QLabel("🔍 掃描設定")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        # === 資料夾選擇 ===
        folder_group = QGroupBox("📁 掃描資料夾")
        folder_layout = QVBoxLayout(folder_group)

        self._folder_list = QListWidget()
        self._folder_list.setMaximumHeight(180)
        self._folder_list.setToolTip("已選擇的掃描資料夾")
        self._folder_list.setStyleSheet("border-radius: 6px; padding: 4px;")
        folder_layout.addWidget(self._folder_list)

        btn_layout = QHBoxLayout()
        self._add_folder_btn = QPushButton("＋ 新增資料夾")
        self._add_folder_btn.setObjectName("secondaryBtn")
        self._add_folder_btn.clicked.connect(self._add_folder)
        self._remove_folder_btn = QPushButton("－ 移除選取")
        self._remove_folder_btn.setObjectName("secondaryBtn")
        self._remove_folder_btn.clicked.connect(self._remove_folder)
        btn_layout.addWidget(self._add_folder_btn)
        btn_layout.addWidget(self._remove_folder_btn)
        folder_layout.addLayout(btn_layout)

        layout.addWidget(folder_group)

        # === 掃描參數 ===
        param_group = QGroupBox("⚙️ 掃描參數")
        param_layout = QVBoxLayout(param_group)

        # 遞迴掃描
        self._recursive_cb = QCheckBox("遞迴掃描子資料夾")
        self._recursive_cb.setChecked(True)
        param_layout.addWidget(self._recursive_cb)

        # 比對模式
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("比對模式:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["精確 + 相似", "僅精確比對", "僅相似比對"])
        self._mode_combo.setToolTip(
            "精確比對：MD5 雜湊完全相同\n相似比對：感知雜湊相近"
        )
        mode_layout.addWidget(self._mode_combo)
        param_layout.addLayout(mode_layout)

        # 雜湊演算法
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("雜湊演算法:"))
        self._algo_combo = QComboBox()
        self._algo_combo.addItems(["phash", "dhash", "average_hash", "whash"])
        self._algo_combo.setToolTip(
            "phash：感知雜湊（推薦）\n"
            "dhash：差異雜湊（快速）\n"
            "average_hash：平均雜湊\n"
            "whash：小波雜湊"
        )
        algo_layout.addWidget(self._algo_combo)
        param_layout.addLayout(algo_layout)

        # 相似度門檻
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("相似門檻:"))
        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(0, 30)
        self._threshold_spin.setValue(5)
        self._threshold_spin.setToolTip(
            "Hamming distance 門檻值\n"
            "0 = 完全相同, 5 = 建議值, 10+ = 寬鬆"
        )
        thresh_layout.addWidget(self._threshold_spin)
        param_layout.addLayout(thresh_layout)

        layout.addWidget(param_group)

        # === 掃描按鈕 ===
        self._scan_btn = QPushButton("🚀 開始掃描")
        self._scan_btn.setObjectName("primaryBtn")
        self._scan_btn.setMinimumHeight(42)
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        layout.addWidget(self._scan_btn)

        layout.addStretch()

        # === 統計資訊 ===
        self._stats_label = QLabel("")
        self._stats_label.setObjectName("statsLabel")
        layout.addWidget(self._stats_label)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇掃描資料夾")
        if folder:
            # 避免重複
            for i in range(self._folder_list.count()):
                if self._folder_list.item(i).text() == folder:
                    return
            self._folder_list.addItem(QListWidgetItem(folder))

    def _remove_folder(self) -> None:
        current = self._folder_list.currentRow()
        if current >= 0:
            self._folder_list.takeItem(current)

    def _on_scan_clicked(self) -> None:
        directories = []
        for i in range(self._folder_list.count()):
            directories.append(self._folder_list.item(i).text())

        if not directories:
            return

        mode_map = {"精確 + 相似": "both", "僅精確比對": "exact", "僅相似比對": "similar"}
        mode_text = self._mode_combo.currentText()

        params = {
            "directories": directories,
            "recursive": self._recursive_cb.isChecked(),
            "mode": mode_map.get(mode_text, "both"),
            "algorithm": self._algo_combo.currentText(),
            "threshold": self._threshold_spin.value(),
        }
        self.scan_requested.emit(params)

    def set_scanning(self, is_scanning: bool) -> None:
        """設定掃描狀態（禁用/啟用控制項）。"""
        self._scan_btn.setEnabled(not is_scanning)
        self._add_folder_btn.setEnabled(not is_scanning)
        self._remove_folder_btn.setEnabled(not is_scanning)
        self._mode_combo.setEnabled(not is_scanning)
        self._algo_combo.setEnabled(not is_scanning)
        self._threshold_spin.setEnabled(not is_scanning)
        self._recursive_cb.setEnabled(not is_scanning)
        if is_scanning:
            self._scan_btn.setText("⏳ 掃描中...")
        else:
            self._scan_btn.setText("🚀 開始掃描")

    def update_stats(self, text: str) -> None:
        self._stats_label.setText(text)
