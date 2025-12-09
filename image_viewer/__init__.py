# ==============================================================================
# image_viewer/__init__.py - 套件初始化
# ==============================================================================
"""
增強型圖片瀏覽器

這是一個使用 PyQt6 和 Pillow 打造的高效能圖片瀏覽與編輯工具。
"""

# 版本號從 config.py 引用 (Single Source of Truth)
from .config import __version__, APP_NAME, APP_TITLE
from .config import Config, HEIC_SUPPORTED, NATSORT_ENABLED
from .main_window import ImageEditorWindow
from .main import main

__all__ = [
    "__version__",
    "APP_NAME",
    "APP_TITLE",
    "Config",
    "ImageEditorWindow", 
    "main",
    "HEIC_SUPPORTED",
    "NATSORT_ENABLED",
]
