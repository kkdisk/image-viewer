"""圖片編輯器的壓縮檔開啟流程。"""

import os
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from image_viewer.core.archive_manager import ArchiveManager
from image_viewer.core.workers import ArchiveExtractWorker


class ArchiveWorkflowMixin:
    """封裝 ImageEditorWindow 的非同步 7z 工作流程。"""

    def _setup_archive_workflow(self) -> None:
        self.archive_manager = ArchiveManager(
            max_files=self.config.MAX_ARCHIVE_FILES,
            max_single_file_size=self.config.MAX_ARCHIVE_SINGLE_FILE_SIZE,
            max_total_size=self.config.MAX_ARCHIVE_UNCOMPRESSED_SIZE,
        )
        self.archive_extract_thread: Optional[ArchiveExtractWorker] = None
        self._close_after_archive = False

    def _load_archive(self, archive_path: str) -> None:
        if self.archive_extract_thread and self.archive_extract_thread.isRunning():
            self.status_bar.showMessage("另一個壓縮檔仍在解壓縮中。", 3000)
            return
        self._start_archive_extraction(archive_path)

    def _start_archive_extraction(
        self,
        archive_path: str,
        password: Optional[str] = None,
    ) -> None:
        self.status_bar.showMessage(
            f"正在準備解壓縮 {os.path.basename(archive_path)}...", 0
        )
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.archive_extract_thread = ArchiveExtractWorker(
            self.archive_manager, archive_path, password, self
        )
        self.archive_extract_thread.extraction_completed.connect(
            self._on_archive_extracted
        )
        self.archive_extract_thread.start()

    @pyqtSlot(bool, str, str)
    def _on_archive_extracted(
        self, success: bool, result: str, archive_path: str
    ) -> None:
        QApplication.restoreOverrideCursor()
        if self.archive_extract_thread:
            self.archive_extract_thread.wait()
            self.archive_extract_thread.deleteLater()
            self.archive_extract_thread = None

        if self._close_after_archive:
            self.archive_manager.cleanup()
            self._close_after_archive = False
            self.close()
            return

        if not success and result in ("密碼錯誤", "需要密碼"):
            password, ok = QInputDialog.getText(
                self,
                "輸入密碼",
                f"檔案 {os.path.basename(archive_path)} 需要密碼:\n"
                + ("(密碼錯誤，請重試)" if result == "密碼錯誤" else ""),
                QLineEdit.EchoMode.Password,
            )
            if ok:
                self._start_archive_extraction(archive_path, password)
            else:
                self.status_bar.showMessage("已取消開啟壓縮檔", 3000)
            return
        if not success:
            QMessageBox.critical(self, "解壓縮失敗", result)
            return

        self._open_first_extracted_image(result)

    def _open_first_extracted_image(self, temp_path: str) -> None:
        self.status_bar.showMessage("解壓縮完成，正在尋找圖片...", 0)
        first_image_path = None
        for root, _, files in os.walk(temp_path):
            files.sort()
            for filename in files:
                if filename.lower().endswith(self.config.SUPPORTED_IMAGE_EXTENSIONS):
                    first_image_path = os.path.join(root, filename)
                    break
            if first_image_path:
                break

        if first_image_path:
            self.load_image(first_image_path)
            self.status_bar.showMessage(
                f"已從壓縮庫載入，可預覽 {os.path.basename(temp_path)}", 3000
            )
        else:
            QMessageBox.information(self, "提示", "壓縮檔內沒有找到支援的圖片格式。")
            self.archive_manager.cleanup()
            self.status_bar.clearMessage()
