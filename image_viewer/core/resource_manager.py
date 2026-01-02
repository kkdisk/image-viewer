import logging
from typing import Dict, Optional
from PyQt6.QtGui import QIcon

class ResourceManager:
    """統一管理應用程式資源，如縮圖快取。"""
    def __init__(self):
        self._thumbnail_cache: Dict[str, QIcon] = {}
        logging.info("ResourceManager 初始化完畢。")

    def get_thumbnail(self, path: str) -> Optional[QIcon]:
        return self._thumbnail_cache.get(path)

    def add_thumbnail(self, path: str, icon: QIcon) -> None:
        self._thumbnail_cache[path] = icon

    def clear_caches(self) -> None:
        self._thumbnail_cache.clear()
        logging.info("所有資源快取已清空。")
