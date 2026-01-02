import sys
import os
import gc
import logging
import traceback
import re
from typing import Optional, List, Dict, Any, Callable
from collections import OrderedDict
import psutil
import numpy as np

# 導入 natsort (如果有的話，在 Config 中已經檢查過，但這裡需要實際導入使用)
try:
    import natsort
except ImportError:
    natsort = None

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QFileDialog, QMessageBox, QStatusBar, QProgressBar, QListWidgetItem, QListWidget,
    QTreeWidgetItem, QDialog, QStyle
)
from PyQt6.QtGui import (
    QPixmap, QAction, QIcon, QKeySequence, QPalette, QCursor, QColor, QDropEvent, QMouseEvent, 
    QCloseEvent, QResizeEvent, QKeyEvent, QWheelEvent, QDragEnterEvent
)
from PyQt6.QtCore import (
    Qt, pyqtSlot, QThread, pyqtSignal, QEvent, QThreadPool, QTimer, QPoint, QRectF, QSize
)

from PIL import Image, ImageEnhance
from PIL.ImageQt import ImageQt
from PIL.ExifTags import TAGS

from image_viewer.config import Config, NATSORT_ENABLED, LANCZOS_RESAMPLE
from image_viewer.core.resource_manager import ResourceManager
from image_viewer.core.workers import EffectWorker, ThumbnailWorker, AsyncImageLoader
from image_viewer.ui.ui_manager import UIManager
from image_viewer.ui.theme_manager import ThemeManager
from image_viewer.ui.widgets import MagnifierWindow
from image_viewer.utils.decorators import requires_image

class ImageEditorWindow(QMainWindow):
    """圖片編輯器的主視窗。"""
    request_load_image = pyqtSignal(str)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config 
        
        self.image: Optional[Image.Image] = None
        self.current_path: Optional[str] = None
        self.undo_stack: List[Image.Image] = []
        self.image_list: List[str] = []
        self.current_index: int = -1
        self.scale: float = 1.0

        self._cached_pixmaps: OrderedDict[float, QPixmap] = OrderedDict()
        try:
            available_memory = psutil.virtual_memory().available / (1024 * 1024)
            self._cache_max_size = min(20, max(5, int(available_memory / 100)))
            logging.info(f"可用記憶體: {available_memory:.0f} MB, 動態設置快取大小為: {self._cache_max_size}")
        except Exception as e:
            logging.warning(f"無法獲取可用記憶體，使用預設快取大小 10: {e}")
            self._cache_max_size = 10
        # self._cache_access_order removed in favor of OrderedDict
        self._cache_hits = 0
        self._cache_misses = 0

        self._base_pixmap: Optional[QPixmap] = None
        self.is_panning: bool = False
        self.pan_start_pos: Optional[QPoint] = None
        self.is_fit_to_window_mode: bool = True
        self.has_unsaved_changes: bool = False
        self._is_programmatic_selection: bool = False
        self._base_image_for_effects: Optional[Image.Image] = None
        self.magnifier_enabled: bool = False
        self.magnifier_factor: float = self.config.MAGNIFIER_DEFAULT_FACTOR
        self.magnifier_window: Optional[MagnifierWindow] = None
        self.filmstrip_item_map: Dict[str, QListWidgetItem] = {}
        self._exif_decode_cache: Dict[bytes, str] = {}

        self.resource_manager = ResourceManager()

        self.effect_thread: Optional[QThread] = None
        self.effect_worker: Optional[EffectWorker] = None
        self.thread_pool = QThreadPool()
        self.filmstrip_generation = 0
        self._is_effect_processing = False
        self._current_effect_id = 0

        self.image_loader_thread = QThread()
        self.image_loader = AsyncImageLoader()
        self.image_loader.moveToThread(self.image_loader_thread)
        self.image_loader.image_loaded.connect(self._on_image_loaded)
        self.image_loader.load_failed.connect(self._on_load_failed)
        self.request_load_image.connect(self.image_loader.start_loading)
        self.image_loader.load_progress.connect(self._update_load_progress)
        self.image_loader_thread.start()

        self.setWindowTitle(self.config.BASE_WINDOW_TITLE) 
        self.setGeometry(100, 100, *self.config.DEFAULT_WINDOW_SIZE)
        self.setAcceptDrops(True)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.theme_manager = ThemeManager(QApplication.instance())
        self.theme_manager.apply_theme(self.config.DEFAULT_THEME)

        self.ui_manager = UIManager(self, self.config)
        self.ui_manager.setup_ui()
        self.ui_manager.create_actions()
        self.ui_manager.create_docks()
        self.ui_manager.create_menus()
        self.ui_manager.create_toolbars()

        self.image_label.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)

        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._check_memory_usage)
        self._memory_timer.start(self.config.MEMORY_CHECK_INTERVAL_MS)

        self.status_bar.showMessage("準備就緒。請開啟一張圖片。", 0)
        self._update_ui_state()

    def load_image(self, path: str) -> None:
        self._stop_effect_thread()
        if self.magnifier_window: self.magnifier_window.hide()

        try:
            normalized_path = os.path.normcase(os.path.normpath(path))
            if not os.path.exists(normalized_path):
                raise FileNotFoundError(f"檔案不存在: {normalized_path}")
            if not os.path.isfile(normalized_path):
                raise ValueError(f"不是有效的檔案: {normalized_path}")

            file_size = os.path.getsize(normalized_path)
            if file_size > self.config.MAX_IMAGE_FILE_SIZE:
                raise ValueError(
                    f"檔案過大 ({file_size / (1024*1024):.1f} MB), "
                    f"超過限制 ({self.config.MAX_IMAGE_FILE_SIZE / (1024*1024):.0f} MB)"
                )
            if file_size == 0:
                raise ValueError("檔案為空")
        except FileNotFoundError as e:
            self._handle_load_error("檔案不存在", str(e), path)
            return
        except ValueError as e:
            self._handle_load_error("無效的檔案", str(e), path)
            return
        except Exception as e:
            self._handle_load_error("錯誤", f"處理檔案時發生錯誤: {e}", path)
            return

        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
             self._remove_progress_bar()

        self.progress_bar = QProgressBar(self.status_bar)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.status_bar.showMessage(f"正在載入 {os.path.basename(normalized_path)}...", 0)

        self.request_load_image.emit(normalized_path)

    @pyqtSlot(int)
    def _update_load_progress(self, value: int):
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self.progress_bar.setValue(value)

    @pyqtSlot(object, str)
    def _on_image_loaded(self, new_image: Image.Image, path: str):
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self.progress_bar.setValue(100)
            QTimer.singleShot(500, self._remove_progress_bar)

        self._cleanup_image_resources()

        self.image = new_image
        self._base_image_for_effects = self.image.copy()
        self.current_path = path

        self._reset_image_state()
        self._update_file_list()

        try:
            exif_data = self.image.getexif()
            self._display_exif_data(exif_data)
        except Exception as e:
            logging.warning(f"讀取 EXIF 時發生錯誤: {e}")
            self._display_exif_data(None)

        self.histogram_widget.update_histogram(self.image)

        if self.is_fit_to_window_mode: self.fit_to_window()
        else: self.set_scale(1.0, is_manual_zoom=False)

        logging.info(f"成功載入圖片: {self.current_path}")
        QApplication.restoreOverrideCursor()
        self.update_status_bar()
        self._update_ui_state()

    @pyqtSlot(str, str)
    def _on_load_failed(self, error_message: str, path: str):
        self._remove_progress_bar()
        self._handle_load_error(f"載入失敗: {os.path.basename(path)}", error_message, path)
        QApplication.restoreOverrideCursor()
        self.status_bar.showMessage(f"載入失敗: {os.path.basename(path)}", 5000)
        self._update_ui_state()

    def _remove_progress_bar(self):
        """輔助函數，用於移除進度條"""
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            try:
                self.status_bar.removeWidget(self.progress_bar)
                self.progress_bar.deleteLater()
                self.progress_bar = None
            except RuntimeError as e:
                logging.debug(f"移除進度條時出現預期錯誤: {e}")
                self.progress_bar = None

    def _cleanup_image_resources(self):
        """統一的資源清理方法"""
        if self.image:
            try: self.image.close()
            except Exception as e: logging.warning(f"關閉主圖片時出錯: {e}")
            self.image = None
        if self._base_image_for_effects:
            try: self._base_image_for_effects.close()
            except Exception as e: logging.warning(f"關閉效果基礎圖片時出錯: {e}")
            self._base_image_for_effects = None

        self._cached_pixmaps.clear()
        self._base_pixmap = None

        for img in self.undo_stack:
            try: img.close()
            except Exception as e: logging.warning(f"關閉復原堆疊圖片時出錯: {e}")
        self.undo_stack.clear()

        gc.collect()

    @pyqtSlot()
    def open_file_dialog(self, checked: bool = False):
        if not self._prompt_to_save_if_needed(): return
        exts_str = " ".join([f"*{ext}" for ext in self.config.SUPPORTED_IMAGE_EXTENSIONS])
        path, _ = QFileDialog.getOpenFileName(self, "開啟圖片", os.path.dirname(self.current_path) if self.current_path else "", f"圖片 ({exts_str});;所有檔案 (*.*)")
        if path:
            self.load_image(path)

    @requires_image
    def save_image(self, checked: bool = False) -> bool:
        return self._execute_save(self.current_path) if self.current_path else self.save_image_as()

    @requires_image
    def save_image_as(self, checked: bool = False) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "圖片另存為", self.current_path or "", "PNG (*.png);;JPEG (*.jpg *.jpeg);;All Files (*)")
        return self._execute_save(path) if path else False

    @requires_image
    def push_undo(self) -> None:
        try:
            if len(self.undo_stack) >= self.config.MAX_UNDO_STEPS:
                self.undo_stack.pop(0).close()
            self.undo_stack.append(self.image.copy())
            self._update_ui_state()
        except Exception as e:
            logging.error(f"壓入復原堆疊時出錯: {e}")
            QMessageBox.warning(self, "錯誤", "無法儲存復原狀態，可能是記憶體不足。")

    def undo(self, *, is_effect_failure: bool = False, checked: bool = False) -> None:
        if checked is not False:
             is_effect_failure = False

        if not self.undo_stack:
            self.status_bar.showMessage("沒有更多操作可以復原。", 2000)
            return

        if self.image: self.image.close()
        self.image = self.undo_stack.pop()

        if self._base_image_for_effects: self._base_image_for_effects.close()

        try:
            self._base_image_for_effects = self.image.copy()
        except Exception as e:
            logging.error(f"復原時複製基礎圖片失敗: {e}")
            QMessageBox.critical(self, "復原失敗", f"無法複製圖片狀態: {e}")
            self._cleanup_image_resources()
            self._update_ui_state()
            return

        self._cached_pixmaps.clear()
        self._base_pixmap = None

        self._display_image()
        self.histogram_widget.update_histogram(self.image)
        self.ui_manager.reset_adjustment_sliders()

        if not is_effect_failure:
            self.set_unsaved_changes(True)
            self.status_bar.showMessage("已復原上一個操作。", 2000)

        self._update_ui_state()

    @requires_image
    def _apply_effect(self, effect_func: Callable) -> None:
        if not self._base_image_for_effects:
            logging.warning("_apply_effect: _base_image_for_effects 為 None。")
            return
        if self._is_effect_processing:
            self.status_bar.showMessage("正在處理效果，請稍候...", 2000)
            return
        self._is_effect_processing = True
        try:
            self._stop_effect_thread()
            self.push_undo()
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            self._current_effect_id += 1
            copied_image = self._base_image_for_effects.copy()
            self.effect_thread = QThread()
            self.effect_worker = EffectWorker()
            self.effect_worker.moveToThread(self.effect_thread)
            self.effect_worker.result_ready.connect(self._handle_effect_result)
            self.effect_worker.error_occurred.connect(self._handle_effect_error)
            self.effect_thread.started.connect(
                lambda: self.effect_worker.apply_effect(copied_image, effect_func, self._current_effect_id)
            )
            self.effect_thread.finished.connect(self._cleanup_thread)
            self.effect_thread.start()
        except Exception as e:
            logging.error(f"啟動效果執行緒時出錯: {e}")
            QApplication.restoreOverrideCursor()
            self.undo(is_effect_failure=True)
            self._is_effect_processing = False

    def _display_image(self) -> None:
        if not self.image:
            self.image_label.clear()
            return
        try:
            pixmap = self._get_scaled_pixmap(self.scale)
            self.image_label.setPixmap(pixmap)
            if self.magnifier_enabled and self.magnifier_window:
                # 注意：這裡修改了 MagnifierWindow 的介面，需要修正參數
                #self.magnifier_window.set_magnifier_params(self.image, self.scale, self.magnifier_factor)
                #if self.image_label.underMouse():
                #    self.update_magnifier_position_and_content(self.image_label.mapFromGlobal(QCursor.pos()))
                
                # 正確的呼叫方式（配合 widgets.py 的變更）
                self.magnifier_window.set_magnifier_params(self.image, self.scale, self.magnifier_factor)
                if self.image_label.underMouse():
                     self.update_magnifier_position_and_content(self.image_label.mapFromGlobal(QCursor.pos()))
        except Exception as e:
            logging.error(f"顯示圖片時出錯: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "顯示錯誤", f"無法顯示圖片: {e}")
            self._cleanup_image_resources()
            self._update_ui_state()

    def _get_scaled_pixmap(self, scale: float) -> QPixmap:
        scale = round(scale, 2)
        if scale in self._cached_pixmaps:
            self._cache_hits += 1
            self._cached_pixmaps.move_to_end(scale)
            return self._cached_pixmaps[scale]

        self._cache_misses += 1
        if self._cache_misses > 0 and self._cache_misses % self.config.CACHE_STATS_LOG_INTERVAL == 0:
            total_access = self._cache_hits + self._cache_misses
            if total_access > 0:
                hit_rate = self._cache_hits / total_access
                logging.info(f"快取統計: Hits={self._cache_hits}, Misses={self._cache_misses}, Hit Rate={hit_rate:.2%}")
        if not self.image:
            return QPixmap()
        if self._base_pixmap is None:
            try:
                if self.image is None: return QPixmap()
                self._base_pixmap = QPixmap.fromImage(ImageQt(self.image))
            except Exception as e:
                logging.error(f"從 PIL Image 創建 QPixmap 失敗: {e}")
                return QPixmap()
        w, h = self._base_pixmap.size().width(), self._base_pixmap.size().height()
        scaled_pixmap = self._base_pixmap.scaled(
            max(1, int(w * scale)),
            max(1, int(h * scale)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 快取移除策略 (LRU)
        if len(self._cached_pixmaps) >= self._cache_max_size:
            self._cached_pixmaps.popitem(last=False) # 移除最久未使用的項目 (第一個)
            
        self._cached_pixmaps[scale] = scaled_pixmap
        return scaled_pixmap

    def fit_to_window(self) -> None:
        if not self.image: return
        vp_size = self.scroll_area.viewport().size()
        if vp_size.width() <= 0 or vp_size.height() <= 0: return
        img_size = self.image.size
        if img_size[0] == 0 or img_size[1] == 0: return
        w_scale, h_scale = vp_size.width() / img_size[0], vp_size.height() / img_size[1]
        self.set_scale(min(w_scale, h_scale), is_manual_zoom=False)

    def set_scale(self, new_scale: float, is_manual_zoom: bool = True) -> None:
        if not self.image: return
        self.scale = max(0.01, min(new_scale, 10.0))
        if is_manual_zoom and self.is_fit_to_window_mode: self.toggle_fit_to_window_mode(False)
        self._display_image(); self.update_status_bar()

    def update_status_bar(self) -> None:
        if not self.image or not self.current_path:
            self.status_bar.clearMessage()
            if hasattr(self, 'zoom_entry'): self.zoom_entry.setText("")
            return
        w, h = self.image.size
        filename = os.path.basename(self.current_path)
        status_text = f"檔名: {filename} | 尺寸: {w}x{h} | 縮放: {self.scale * 100:.1f}%"
        self.status_bar.showMessage(status_text)
        if hasattr(self, 'zoom_entry'):
            if not self.zoom_entry.hasFocus():
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%")

    def set_unsaved_changes(self, has_changes: bool) -> None:
        if self.has_unsaved_changes == has_changes: return
        self.has_unsaved_changes = has_changes
        title = self.config.BASE_WINDOW_TITLE
        self.setWindowTitle(f"*{title}" if has_changes else title)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._prompt_to_save_if_needed():
            logging.info("開始關閉應用程式...")
            self._stop_effect_thread()
            if self.image_loader_thread and self.image_loader_thread.isRunning():
                logging.info("正在停止圖片載入執行緒...")
                self.image_loader_thread.quit()
                if not self.image_loader_thread.wait(3000):
                     logging.warning("圖片載入執行緒未在3秒內停止。")
            logging.info("正在等待縮圖執行緒池完成...")
            self.thread_pool.clear()
            if not self.thread_pool.waitForDone(2000):
                 logging.warning("縮圖執行緒池未在2秒內完成。")
            logging.info("正在清理圖片資源...")
            self._cleanup_image_resources()
            logging.info("正在清理資源管理器快取...")
            self.resource_manager.clear_caches()
            if self.magnifier_window:
                logging.info("正在關閉放大鏡視窗...")
                self.magnifier_window.close()
                self.magnifier_window = None
            if hasattr(self, '_memory_timer'):
                logging.info("正在停止記憶體檢查計時器...")
                self._memory_timer.stop()
            logging.info("正在執行垃圾回收...")
            gc.collect()
            logging.info("應用程式關閉完成。")
            event.accept()
        else:
            logging.info("使用者取消關閉。")
            event.ignore()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.image and self.is_fit_to_window_mode: self.fit_to_window()
        if hasattr(self, 'startup_container') and self.startup_label.isVisible():
            self.startup_container.setGeometry(self.scroll_area.viewport().rect())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key_map = {Qt.Key.Key_Left: self.prev_image, Qt.Key.Key_Right: self.next_image}
        if event.key() in key_map: key_map[event.key()]()
        else: super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.image and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()

    def eventFilter(self, source: Any, event: QEvent) -> bool:
        try:
            if source == self.image_label:
                if event.type() == QEvent.Type.MouseMove and self.magnifier_enabled:
                    self.update_magnifier_position_and_content(event.pos())
                    return True
                elif event.type() in (QEvent.Type.Leave, QEvent.Type.Enter) and self.magnifier_window:
                    self.magnifier_window.setVisible(event.type() == QEvent.Type.Enter and self.magnifier_enabled)
                    return True
            elif source == self.scroll_area.viewport():
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = True
                    self.pan_start_pos = event.pos()
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return True
                elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = False
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    return True
                elif event.type() == QEvent.Type.MouseMove and self.is_panning and self.pan_start_pos:
                    delta = event.pos() - self.pan_start_pos
                    self.scroll_area.horizontalScrollBar().setValue(self.scroll_area.horizontalScrollBar().value() - delta.x())
                    self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value() - delta.y())
                    self.pan_start_pos = event.pos()
                    return True
                elif event.type() == QEvent.Type.Resize:
                    if hasattr(self, 'startup_container') and self.startup_label.isVisible():
                         self.startup_container.setGeometry(self.scroll_area.viewport().rect())
                    if self.image and self.is_fit_to_window_mode:
                        self.fit_to_window()
        except Exception as e:
            logging.error(f"事件過濾器發生錯誤: {e}")
        return super().eventFilter(source, event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if (urls := event.mimeData().urls()) and os.path.isfile(path := urls[0].toLocalFile()):
            if self._prompt_to_save_if_needed(): self.load_image(path)

    def _populate_filmstrip(self) -> None:
        """分批載入縮圖,避免 UI 凍結"""
        self.thread_pool.clear()
        self.filmstrip_generation += 1
        self.filmstrip_widget.clear()
        self.filmstrip_item_map.clear()
        BATCH_SIZE = 20

        for i, path in enumerate(self.image_list):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            cached_icon = self.resource_manager.get_thumbnail(path)
            if cached_icon:
                item.setIcon(cached_icon)
            else:
                item.setIcon(self.style().standardIcon(
                    QStyle.StandardPixmap.SP_FileIcon
                ))
                worker = ThumbnailWorker(
                    path,
                    QSize(*self.config.THUMBNAIL_SIZE),
                    self.filmstrip_generation,
                    self.config
                )
                worker.signals.thumbnail_ready.connect(self._update_thumbnail)
                worker.signals.thumbnail_error.connect(self._update_thumbnail_error)
                self.thread_pool.start(worker)

            self.filmstrip_widget.addItem(item)
            self.filmstrip_item_map[path] = item
            if (i + 1) % BATCH_SIZE == 0:
                QApplication.processEvents()

    @pyqtSlot(QIcon, str, int)
    def _update_thumbnail(self, icon: QIcon, path: str, generation: int):
        if generation == self.filmstrip_generation and path in self.filmstrip_item_map:
            self.filmstrip_item_map[path].setIcon(icon)
            self.resource_manager.add_thumbnail(path, icon)

    def _execute_save(self, path: str) -> bool:
        if not self.image: return False
        try:
            save_image = self.image.convert('RGB') if path.lower().endswith(('.jpg', '.jpeg')) and self.image.mode == 'RGBA' else self.image
            save_image.save(path)
            self.status_bar.showMessage(f"圖片已儲存至: {os.path.basename(path)}", 3000)
            if os.path.normcase(path) != os.path.normcase(self.current_path or ""):
                self.current_path = os.path.normcase(os.path.normpath(path))
                self._update_file_list(rescan=True)
            self.set_unsaved_changes(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", f"儲存圖片時發生錯誤: {e}")
            logging.error(f"儲存失敗: {e}")
            return False

    def _reset_image_state(self) -> None:
        self._cached_pixmaps.clear()
        self._base_pixmap = None
        self.set_unsaved_changes(False)
        self.ui_manager.reset_adjustment_sliders()

    def _update_file_list(self, rescan: bool = False) -> None:
        if not self.current_path: return
        try:
            new_folder = os.path.dirname(self.current_path)
            current_folder = os.path.dirname(self.image_list[0]) if self.image_list else None
            if rescan or new_folder != current_folder:
                if not os.path.isdir(new_folder):
                    logging.warning(f"無法更新檔案列表，目錄不存在: {new_folder}")
                    self.image_list.clear()
                    self._populate_filmstrip()
                    return
                exts = self.config.SUPPORTED_IMAGE_EXTENSIONS
                self.image_list = [os.path.normcase(os.path.normpath(os.path.join(new_folder, f))) for f in os.listdir(new_folder) if f.lower().endswith(exts) and os.path.isfile(os.path.join(new_folder, f))]
                
                # [Fix] natsort usage
                if natsort:
                    self.image_list = natsort.natsorted(self.image_list)
                else:
                    self.image_list = sorted(self.image_list)
                    
                self.resource_manager.clear_caches()
                self._populate_filmstrip()
        except Exception as e:
            logging.error(f"更新檔案列表時出錯: {e}")
            self.image_list.clear()
            self._populate_filmstrip()
        try:
            self.current_index = self.image_list.index(self.current_path)
            if self.current_path in self.filmstrip_item_map:
                self._select_filmstrip_item(self.filmstrip_item_map[self.current_path])
        except ValueError:
            self.current_index = -1
            logging.warning(f"目前路徑 {self.current_path} 不在新的 image_list 中。")

    def _select_filmstrip_item(self, item_to_select: QListWidgetItem) -> None:
        self._is_programmatic_selection = True
        self.filmstrip_widget.setCurrentItem(item_to_select)
        self.filmstrip_widget.scrollToItem(item_to_select, QListWidget.ScrollHint.EnsureVisible)
        self._is_programmatic_selection = False

    def _display_exif_data(self, exif_data: Optional[Dict]) -> None:
        self.exif_tree.clear()
        if not exif_data:
            QTreeWidgetItem(self.exif_tree, ["無 EXIF 資訊", ""])
            return
        try:
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, f"Unknown ({tag_id})")
                if isinstance(value, bytes):
                    display_value = self._decode_exif_bytes(value)
                else:
                    display_value = str(value)
                if len(display_value) > 150:
                    display_value = display_value[:150] + '...'
                QTreeWidgetItem(self.exif_tree, [str(tag_name), display_value])
        except Exception as e:
            logging.error(f"解析 EXIF 標籤時出錯: {e}")
            self.exif_tree.clear()
            QTreeWidgetItem(self.exif_tree, ["解析 EXIF 時出錯", str(e)])

    def _decode_exif_bytes(self, data: bytes) -> str:
        """嘗試解碼 EXIF bytes 數據 (帶快取)"""
        if not data:
            return "[空數據]"
        if data in self._exif_decode_cache:
            return self._exif_decode_cache[data]
        data = data.rstrip(b'\x00')
        encodings = ['utf-8', 'latin-1', 'ascii']
        try:
            encodings.append(sys.getdefaultencoding())
        except Exception:
            pass
        result: str = ""
        for encoding in encodings:
            try:
                decoded = data.decode(encoding, errors='strict')
                if all(c.isprintable() or c.isspace() for c in decoded.strip()):
                    if decoded.startswith('\ufeff'):
                        decoded = decoded[1:]
                    result = decoded.strip()
                    break
            except (UnicodeDecodeError, AttributeError):
                continue
        if not result:
            if len(data) <= 20:
                result = f"[Hex: {data.hex()}]"
            else:
                result = f"[二進位資料, 長度 {len(data)} bytes]"
        if len(self._exif_decode_cache) > 100:
            self._exif_decode_cache.clear()
        self._exif_decode_cache[data] = result
        return result

    def _prompt_to_save_if_needed(self) -> bool:
        if not self.has_unsaved_changes: return True
        ret = QMessageBox.question(self, "儲存變更", "您有未儲存的變更，要儲存嗎？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if ret == QMessageBox.StandardButton.Save: return self.save_image()
        return ret != QMessageBox.StandardButton.Cancel

    def _check_memory_usage(self) -> None:
        try:
            memory_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            logging.info(f"目前記憶體使用量: {memory_mb:.2f} MB")
            if memory_mb > self.config.MEMORY_THRESHOLD_MB:
                logging.warning("記憶體用量超過閾值，開始清理快取。")
                self._cached_pixmaps.clear()
                self._base_pixmap = None
                gc.collect()
                self._display_image()
        except Exception as e: logging.error(f"檢查記憶體時出錯: {e}")

    @pyqtSlot(str, int)
    def _update_thumbnail_error(self, path: str, generation: int):
        if generation == self.filmstrip_generation and path in self.filmstrip_item_map:
            self.filmstrip_item_map[path].setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical))

    def _handle_load_error(self, title: str, msg: str, path: str):
        logging.error(f"載入失敗 (路徑: {path}): {title} - {msg}")
        QMessageBox.critical(self, title, msg)

    def _update_ui_state(self):
        """代理呼叫 UIManager 的 UI 狀態更新方法。"""
        self.ui_manager.update_ui_state()

    def _show_about_dialog(self, checked: bool = False):
        """顯示關於對話框"""
        shortcuts_html = """
        <p><b>常用快捷鍵:</b></p>
        <ul style="list-style-type:none; padding-left:0;">
            <li><b>Ctrl+O</b>: 開啟檔案</li>
            <li><b>Ctrl+S</b>: 儲存</li>
            <li><b>Ctrl+Z</b>: 復原</li>
            <li><b>Ctrl+M</b>: 開啟/關閉放大鏡</li>
            <li><b>Ctrl+T</b>: 切換主題</li>
            <li><b>&larr; / &rarr;</b> (方向鍵): 上一張/下一張</li>
            <li><b>滑鼠滾輪</b>: 縮放</li>
        </ul>
        """
        QMessageBox.about(self, "關於", f"""
            <h3>{self.config.BASE_WINDOW_TITLE}</h3> 
            <p>一個使用 PyQt6 和 Pillow 打造的高效能圖片瀏覽與編輯工具。</p>
            {shortcuts_html}
        """)

    @pyqtSlot(QListWidgetItem)
    def on_filmstrip_item_selected(self, current: QListWidgetItem):
        if self._is_programmatic_selection or not current: return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path and path != self.current_path and self._prompt_to_save_if_needed(): self.load_image(path)

    def prev_image(self, checked: bool = False):
        if self.current_index > 0 and self._prompt_to_save_if_needed(): self.load_image(self.image_list[self.current_index - 1])

    def next_image(self, checked: bool = False):
        if self.current_index < len(self.image_list) - 1 and self._prompt_to_save_if_needed(): self.load_image(self.image_list[self.current_index + 1])

    def zoom_in(self, checked: bool = False):
        self.set_scale(self.scale * self.config.ZOOM_IN_FACTOR)

    def zoom_out(self, checked: bool = False):
        self.set_scale(self.scale * self.config.ZOOM_OUT_FACTOR)

    @pyqtSlot(bool)
    def toggle_fit_to_window_mode(self, checked: bool):
        self.is_fit_to_window_mode = checked
        self.fit_to_window_action.setChecked(checked)
        policy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff if checked else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        self.scroll_area.setHorizontalScrollBarPolicy(policy); self.scroll_area.setVerticalScrollBarPolicy(policy)
        if checked and self.image: self.fit_to_window()

    @pyqtSlot(bool)
    def toggle_magnifier(self, checked: bool):
        if checked and not self.image:
            QMessageBox.information(self, "提示", "請先載入圖片以使用放大鏡。")
            self.toggle_magnifier_action.setChecked(False); return
        self.magnifier_enabled = checked
        if checked:
            if not self.magnifier_window:
                # [Fix] 傳遞 config 和 parent
                self.magnifier_window = MagnifierWindow(self, self.config)
            
            self.magnifier_window.set_magnifier_params(self.image, self.scale, self.magnifier_factor)
            self.status_bar.showMessage(
                f"放大鏡已啟用 ({self.magnifier_factor:.1f}x) - "
                f"移動滑鼠到圖片上查看 | 調整右側數值改變倍率", 
                5000
            )
        elif self.magnifier_window:
            self.magnifier_window.hide()
            self.status_bar.showMessage("放大鏡已關閉", 2000)
        if hasattr(self, 'magnifier_factor_spinbox'):
            self.magnifier_factor_spinbox.setEnabled(checked)

    @requires_image
    def _on_white_balance_slider_released(self):
        if not self._base_image_for_effects:
            return
        temp, tint = self.temp_slider.value(), self.tint_slider.value()
        def white_balance_func(img: Image.Image) -> Image.Image:
            img_rgb = img.convert('RGB')
            img_np = np.array(img_rgb, dtype=np.float32) / 255.0
            r, g, b = img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2]
            temp_factor = temp / 100.0
            if temp_factor > 0:
                r *= 1.0 + temp_factor * 0.8
                b *= 1.0 - temp_factor * 0.5
            else:
                r *= 1.0 + temp_factor * 0.5
                b *= 1.0 - temp_factor * 0.8
            tint_factor = tint / 100.0
            g *= 1.0 + tint_factor * 0.6
            r *= 1.0 - tint_factor * 0.1
            b *= 1.0 - tint_factor * 0.1
            img_np = np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0) * 255.0
            return Image.fromarray(img_np.astype(np.uint8)).convert(img.mode)
        self._apply_effect(white_balance_func)

    @requires_image
    def _on_fine_tune_slider_released(self):
        if not self._base_image_for_effects: return
        try:
            b_val = self.brightness_slider.value()
            c_val = self.contrast_slider.value()
            s_val = self.saturation_slider.value()
            
            b = b_val / self.config.ADJUSTMENT_DEFAULT
            c = c_val / self.config.ADJUSTMENT_DEFAULT
            s = s_val / self.config.ADJUSTMENT_DEFAULT

            max_factor = self.config.ADJUSTMENT_RANGE[1] / self.config.ADJUSTMENT_DEFAULT
            
            if not all(0 <= x <= max_factor for x in [b, c, s]):
                logging.warning(f"細緻調整值超出預期範圍: B={b}, C={c}, S={s}")
                b = max(0, min(b, max_factor))
                c = max(0, min(c, max_factor))
                s = max(0, min(s, max_factor))

            def fine_tune_func(img: Image.Image) -> Image.Image:
                img_proc = img.copy()
                try:
                    enhancer = ImageEnhance.Brightness(img_proc)
                    img_proc = enhancer.enhance(max(0.01, b))
                    enhancer = ImageEnhance.Contrast(img_proc)
                    img_proc = enhancer.enhance(max(0.01, c))
                    enhancer = ImageEnhance.Color(img_proc)
                    img_proc = enhancer.enhance(max(0.01, s))
                except Exception as e:
                    logging.error(f"應用 Enhancer 時出錯: {e}")
                    return img.copy()
                return img_proc
            self._apply_effect(fine_tune_func)
        except Exception as e:
            logging.error(f"細緻調整時發生錯誤: {e}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "調整失敗", f"無法應用調整: {e}")

    @pyqtSlot(object, int)
    def _handle_effect_result(self, new_image: Image.Image, effect_id: int):
        if effect_id != self._current_effect_id:
            try: new_image.close()
            except Exception as e: logging.warning(f"關閉過時效果圖片失敗: {e}")
            logging.debug(f"忽略過時效果 ID: {effect_id} (當前: {self._current_effect_id})")
            return
        try:
            if self.image:
                self.image.close()
            self.image = new_image
            if self._base_image_for_effects:
                self._base_image_for_effects.close()
            self._base_image_for_effects = self.image.copy()
            self._cached_pixmaps.clear()
            self._base_pixmap = None
            self._display_image()
            self.histogram_widget.update_histogram(self.image)
            self.set_unsaved_changes(True)
        except Exception as e:
            logging.critical(f"處理效果結果時複製基礎圖片失敗: {e}")
            QMessageBox.critical(self, "嚴重錯誤", f"無法更新圖片狀態: {e}。建議重新載入圖片。")
            self._cleanup_image_resources()
            self._update_ui_state()
        finally:
            if self.effect_thread:
                self.effect_thread.quit()
            self._is_effect_processing = False
            QApplication.restoreOverrideCursor()

    @pyqtSlot(str, int)
    def _handle_effect_error(self, error_msg: str, effect_id: int):
        if effect_id != self._current_effect_id:
            logging.debug(f"忽略過時效果錯誤 ID: {effect_id}")
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.critical(self, "效果套用失敗", error_msg)
        try:
            self.undo(is_effect_failure=True)
        except Exception as e:
            logging.error(f"效果失敗後復原時出錯: {e}")
        if self.effect_thread:
            self.effect_thread.quit()
        self._is_effect_processing = False

    def _stop_effect_thread(self):
        if self.effect_thread and self.effect_thread.isRunning():
            logging.debug(f"正在停止效果執行緒 (ID: {self._current_effect_id})...")
            if self.effect_worker: self.effect_worker.request_stop()
            self.effect_thread.quit()
            if not self.effect_thread.wait(1000):
                logging.warning("效果執行緒未在1秒內結束，強制終止。")
                self.effect_thread.terminate()
            self._cleanup_thread_references_only()
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
            self._is_effect_processing = False

    def _cleanup_thread(self):
        logging.debug(f"效果執行緒 finished 信號觸發 (ID: {self._current_effect_id})")
        self._cleanup_thread_references_only()

    def _cleanup_thread_references_only(self):
        self.effect_thread, self.effect_worker = None, None

    def update_magnifier_position_and_content(self, pos: QPoint):
        if not self.magnifier_window or not self.image: return
        if not self.image_label.rect().contains(pos):
             self.magnifier_window.hide()
             return
        
        # [Fix] 呼叫 MagnifierWindow.update_magnified_view 的新介面
        # self.magnifier_window.update_magnified_view(pos)
        self.magnifier_window.update_magnified_view(pos, self.image_label.size(), self.image_label.pixmap())
        
        global_pos = self.image_label.mapToGlobal(pos)
        screen_rect = QApplication.primaryScreen().availableGeometry()
        offset = self.config.MAGNIFIER_WINDOW_OFFSET
        x, y = global_pos.x() + offset, global_pos.y() + offset
        if x + self.magnifier_window.width() > screen_rect.right():
            x = global_pos.x() - self.magnifier_window.width() - offset
        if y + self.magnifier_window.height() > screen_rect.bottom():
            y = global_pos.y() - self.magnifier_window.height() - offset
        self.magnifier_window.move(x, y)
        if not self.magnifier_window.isVisible():
            self.magnifier_window.show()

    def _on_zoom_entry_submit(self):
        """處理縮放輸入框的提交"""
        try:
            text = self.zoom_entry.text().strip()
            if not text: return
            has_percent = '%' in text
            clean_text = re.sub(r'[^\d.]', '', text.replace('%', ''))
            if not clean_text or clean_text == '.' or clean_text.count('.') > 1:
                self.status_bar.showMessage("無效的縮放值", 2000)
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
                return
            value = float(clean_text)
            if value <= 0:
                self.status_bar.showMessage("縮放值必須大於 0", 2000)
                self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
                return
            scale: float
            if has_percent: scale = value / 100.0
            elif value >= 10: scale = value / 100.0
            else: scale = value
            if scale < 0.01:
                self.status_bar.showMessage("縮放值過小 (最小 1%)", 2000)
                scale = 0.01
            elif scale > 10.0:
                self.status_bar.showMessage("縮放值過大 (最大 1000%)", 2000)
                scale = 10.0
            self.set_scale(scale)
            self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
        except ValueError as e:
            self.status_bar.showMessage("無效的縮放值", 2000)
            logging.warning(f"無效的縮放輸入: '{self.zoom_entry.text()}' - {e}")
            self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
        except Exception as e:
            logging.error(f"處理縮放輸入時發生錯誤: {e}")
            self.status_bar.showMessage("處理縮放輸入時出錯", 2000)
            self.zoom_entry.setText(f"{self.scale * 100:.1f}%")
