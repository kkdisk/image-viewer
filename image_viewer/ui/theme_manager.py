import os
import sys
import logging
from typing import Optional

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

class ThemeManager:
    # [v1.6] 大幅修改
    def __init__(self, app: QApplication): 
        self.app = app
        # 儲存原始的系統調色盤 (用於亮色主題)
        self.original_palette = app.style().standardPalette()
        # 內嵌備份 QSS
        self._fallback_dark_stylesheet = self._get_fallback_stylesheet()
        # 定義可用的主題
        self.themes = ["light", "dark"]
        # 初始化目前主題 (將在 apply_theme 中被設定)
        self.current_theme_name = self.themes[0] 

    def apply_theme(self, theme_name: str):
        """套用指定名稱的主題"""
        if theme_name not in self.themes:
            logging.warning(f"未知的主題: {theme_name}。退回至 'light'。")
            theme_name = "light"
            
        self.current_theme_name = theme_name
        
        if theme_name == "dark":
            # 套用深色調色盤
            self._apply_dark_palette()
            # 嘗試從檔案載入 QSS，如果失敗則使用備份
            stylesheet = self._load_stylesheet_from_file("dark_theme.qss")
            if stylesheet is None:
                logging.warning("dark_theme.qss 載入失敗，使用內嵌備份樣式。")
                stylesheet = self._fallback_dark_stylesheet
            self.app.setStyleSheet(stylesheet)
            
        elif theme_name == "light":
            # 恢復為原始系統調色盤
            self.app.setPalette(self.original_palette)
            # 清除自訂樣式表
            self.app.setStyleSheet("")
            
        logging.info(f"已切換主題至: {theme_name}")

    def toggle_theme(self):
        """循環切換到下一個可用的主題"""
        try:
            current_index = self.themes.index(self.current_theme_name)
        except ValueError:
            current_index = 0 # 如果當前主題不在列表中，從第一個開始
            
        # 計算下一個主題的索引
        next_index = (current_index + 1) % len(self.themes)
        next_theme = self.themes[next_index]
        
        # 套用下一個主題
        self.apply_theme(next_theme)

    def _apply_dark_palette(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(37, 37, 37))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        self.app.setPalette(dark_palette)

    def _load_stylesheet_from_file(self, file_path: str) -> Optional[str]:
        """嘗試從檔案讀取 QSS 字串"""
        try:
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            # 注意：這裡的路徑調整要小心，因為我們在 image_viewer/ui/theme_manager.py
            # 原始檔案是在根目錄，setStyleSheet 需要絕對路徑或者相對於執行檔的路徑
            # 我們假設 dark_theme.qss 在根目錄 (d:\Code\AI_generate_Code\image-viewer\dark_theme.qss)
            
            # 使用 os.getcwd() 可能不準確，最好是相對於入口點
            # 但這裡我們先嘗試獲取專案根目錄
            # 假設專案根目錄是本檔案的上兩層 (image_viewer/ui/.. -> image_viewer/.. -> root)
            
            project_root = base_path
            full_path = os.path.join(project_root, file_path)

            if not os.path.exists(full_path):
                 # Fallback: 嘗試直接使用 file_path (假設在 CWD)
                 full_path = file_path

            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logging.warning(f"樣式表檔案未找到: {file_path}")
            return None
        except Exception as e:
            logging.error(f"讀取樣式表時發生錯誤: {e}", exc_info=True)
            return None

    def _get_fallback_stylesheet(self) -> str:
        """返回內嵌的備份 QSS 樣式表"""
        return """
        /* === General === */
        QWidget {
            color: #dcdcdc;
            font-family: 'Segoe UI', 'Microsoft JhengHei', 'Helvetica', sans-serif;
        }
        QMainWindow, QDialog {
            background-color: #252525;
        }
        /* ... (省略 QSS 內容，與 dark_theme.qss 相同) ... */
        QScrollArea#scrollArea { border: none; background-color: #1e1e1e; }
        QLabel#imageLabel { background-color: #1e1e1e; }
        QDockWidget::title { background-color: #333333; padding: 8px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }
        QDockWidget > QWidget { border: 1px solid #3c3c3c; border-top: none; }
        QTreeWidget, QListWidget { background-color: #2c2c2c; border: 1px solid #3c3c3c; padding: 5px; border-radius: 4px; }
        QListWidget::item { border-radius: 4px; padding: 4px; }
        QListWidget::item:hover { background-color: #383838; }
        QListWidget::item:selected { background-color: rgba(0, 120, 215, 0.5); border: 1px solid #0078d7; color: #ffffff; }
        QHeaderView::section { background-color: #383838; padding: 6px; border: none; border-bottom: 1px solid #454545; }
        QPushButton { background-color: #3e3e3e; border: 1px solid #555555; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
        QPushButton:hover { background-color: #4a4a4a; border-color: #6a6a6a; }
        QPushButton:pressed { background-color: #333333; }
        QPushButton:disabled { background-color: #303030; color: #777777; border-color: #444444; }
        QSlider::groove:horizontal { height: 4px; background: #444444; margin: 2px 0; border-radius: 2px; }
        QSlider::handle:horizontal { background: #0078d7; border: 1px solid #0078d7; width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; }
        QGroupBox { border: 1px solid #3c3c3c; border-radius: 6px; margin-top: 1ex; font-weight: bold; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
        QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #333333; padding: 6px; border: 1px solid #444444; border-radius: 4px; }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #0078d7; }
        QToolBar { background-color: #2d2d2d; border: none; padding: 4px; spacing: 6px; }
        QStatusBar { background-color: #2d2d2d; border-top: 1px solid #3c3c3c; }
        QStatusBar QProgressBar { background-color: #3e3e3e; border: 1px solid #555; border-radius: 4px; text-align: center; color: #dcdcdc; }
        QStatusBar QProgressBar::chunk { background-color: #0078d7; border-radius: 4px; }
        QMenuBar { background-color: #2d2d2d; }
        QMenuBar::item:selected { background-color: #3e3e3e; }
        QMenu { background-color: #2c2c2c; border: 1px solid #444444; padding: 4px; }
        QMenu::item:selected { background-color: #0078d7; }
        QScrollBar:vertical { border: none; background: #2c2c2c; width: 12px; margin: 0px 0px 0px 0px; }
        QScrollBar:horizontal { border: none; background: #2c2c2c; height: 12px; margin: 0px 0px 0px 0px; }
        QScrollBar::handle:vertical { background: #555555; min-height: 25px; border-radius: 6px; }
        QScrollBar::handle:horizontal { background: #555555; min-width: 25px; border-radius: 6px; }
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #6a6a6a; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
        QToolTip { background-color: #1e1e1e; color: #dcdcdc; border: 1px solid #3c3c3c; padding: 5px; border-radius: 4px; }
        """
