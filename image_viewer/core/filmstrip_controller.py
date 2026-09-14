"""Filmstrip 媒體掃描、縮圖排程與選取同步。"""

import logging
import os
from typing import Dict, Optional

from PyQt6.QtCore import QObject, QSize, Qt, QThreadPool, pyqtSlot
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QStyle

from image_viewer.config import Config, NATSORT_ENABLED
from image_viewer.core.media_types import (
    MediaKind,
    classify_media_path,
    supported_media_extensions,
)
from image_viewer.core.resource_manager import ResourceManager
from image_viewer.core.video_thumbnailer import VideoThumbnailer
from image_viewer.core.workers import ThumbnailWorker

try:
    import natsort

    HAS_NATSORT = True
except ImportError:
    HAS_NATSORT = False


class FilmstripController(QObject):
    """管理共用媒體列表與 Filmstrip，避免主視窗承擔縮圖細節。"""

    BATCH_SIZE = 20

    def __init__(
        self,
        window,
        model,
        widget: QListWidget,
        config: Config,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.window = window
        self.model = model
        self.widget = widget
        self.config = config
        self.item_map: Dict[str, QListWidgetItem] = {}
        self.generation = 0
        self.is_programmatic_selection = False
        self.resource_manager = ResourceManager()
        self.thread_pool = QThreadPool(self)
        self.video_thumbnailer = VideoThumbnailer(
            QSize(*config.THUMBNAIL_SIZE),
            timeout_ms=config.VIDEO_THUMBNAIL_TIMEOUT_MS,
            parent=self,
        )
        self.video_thumbnailer.thumbnail_ready.connect(self._update_thumbnail)
        self.video_thumbnailer.thumbnail_error.connect(
            self._update_thumbnail_error
        )

    def refresh(self, rescan: bool = False) -> None:
        """必要時重新掃描目前資料夾，並同步 Filmstrip 選取項目。"""
        if not self.model.current_path:
            return
        try:
            new_folder = os.path.dirname(self.model.current_path)
            current_folder = (
                os.path.dirname(self.model.media_list[0])
                if self.model.media_list
                else None
            )
            if rescan or new_folder != current_folder:
                if not os.path.isdir(new_folder):
                    logging.warning(f"無法更新媒體列表，目錄不存在: {new_folder}")
                    self.model.clear_gallery()
                    self.populate()
                    return
                self.model.update_gallery(self._scan_folder(new_folder))
                self.resource_manager.clear_caches()
                self.populate()
        except Exception as error:
            logging.error(f"更新媒體列表時出錯: {error}")
            self.model.clear_gallery()
            self.populate()

        self.model.sync_current_index()
        item = self.item_map.get(self.model.current_path)
        if item is not None:
            self.select_item(item)
        elif self.model.current_index == -1:
            logging.warning(
                f"目前路徑 {self.model.current_path} 不在新的 media_list 中。"
            )

    def populate(self) -> None:
        """建立 Filmstrip 項目並排程圖片與影片縮圖。"""
        self.thread_pool.clear()
        self.video_thumbnailer.clear()
        self.generation += 1
        self.widget.clear()
        self.item_map.clear()

        for index, path in enumerate(self.model.media_list):
            item = self._create_item(path)
            self.widget.addItem(item)
            self.item_map[path] = item
            if (index + 1) % self.BATCH_SIZE == 0:
                QApplication.processEvents()

    def select_item(self, item: QListWidgetItem) -> None:
        self.is_programmatic_selection = True
        try:
            self.widget.setCurrentItem(item)
            self.widget.scrollToItem(
                item,
                QListWidget.ScrollHint.EnsureVisible,
            )
        finally:
            self.is_programmatic_selection = False

    def shutdown(self, timeout_ms: int = 2000) -> bool:
        """停止縮圖排程；回傳圖片 worker 是否在期限內結束。"""
        self.video_thumbnailer.clear()
        self.thread_pool.clear()
        completed = self.thread_pool.waitForDone(timeout_ms)
        self.resource_manager.clear_caches()
        return completed

    def _scan_folder(self, folder: str) -> list[str]:
        extensions = supported_media_extensions(self.config)
        paths = [
            os.path.normcase(os.path.normpath(os.path.join(folder, filename)))
            for filename in os.listdir(folder)
            if filename.lower().endswith(extensions)
            and os.path.isfile(os.path.join(folder, filename))
        ]
        if HAS_NATSORT and NATSORT_ENABLED:
            return natsort.natsorted(paths)
        return sorted(paths)

    def _create_item(self, path: str) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        media_kind = classify_media_path(path, self.config)
        item.setData(Qt.ItemDataRole.UserRole + 1, media_kind.value)
        item.setToolTip(os.path.basename(path))

        cached_icon = self.resource_manager.get_thumbnail(path)
        if cached_icon:
            item.setIcon(cached_icon)
        elif media_kind == MediaKind.VIDEO:
            item.setIcon(self.window.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaPlay
            ))
            self.video_thumbnailer.enqueue(path, self.generation)
        else:
            item.setIcon(self.window.style().standardIcon(
                QStyle.StandardPixmap.SP_FileIcon
            ))
            worker = ThumbnailWorker(
                path,
                QSize(*self.config.THUMBNAIL_SIZE),
                self.generation,
                self.config,
            )
            worker.signals.thumbnail_ready.connect(self._update_thumbnail)
            worker.signals.thumbnail_error.connect(self._update_thumbnail_error)
            self.thread_pool.start(worker)
        return item

    @pyqtSlot(object, str, int)
    def _update_thumbnail(self, qimage: object, path: str, generation: int) -> None:
        if generation != self.generation or path not in self.item_map:
            return
        try:
            icon = QIcon(QPixmap.fromImage(qimage))
        except Exception as error:
            logging.error(f"無法在主執行緒建立縮圖圖示: {error}")
            return
        self.item_map[path].setIcon(icon)
        self.resource_manager.add_thumbnail(path, icon)

    @pyqtSlot(str, int)
    def _update_thumbnail_error(self, path: str, generation: int) -> None:
        if generation == self.generation and path in self.item_map:
            self.item_map[path].setIcon(self.window.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxCritical
            ))
