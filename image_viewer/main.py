import sys
import os
import logging
from PyQt6.QtWidgets import QApplication, QMessageBox
from image_viewer.config import Config
from image_viewer.core.editor_window import ImageEditorWindow

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s] - %(message)s",
    handlers=[
        logging.FileHandler('image_viewer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def main() -> None:
    """主函式，用於啟動應用程式。"""

    app = QApplication(sys.argv)

    # [v1.7 Build 修正] 獲取資源的基礎路徑
    # 這段邏輯適用於 .py 執行和 PyInstaller --onefile 執行
    # (getattr 會安全地檢查 'sys' 是否有 '_MEIPASS' 屬性)
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 注意: 我們現在在 image_viewer/main.py，所以 config.json 應該在上一層
    # 但如果是在開發環境，它可能在更外層。
    # 假設這是一個 package，通常 config 不會放在 package 內部，而是外部
    # 這裡我們假設 config.json 和入口腳本 (run.py) 在同一層
    
    # 調整路徑邏輯：
    # 如果是 PyInstaller，_MEIPASS 是解壓的暫存目錄
    # 如果是開發環境，os.path.abspath(__file__) 是 .../image_viewer/image_viewer/main.py
    # 我們需要回到專案根目錄 .../image_viewer/
    
    if hasattr(sys, '_MEIPASS'):
        project_root = sys._MEIPASS
    else:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    config_path = os.path.join(project_root, 'config.json')

    # Fallback: 如果找不到，嘗試当前目錄
    if not os.path.exists(config_path):
        config_path = 'config.json'

    config = Config()
    config.load_from_json(config_path) 
    config.apply_heic_support()

    try:
        config.validate()
    except AssertionError as e:
        logging.critical(f"設定檔驗證失敗: {e}")
        QMessageBox.critical(None, "設定錯誤", f"應用程式設定錯誤，無法啟動:\n{e}")
        sys.exit(1)

    window = ImageEditorWindow(config)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
