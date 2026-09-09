import tempfile
import logging
from pathlib import PurePosixPath
from typing import Optional, Tuple
import py7zr

class ArchiveManager:
    """管理壓縮檔的解壓縮與暫存資料夾生命週期。"""

    def __init__(
        self,
        max_files: int = 10000,
        max_single_file_size: int = 524288000,
        max_total_size: int = 2147483648,
    ):
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._current_archive_path: Optional[str] = None
        self._max_files = max_files
        self._max_single_file_size = max_single_file_size
        self._max_total_size = max_total_size

    def _validate_archive_entries(self, archive: py7zr.SevenZipFile) -> None:
        """在寫入磁碟前驗證路徑與解壓後大小。"""
        entries = archive.list()
        if len(entries) > self._max_files:
            raise ValueError(f"壓縮檔包含過多項目 ({len(entries)} > {self._max_files})")

        total_size = 0
        for entry in entries:
            if getattr(entry, 'is_symlink', False):
                raise ValueError(f"壓縮檔包含不允許的符號連結: {entry.filename}")
            normalized_name = entry.filename.replace('\\', '/')
            member_path = PurePosixPath(normalized_name)
            if (
                member_path.is_absolute()
                or '..' in member_path.parts
                or (member_path.parts and ':' in member_path.parts[0])
            ):
                raise ValueError(f"壓縮檔包含不安全路徑: {entry.filename}")

            size = int(entry.uncompressed or 0)
            if size > self._max_single_file_size:
                raise ValueError(f"壓縮檔中的檔案過大: {entry.filename}")
            total_size += size
            if total_size > self._max_total_size:
                raise ValueError("壓縮檔解壓後總大小超過安全限制")

    def extract_7z(self, archive_path: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """
        將 7z 檔案解壓縮到新的暫存資料夾。

        Args:
            archive_path: 7z 檔案路徑
            password: 解壓縮密碼 (如果有的話)

        Returns:
            Tuple[bool, str]: (是否成功, 錯誤訊息或暫存資料夾路徑)
        """
        try:
            # 清理先前的暫存目錄
            self.cleanup()

            # 建立新的暫存目錄
            self._temp_dir = tempfile.TemporaryDirectory(prefix="image_viewer_")
            temp_path = self._temp_dir.name

            logging.info(f"開始解壓縮 {archive_path} 到 {temp_path}")

            with py7zr.SevenZipFile(archive_path, mode='r', password=password) as z:
                # 若需要密碼但未提供，或者密碼錯誤，py7zr 會拋出 exception
                # py7zr.exceptions.BadPassword
                self._validate_archive_entries(z)
                z.extractall(path=temp_path)

            self._current_archive_path = archive_path
            return True, temp_path

        except py7zr.exceptions.PasswordRequired:
            self.cleanup()
            # If a password was provided and we still get PasswordRequired or an error, it's a bad password
            if password is not None:
                return False, "密碼錯誤"
            return False, "需要密碼"
        except Exception as e:
            self.cleanup()
            logging.error(f"解壓縮 {archive_path} 失敗: {e}")
            return False, f"解壓縮失敗: {str(e)}"

    def cleanup(self):
        """清理目前的暫存資料夾。"""
        if self._temp_dir:
            try:
                logging.info(f"正在清理暫存資料夾: {self._temp_dir.name}")
                self._temp_dir.cleanup()
            except Exception as e:
                logging.warning(f"清理暫存資料夾失敗: {e}")
            finally:
                self._temp_dir = None
                self._current_archive_path = None

    def get_current_archive_path(self) -> Optional[str]:
        return self._current_archive_path

    def is_archive_open(self) -> bool:
        return self._temp_dir is not None

    def __del__(self):
        self.cleanup()
