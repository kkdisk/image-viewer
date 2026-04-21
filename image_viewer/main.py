import sys
import os
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from image_viewer.config import Config
from image_viewer.core.editor_window import ImageEditorWindow


def _resolve_project_root() -> str:
    """Resolve project root for both source run and PyInstaller onefile run."""
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_log_file_path() -> Path:
    """
    Resolve a writable log path in user data directory.
    Falls back to current working directory if necessary.
    """
    if os.name == "nt":
        app_data = os.getenv("APPDATA")
        if app_data:
            return (
                Path(app_data)
                / "ImageViewer"
                / "logs"
                / "image_viewer.log"
            )
    return Path.home() / ".image_viewer" / "logs" / "image_viewer.log"


def _setup_logging() -> None:
    log_file_path = _resolve_log_file_path()
    try:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    except Exception:
        # Keep app startup resilient even if user profile path is unavailable.
        file_handler = logging.FileHandler(
            "image_viewer.log",
            encoding="utf-8",
        )

    log_format = (
        "%(asctime)s - %(levelname)s - "
        "[%(filename)s:%(lineno)d - %(funcName)s] - %(message)s"
    )
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[file_handler, logging.StreamHandler()],
        force=True,
    )


def main() -> None:
    """主函式，用於啟動應用程式。"""
    _setup_logging()

    app = QApplication(sys.argv)

    # [v1.7 Build 修正] 獲取資源的基礎路徑
    # 這段邏輯適用於 .py 執行和 PyInstaller --onefile 執行
    project_root = _resolve_project_root()

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
