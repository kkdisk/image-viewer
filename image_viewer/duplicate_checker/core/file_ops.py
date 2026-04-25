"""檔案操作模組 — 刪除（移至回收桶）與移動檔案。"""

import shutil
import subprocess
import sys
from pathlib import Path

from send2trash import send2trash


class FileOperator:
    """安全的檔案操作工具。"""

    def __init__(self) -> None:
        self._operation_log: list[dict] = []

    @property
    def operation_log(self) -> list[dict]:
        return list(self._operation_log)

    def delete_to_trash(self, filepath: Path) -> bool:
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"檔案不存在: {filepath}")
        send2trash(str(filepath))
        self._operation_log.append({"action": "delete", "source": str(filepath), "success": True})
        return True

    def move_file(self, filepath: Path, destination_dir: Path) -> Path:
        filepath, destination_dir = Path(filepath), Path(destination_dir)
        if not filepath.exists():
            raise FileNotFoundError(f"檔案不存在: {filepath}")
        if not destination_dir.exists():
            destination_dir.mkdir(parents=True, exist_ok=True)
        if not destination_dir.is_dir():
            raise NotADirectoryError(f"目標路徑不是資料夾: {destination_dir}")
        dest_path = self._get_unique_path(destination_dir / filepath.name)
        shutil.move(str(filepath), str(dest_path))
        self._operation_log.append({"action": "move", "source": str(filepath), "destination": str(dest_path), "success": True})
        return dest_path

    def batch_delete(self, filepaths: list[Path]) -> dict:
        results = {"success_count": 0, "fail_count": 0, "errors": []}
        for fp in filepaths:
            try:
                self.delete_to_trash(fp)
                results["success_count"] += 1
            except Exception as e:
                results["fail_count"] += 1
                results["errors"].append({"file": str(fp), "error": str(e)})
        return results

    def batch_move(self, filepaths: list[Path], destination_dir: Path) -> dict:
        results = {"success_count": 0, "fail_count": 0, "errors": []}
        for fp in filepaths:
            try:
                self.move_file(fp, destination_dir)
                results["success_count"] += 1
            except Exception as e:
                results["fail_count"] += 1
                results["errors"].append({"file": str(fp), "error": str(e)})
        return results

    @staticmethod
    def _get_unique_path(filepath: Path) -> Path:
        if not filepath.exists():
            return filepath
        stem, suffix, parent, counter = filepath.stem, filepath.suffix, filepath.parent, 1
        while True:
            new_path = parent / f"{stem} ({counter}){suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    @staticmethod
    def open_in_explorer(filepath: Path) -> None:
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"檔案不存在: {filepath}")
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(filepath)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath.parent)])
