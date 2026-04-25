"""結果顯示面板 — 以群組方式顯示重複圖片。"""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView,
)

from image_viewer.duplicate_checker.core.comparator import DuplicateGroup
from image_viewer.duplicate_checker.core.utils import format_size


class ResultsPanel(QWidget):
    """重複圖片結果顯示面板。

    Signals:
        image_selected: 使用者選擇某張圖片時發出，帶有檔案路徑。
        selection_changed: 勾選狀態改變時發出，帶有已勾選的路徑清單。
    """

    image_selected = pyqtSignal(str)
    selection_changed = pyqtSignal(list)

    THUMB_SIZE = 48

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._groups: list[DuplicateGroup] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        # 標題列
        header = QHBoxLayout()
        title = QLabel("📋 重複群組")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()

        self._count_label = QLabel("")
        self._count_label.setObjectName("subtitleLabel")
        header.addWidget(self._count_label)
        layout.addLayout(header)

        # 批次操作按鈕
        btn_bar = QHBoxLayout()
        self._select_all_dup_btn = QPushButton("☑ 選取所有重複")
        self._select_all_dup_btn.setToolTip("自動勾選每組中非最佳的圖片")
        self._select_all_dup_btn.clicked.connect(self._select_all_duplicates)
        btn_bar.addWidget(self._select_all_dup_btn)

        self._deselect_all_btn = QPushButton("☐ 取消全選")
        self._deselect_all_btn.clicked.connect(self._deselect_all)
        btn_bar.addWidget(self._deselect_all_btn)

        self._expand_btn = QPushButton("▼ 全部展開")
        self._expand_btn.clicked.connect(self._toggle_expand)
        btn_bar.addWidget(self._expand_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # 樹狀結果列表
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["檔案名稱", "大小", "尺寸", "路徑"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setIconSize(QSize(self.THUMB_SIZE, self.THUMB_SIZE))
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemChanged.connect(self._on_item_changed)

        header_view = self._tree.header()
        header_view.setStretchLastSection(True)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header_view.resizeSection(0, 250)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)

        layout.addWidget(self._tree)

        # 空狀態
        self._empty_label = QLabel("尚未掃描。請在左側設定資料夾後點擊「開始掃描」")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("subtitleLabel")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._expanded = False

    def set_results(self, groups: list[DuplicateGroup]) -> None:
        """設定並顯示掃描結果。"""
        self._groups = groups
        self._tree.blockSignals(True)
        self._tree.clear()
        self._get_thumbnail.cache_clear()  # 清除舊掃描的快取

        if not groups:
            self._tree.setVisible(False)
            self._empty_label.setVisible(True)
            self._empty_label.setText("✅ 未發現重複圖片！")
            self._count_label.setText("")
            self._tree.blockSignals(False)
            return

        self._tree.setVisible(True)
        self._empty_label.setVisible(False)

        total_saveable = 0
        for group in groups:
            total_saveable += group.saveable_size
            match_label = "🔴 精確相同" if group.match_type == "exact" else "🟡 視覺相似"
            group_item = QTreeWidgetItem([
                f"群組 {group.group_id + 1} — {match_label} ({group.file_count} 張)",
                format_size(group.total_size),
                "",
                "",
            ])
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)

            best = group.get_best_image()

            for img in group.images:
                is_best = best and img.filepath == best.filepath
                child = QTreeWidgetItem()
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setText(0, ("⭐ " if is_best else "") + img.filename)
                child.setText(1, format_size(img.file_size))
                w, h = img.dimensions
                child.setText(2, f"{w}×{h}")
                child.setText(3, str(img.filepath))
                child.setData(0, Qt.ItemDataRole.UserRole, str(img.filepath))
                child.setToolTip(0, "建議保留" if is_best else "可移除的重複檔案")

                # 載入縮圖
                thumb = self._get_thumbnail(str(img.filepath), self.THUMB_SIZE)
                if thumb:
                    child.setIcon(0, QIcon(thumb))

                group_item.addChild(child)

            self._tree.addTopLevelItem(group_item)

        self._count_label.setText(
            f"{len(groups)} 個群組 | 可節省 {format_size(total_saveable)}"
        )
        self._tree.expandAll()
        self._expanded = True
        self._tree.blockSignals(False)

    def get_checked_paths(self) -> list[Path]:
        """取得所有已勾選的檔案路徑。"""
        paths = []
        for i in range(self._tree.topLevelItemCount()):
            group_item = self._tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    path_str = child.data(0, Qt.ItemDataRole.UserRole)
                    if path_str:
                        paths.append(Path(path_str))
        return paths

    def remove_paths(self, paths: list[Path]) -> None:
        """從結果中移除指定路徑的項目（用於刪除/移動後更新）。"""
        path_strs = {str(p) for p in paths}
        for i in range(self._tree.topLevelItemCount() - 1, -1, -1):
            group_item = self._tree.topLevelItem(i)
            for j in range(group_item.childCount() - 1, -1, -1):
                child = group_item.child(j)
                path_str = child.data(0, Qt.ItemDataRole.UserRole)
                if path_str in path_strs:
                    group_item.removeChild(child)
            # 只剩 0-1 個子項目則移除整個群組
            if group_item.childCount() <= 1:
                self._tree.takeTopLevelItem(i)

    def _select_all_duplicates(self) -> None:
        """自動選取每組中非最佳的圖片。"""
        self._tree.blockSignals(True)
        for gi in range(len(self._groups)):
            if gi >= self._tree.topLevelItemCount():
                break
            group = self._groups[gi]
            group_item = self._tree.topLevelItem(gi)
            best = group.get_best_image()

            for j in range(group_item.childCount()):
                child = group_item.child(j)
                path_str = child.data(0, Qt.ItemDataRole.UserRole)
                if best and path_str == str(best.filepath):
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                else:
                    child.setCheckState(0, Qt.CheckState.Checked)
        self._tree.blockSignals(False)
        self.selection_changed.emit([str(p) for p in self.get_checked_paths()])

    def _deselect_all(self) -> None:
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            group_item = self._tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                group_item.child(j).setCheckState(0, Qt.CheckState.Unchecked)
        self._tree.blockSignals(False)
        self.selection_changed.emit([])

    def _toggle_expand(self) -> None:
        if self._expanded:
            self._tree.collapseAll()
            self._expand_btn.setText("▶ 全部展開")
        else:
            self._tree.expandAll()
            self._expand_btn.setText("▼ 全部收合")
        self._expanded = not self._expanded

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if path_str:
            self.image_selected.emit(path_str)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == 0:
            self.selection_changed.emit([str(p) for p in self.get_checked_paths()])

    @staticmethod
    @lru_cache(maxsize=500)
    def _get_thumbnail(filepath: str, size: int) -> QPixmap | None:
        """使用 PIL 高效產生縮圖並快取。"""
        try:
            with Image.open(filepath) as img:
                # 轉為 RGB 確保相容性
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                
                # thumbnail 會直接修改原圖，且極度節省記憶體
                img.thumbnail((size, size))
                
                # 轉換為 QPixmap
                with io.BytesIO() as buffer:
                    img.save(buffer, format="PNG")
                    pixmap = QPixmap()
                    pixmap.loadFromData(buffer.getvalue())
                    return pixmap
        except Exception:
            pass
        return None

