"""掃描背景工作執行緒。"""

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from image_viewer.duplicate_checker.core.scanner import ImageScanner
from image_viewer.duplicate_checker.core.comparator import ImageComparator, DuplicateGroup, CompareMode
from image_viewer.duplicate_checker.core.hasher import ImageHasher, HashAlgorithm


class ScanWorker(QThread):
    """在背景執行緒中執行圖片掃描與重複偵測。

    Signals:
        progress_updated: (current, total, message) 掃描進度更新。
        scan_completed: (groups, errors) 掃描完成。
        scan_error: (error_message) 掃描發生致命錯誤。
    """

    progress_updated = pyqtSignal(int, int, str)
    scan_completed = pyqtSignal(list, list)
    scan_error = pyqtSignal(str)

    def __init__(
        self,
        directories: list[str],
        recursive: bool = True,
        mode: CompareMode = "both",
        algorithm: HashAlgorithm = "phash",
        threshold: int = 5,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._directories = directories
        self._recursive = recursive
        self._mode = mode
        self._algorithm = algorithm
        self._threshold = threshold
        self._cancelled = False

    def cancel(self) -> None:
        """請求取消掃描。"""
        self._cancelled = True

    def run(self) -> None:
        """執行掃描（在背景執行緒中）。"""
        try:
            # 階段 1：掃描檔案
            self.progress_updated.emit(0, 0, "正在掃描資料夾...")
            scanner = ImageScanner(
                directories=self._directories,
                recursive=self._recursive,
            )
            filepaths = scanner.scan()

            if self._cancelled:
                return

            total = len(filepaths)
            if total == 0:
                self.scan_completed.emit([], [])
                return

            self.progress_updated.emit(0, total, f"找到 {total} 張圖片，正在計算雜湊值...")

            # 階段 2：計算雜湊並比對
            hasher = ImageHasher(algorithm=self._algorithm)
            comparator = ImageComparator(
                mode=self._mode,
                threshold=self._threshold,
                hasher=hasher,
            )

            def on_progress(current: int, total: int) -> None:
                if self._cancelled:
                    raise InterruptedError("掃描已取消")
                self.progress_updated.emit(
                    current, total,
                    f"正在處理: {current}/{total}",
                )

            comparator.process_files(filepaths, progress_callback=on_progress)

            if self._cancelled:
                return

            # 階段 3：尋找重複群組
            self.progress_updated.emit(total, total, "正在分析重複群組...")
            groups = comparator.find_duplicates()
            errors = comparator.errors

            self.scan_completed.emit(groups, errors)

        except InterruptedError:
            pass  # 使用者取消
        except Exception as e:
            self.scan_error.emit(str(e))
