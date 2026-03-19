import logging
from typing import Dict, Optional
from collections import OrderedDict
from PyQt6.QtGui import QIcon

class ResourceManager:
    """統一管理應用程式資源，如縮圖快取（LRU 策略）。"""

    # 縮圖快取最大容量
    MAX_THUMBNAIL_CACHE_SIZE = 200

    def __init__(self):
        self._thumbnail_cache: OrderedDict[str, QIcon] = OrderedDict()
        logging.info("ResourceManager 初始化完畢。")

    def get_thumbnail(self, path: str) -> Optional[QIcon]:
        icon = self._thumbnail_cache.get(path)
        if icon is not None:
            # 移到最近使用位置 (LRU)
            self._thumbnail_cache.move_to_end(path)
        return icon

    def add_thumbnail(self, path: str, icon: QIcon) -> None:
        if path in self._thumbnail_cache:
            self._thumbnail_cache.move_to_end(path)
        self._thumbnail_cache[path] = icon
        # 移除最久未使用的項目
        while len(self._thumbnail_cache) > self.MAX_THUMBNAIL_CACHE_SIZE:
            evicted_path, _ = self._thumbnail_cache.popitem(last=False)
            logging.debug(f"縮圖快取已滿，移除最久未使用: {evicted_path}")

    def clear_caches(self) -> None:
        self._thumbnail_cache.clear()
        logging.info("所有資源快取已清空。")

