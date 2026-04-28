import tempfile
import logging
from typing import Optional, Tuple
import py7zr

class ArchiveManager:
    """管理壓縮檔的解壓縮與暫存資料夾生命週期。"""
    
    def __init__(self):
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._current_archive_path: Optional[str] = None

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
