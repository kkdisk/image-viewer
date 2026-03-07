# ==============================================================================
# image_viewer/__init__.py - 套件初始化
# ==============================================================================
"""
增強型圖片瀏覽器 v2.0.1

這是一個使用 PyQt6 和 Pillow 打造的高效能圖片瀏覽與編輯工具。
"""

__version__ = "2.0.1"
__author__ = "omero"

from .config import Config, HEIC_SUPPORTED, NATSORT_ENABLED
from .core.editor_window import ImageEditorWindow
from .main import main

__all__ = [
    "__version__",
    "__author__",
    "Config",
    "ImageEditorWindow", 
    "main",
    "HEIC_SUPPORTED",
    "NATSORT_ENABLED",
]
