# ==============================================================================
# main.py - 應用程式入口點
# ==============================================================================
"""
圖片瀏覽器應用程式的主入口點
"""

import sys
import os

# 修正 PyInstaller 相對 import 問題
# 當直接執行時，需要將父目錄加入 sys.path
if __name__ == '__main__' and __package__ is None:
    # 獲取此檔案的目錄
    file_dir = os.path.dirname(os.path.abspath(__file__))
    # 獲取父目錄 (image_viewer 的父目錄)
    parent_dir = os.path.dirname(file_dir)
    # 加入 sys.path
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    # 設定 package 名稱
    __package__ = 'image_viewer'

from PyQt6.QtWidgets import QApplication, QMessageBox

from image_viewer.config import Config
from image_viewer.main_window import ImageEditorWindow


def main() -> None:
    """主函式，用於啟動應用程式。"""

    app = QApplication(sys.argv)

    # 獲取資源的基礎路徑
    # 這段邏輯適用於 .py 執行和 PyInstaller --onefile 執行
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包後的路徑
        base_path = sys._MEIPASS
    else:
        # 開發時的路徑
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    config_path = os.path.join(base_path, 'config.json')

    config = Config()
    config.load_from_json(config_path)
    config.apply_heic_support()

    try:
        config.validate()
    except AssertionError as e:
        import logging
        logging.critical(f"設定檔驗證失敗: {e}")
        QMessageBox.critical(None, "設定錯誤", f"應用程式設定錯誤，無法啟動:\n{e}")
        sys.exit(1)

    window = ImageEditorWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
