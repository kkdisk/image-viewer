"""主視窗 — 整合所有面板與工作流程。"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStatusBar, QMessageBox, QFileDialog, QMenuBar,
    QMenu,
)

from image_viewer.duplicate_checker.core.comparator import DuplicateGroup
from image_viewer.duplicate_checker.core.file_ops import FileOperator
from image_viewer.duplicate_checker.core.reporter import ReportExporter
from image_viewer.duplicate_checker.core.utils import format_size
from image_viewer.duplicate_checker.ui.scan_panel import ScanPanel
from image_viewer.duplicate_checker.ui.results_panel import ResultsPanel
from image_viewer.duplicate_checker.ui.preview_panel import PreviewPanel
from image_viewer.duplicate_checker.ui.progress_dialog import ProgressDialog
from image_viewer.duplicate_checker.workers.scan_worker import ScanWorker


class MainWindow(QMainWindow):
    """應用程式主視窗。"""

    def __init__(self) -> None:
        super().__init__()
        self._worker: ScanWorker | None = None
        self._progress_dialog: ProgressDialog | None = None
        self._groups: list[DuplicateGroup] = []
        self._file_operator = FileOperator()
        self._setup_ui()
        self._apply_styles()
        self._setup_menu()

    def _setup_ui(self) -> None:
        self.setWindowTitle("🔍 重複圖片檢查工具")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 850)

        # 中央元件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # 三欄式分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側：掃描設定
        self._scan_panel = ScanPanel()
        self._scan_panel.scan_requested.connect(self._start_scan)
        self._scan_panel.setMinimumWidth(260)
        self._scan_panel.setMaximumWidth(350)
        splitter.addWidget(self._scan_panel)

        # 中間：結果列表
        self._results_panel = ResultsPanel()
        self._results_panel.image_selected.connect(self._on_image_selected)
        self._results_panel.selection_changed.connect(self._on_selection_changed)
        splitter.addWidget(self._results_panel)

        # 右側：圖片預覽
        self._preview_panel = PreviewPanel()
        self._preview_panel.setMinimumWidth(280)
        splitter.addWidget(self._preview_panel)

        # 設定分割比例
        splitter.setSizes([280, 520, 380])
        main_layout.addWidget(splitter)

        # 底部操作列
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(8, 4, 8, 4)

        self._delete_btn = QPushButton("🗑️ 刪除選取 (移至回收桶)")
        self._delete_btn.setObjectName("dangerBtn")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_selected)
        action_bar.addWidget(self._delete_btn)

        self._move_btn = QPushButton("📦 移動選取至資料夾")
        self._move_btn.setEnabled(False)
        self._move_btn.clicked.connect(self._move_selected)
        action_bar.addWidget(self._move_btn)

        action_bar.addStretch()

        self._selected_label = QPushButton("")
        self._selected_label.setFlat(True)
        self._selected_label.setEnabled(False)
        self._selected_label.setStyleSheet("color: #aaa; border: none;")
        action_bar.addWidget(self._selected_label)

        main_layout.addLayout(action_bar)

        # 狀態列
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("就緒。請選擇資料夾並開始掃描。")

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            #titleLabel {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
                margin-bottom: 5px;
            }
            #subtitleLabel {
                font-size: 13px;
                color: #aaa;
            }
            #statsLabel {
                font-size: 12px;
                color: #888;
            }
            
            /* GroupBox 樣式 */
            QGroupBox {
                border: 1px solid #333;
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 10px;
                font-weight: bold;
                color: #ddd;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px;
            }
            
            /* 按鈕進階樣式 */
            QPushButton#primaryBtn {
                background-color: #0078d7;
                color: white;
                border: none;
                font-size: 15px;
                border-radius: 6px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #0086f0;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #005a9e;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #333;
                color: #777;
            }

            QPushButton#dangerBtn {
                background-color: #c42b1c;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton#dangerBtn:hover {
                background-color: #d83b2a;
            }
            QPushButton#dangerBtn:pressed {
                background-color: #a22217;
            }
            QPushButton#dangerBtn:disabled {
                background-color: #222;
                color: #555;
            }

            QPushButton#secondaryBtn {
                background-color: #333;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #3d3d3d;
                border-color: #555;
            }

            /* 分隔器樣式 */
            QSplitter::handle {
                background-color: #2c2c2c;
                margin: 2px;
            }

            /* 樹狀列表美化 */
            QTreeWidget {
                border: 1px solid #333;
                border-radius: 8px;
                background-color: #1e1e1e;
                outline: none;
            }
            QTreeWidget::item {
                padding: 12px;
                border-bottom: 1px solid #282828;
                height: 40px;
            }
            QTreeWidget::item:selected {
                background-color: #3d3d3d;
                color: #ffffff;
                border-radius: 4px;
            }
            
            /* 群組項目樣式 */
            QTreeWidget::item:has-children {
                background-color: #2a2a2a;
                font-weight: bold;
                color: #eee;
            }

            /* 捲動軸美化 */
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #555;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                height: 0px;
            }

            /* 狀態列 */
            QStatusBar {
                background-color: #1a1a1a;
                color: #888;
                border-top: 1px solid #222;
            }
        """)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # 檔案選單
        file_menu = menubar.addMenu("檔案")
        export_csv = file_menu.addAction("📊 匯出 CSV 報告")
        export_csv.triggered.connect(lambda: self._export_report("csv"))
        export_html = file_menu.addAction("🌐 匯出 HTML 報告")
        export_html.triggered.connect(lambda: self._export_report("html"))
        file_menu.addSeparator()
        quit_action = file_menu.addAction("結束")
        quit_action.triggered.connect(self.close)

        # 說明選單
        help_menu = menubar.addMenu("說明")
        about = help_menu.addAction("關於")
        about.triggered.connect(self._show_about)

    # === 掃描流程 ===

    def _start_scan(self, params: dict) -> None:
        """啟動掃描。"""
        self._scan_panel.set_scanning(True)
        self._preview_panel.clear()
        self._groups = []

        # 建立進度對話框
        self._progress_dialog = ProgressDialog(self)

        # 建立工作執行緒
        self._worker = ScanWorker(
            directories=params["directories"],
            recursive=params["recursive"],
            mode=params["mode"],
            algorithm=params["algorithm"],
            threshold=params["threshold"],
        )
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.scan_completed.connect(self._on_scan_completed)
        self._worker.scan_error.connect(self._on_scan_error)

        # 取消按鈕連接
        self._progress_dialog._cancel_btn.clicked.connect(self._cancel_scan)

        self._worker.start()
        self._progress_dialog.exec()

    def _cancel_scan(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._scan_panel.set_scanning(False)
        self._statusbar.showMessage("掃描已取消。")
        if self._progress_dialog:
            self._progress_dialog.accept()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        if self._progress_dialog:
            self._progress_dialog.update_progress(current, total, message)

    def _on_scan_completed(self, groups: list, errors: list) -> None:
        self._groups = groups
        self._scan_panel.set_scanning(False)

        if self._progress_dialog:
            self._progress_dialog.accept()

        self._results_panel.set_results(groups)

        # 統計資訊
        total_files = sum(g.file_count for g in groups)
        total_saveable = sum(g.saveable_size for g in groups)
        saveable_str = format_size(total_saveable)

        stats_msg = f"找到 {len(groups)} 個重複群組，共 {total_files} 張圖片"
        if total_saveable > 0:
            stats_msg += f"，可節省 {saveable_str}"
        if errors:
            stats_msg += f" | {len(errors)} 個檔案處理失敗"

        self._statusbar.showMessage(stats_msg)
        self._scan_panel.update_stats(stats_msg)

    def _on_scan_error(self, error_msg: str) -> None:
        self._scan_panel.set_scanning(False)
        if self._progress_dialog:
            self._progress_dialog.accept()
        QMessageBox.critical(self, "掃描錯誤", f"掃描過程中發生錯誤:\n\n{error_msg}")
        self._statusbar.showMessage("掃描失敗。")

    # === 圖片操作 ===

    def _on_image_selected(self, filepath: str) -> None:
        self._preview_panel.show_image(filepath)

    def _on_selection_changed(self, paths: list) -> None:
        count = len(paths)
        self._delete_btn.setEnabled(count > 0)
        self._move_btn.setEnabled(count > 0)
        if count > 0:
            self._selected_label.setText(f"已選取 {count} 個檔案")
        else:
            self._selected_label.setText("")

    def _delete_selected(self) -> None:
        paths = self._results_panel.get_checked_paths()
        if not paths:
            return

        reply = QMessageBox.question(
            self, "確認刪除",
            f"確定要將 {len(paths)} 個檔案移至資源回收桶嗎？\n\n"
            "此操作可從回收桶中還原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        results = self._file_operator.batch_delete(paths)
        self._results_panel.remove_paths(paths)
        self._preview_panel.clear()

        msg = f"成功刪除 {results['success_count']} 個檔案"
        if results["fail_count"] > 0:
            msg += f"，{results['fail_count']} 個失敗"
        self._statusbar.showMessage(msg)
        QMessageBox.information(self, "操作完成", msg)

    def _move_selected(self) -> None:
        paths = self._results_panel.get_checked_paths()
        if not paths:
            return

        dest_dir = QFileDialog.getExistingDirectory(self, "選擇目標資料夾")
        if not dest_dir:
            return

        results = self._file_operator.batch_move(paths, Path(dest_dir))
        self._results_panel.remove_paths(paths)
        self._preview_panel.clear()

        msg = f"成功移動 {results['success_count']} 個檔案至 {dest_dir}"
        if results["fail_count"] > 0:
            msg += f"，{results['fail_count']} 個失敗"
        self._statusbar.showMessage(msg)
        QMessageBox.information(self, "操作完成", msg)

    # === 匯出報告 ===

    def _export_report(self, format_type: str) -> None:
        if not self._groups:
            QMessageBox.information(self, "無資料", "請先執行掃描再匯出報告。")
            return

        if format_type == "csv":
            filepath, _ = QFileDialog.getSaveFileName(
                self, "匯出 CSV 報告", "duplicate_report.csv",
                "CSV 檔案 (*.csv)",
            )
        else:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "匯出 HTML 報告", "duplicate_report.html",
                "HTML 檔案 (*.html)",
            )

        if not filepath:
            return

        try:
            if format_type == "csv":
                ReportExporter.export_csv(self._groups, Path(filepath))
            else:
                ReportExporter.export_html(self._groups, Path(filepath))
            self._statusbar.showMessage(f"報告已匯出至: {filepath}")
            QMessageBox.information(self, "匯出成功", f"報告已儲存至:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "匯出失敗", f"匯出報告時發生錯誤:\n{e}")

    # === 其他 ===

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "關於",
            "<h2>🔍 重複圖片檢查工具</h2>"
            "<p>版本 2.1.0</p>"
            "<p>使用感知雜湊技術偵測重複與相似圖片。</p>"
            "<p>支援精確比對（MD5）與視覺相似比對（pHash）。</p>"
            "<hr>"
            "<p>技術: PyQt6 + imagehash + Pillow</p>",
        )

