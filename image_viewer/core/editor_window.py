import sys
import os
import gc
import logging
import traceback
import re
from typing import Optional, Dict, Any, Callable
from collections import OrderedDict
import psutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QStatusBar,
    QProgressBar, QListWidgetItem, QTreeWidgetItem
)
from PyQt6.QtGui import (
    QPixmap, QCursor, QDropEvent,
    QCloseEvent, QResizeEvent, QKeyEvent, QWheelEvent, QDragEnterEvent
)
from PyQt6.QtCore import (
    Qt, pyqtSlot, QThread, pyqtSignal, QEvent, QTimer, QPoint
)

from PIL import Image
from PIL.ImageQt import ImageQt
from PIL.ExifTags import TAGS

from image_viewer.config import Config
from image_viewer.core.workers import AsyncImageLoader
from image_viewer.core.archive_workflow import ArchiveWorkflowMixin
from image_viewer.core.effect_controller import EffectController
from image_viewer.core.image_ops import (
    normalize_and_validate_image_path,
    build_white_balance_effect,
    compute_fine_tune_factors,
    build_fine_tune_effect,
)
from image_viewer.ui.ui_manager import UIManager
from image_viewer.ui.theme_manager import ThemeManager
from image_viewer.ui.widgets import MagnifierWindow
from image_viewer.utils.decorators import requires_image
from image_viewer.core.image_model import ImageModel
from image_viewer.core.media_types import (
    MediaKind,
    classify_media_path,
    first_supported_file,
)
from image_viewer.core.video_controller import VideoController
from image_viewer.core.filmstrip_controller import FilmstripController
from image_viewer.core.video_fullscreen_controller import (
    VideoFullscreenController,
)


class ImageEditorWindow(ArchiveWorkflowMixin, QMainWindow):
    """圖片編輯器的主視窗。"""
    request_load_image = pyqtSignal(str)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

        # --- Model Initialization ---
        self.model = ImageModel(self.config)
        self.model.image_loaded.connect(self._on_model_image_loaded)
        self.model.image_cleared.connect(self._on_model_image_cleared)
        self.model.scale_changed.connect(self._on_model_scale_changed)
        self.model.unsaved_changes_changed.connect(self._on_model_unsaved_changes_changed)
        self.model.error_occurred.connect(self._handle_load_error)

        # --- UI State ---
        try:
            available_memory = psutil.virtual_memory().available / (1024 * 1024)
            self._cache_max_size = min(20, max(5, int(available_memory / 100)))
            logging.info(f"可用記憶體: {available_memory:.0f} MB, 動態設置快取大小為: {self._cache_max_size}")
        except Exception as e:
            logging.warning(f"無法獲取可用記憶體，使用預設快取大小 10: {e}")
            self._cache_max_size = 10
        # self._cache_access_order removed in favor of OrderedDict
        self._cached_pixmaps: OrderedDict[float, QPixmap] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0

        self._base_pixmap: Optional[QPixmap] = None
        self.is_panning: bool = False
        self.pan_start_pos: Optional[QPoint] = None
        self.is_fit_to_window_mode: bool = True
        self.has_unsaved_changes: bool = False
        self.is_video_mode: bool = False
        self.magnifier_enabled: bool = False
        self.magnifier_factor: float = self.config.MAGNIFIER_DEFAULT_FACTOR
        self.magnifier_window: Optional[MagnifierWindow] = None
        self._exif_decode_cache: Dict[bytes, str] = {}

        self._setup_archive_workflow()

        self.effect_controller = EffectController(self)
        self.effect_controller.result_ready.connect(self._handle_effect_result)
        self.effect_controller.error_occurred.connect(self._handle_effect_error)
        self.image_loader_thread = QThread()
        self._close_after_image_load = False
        self._pending_image_path: Optional[str] = None
        self._image_load_cursor_active = False
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
        self.video_controller = VideoController(
            self.video_widget,
            self.video_play_button,
            self.video_stop_button,
            self.video_position_slider,
            self.video_time_label,
            self.video_mute_button,
            self.video_volume_slider,
            self,
        )
        self.video_controller.error_occurred.connect(self._on_video_error)
        self.video_controller.status_changed.connect(self._on_video_status)
        self.video_fullscreen_controller = VideoFullscreenController(
            self,
            self.video_widget,
            self.video_page,
            self.video_controls,
            self.config.VIDEO_CONTROLS_HIDE_DELAY_MS,
            self,
        )
        self.ui_manager.create_actions()
        self.ui_manager.create_docks()
        self.filmstrip_controller = FilmstripController(
            self,
            self.model,
            self.filmstrip_widget,
            self.config,
            self,
        )
        # Compatibility aliases for existing integrations and tests.
        self.filmstrip_item_map = self.filmstrip_controller.item_map
        self.resource_manager = self.filmstrip_controller.resource_manager
        self.ui_manager.create_menus()
        self.ui_manager.create_toolbars()

        self.image_label.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)

        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._check_memory_usage)
        self._memory_timer.start(self.config.MEMORY_CHECK_INTERVAL_MS)

        self.progress_bar: Optional[QProgressBar] = None

        self.status_bar.showMessage("準備就緒。請開啟圖片或影片。", 0)
        self._update_ui_state()

    def load_media(self, path: str) -> None:
        if not self._stop_effect_thread():
            self.status_bar.showMessage("正在結束圖片效果處理，請稍後再試。", 3000)
            return
        if self.magnifier_window:
            self.magnifier_window.hide()

        try:
            normalized_path = os.path.normcase(os.path.normpath(path))
            media_kind = classify_media_path(normalized_path, self.config)
            if media_kind != MediaKind.VIDEO:
                self.video_fullscreen_controller.exit()
            if media_kind == MediaKind.ARCHIVE:
                self._load_archive(normalized_path)
                return
            if media_kind == MediaKind.UNSUPPORTED:
                raise ValueError(f"不支援的檔案格式: {os.path.splitext(path)[1].lower()}")
            max_size = (
                self.config.MAX_VIDEO_FILE_SIZE
                if media_kind == MediaKind.VIDEO
                else self.config.MAX_IMAGE_FILE_SIZE
            )
            normalized_path = normalize_and_validate_image_path(
                path,
                max_size,
            )
        except FileNotFoundError as e:
            self._handle_load_error("檔案不存在", str(e), path)
            return
        except ValueError as e:
            self._handle_load_error("無效的檔案", str(e), path)
            return
        except Exception as e:
            self._handle_load_error("錯誤", f"處理檔案時發生錯誤: {e}", path)
            return

        if media_kind == MediaKind.VIDEO:
            self._load_video(normalized_path)
            return

        self.video_controller.clear()
        self.is_video_mode = False
        self.central_stack.setCurrentWidget(self.scroll_area)
        self._pending_image_path = normalized_path

        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self._remove_progress_bar()

        self.progress_bar = QProgressBar(self.status_bar)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        if not self._image_load_cursor_active:
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            self._image_load_cursor_active = True
        self.status_bar.showMessage(f"正在載入 {os.path.basename(normalized_path)}...", 0)

        self.request_load_image.emit(normalized_path)

    def load_image(self, path: str) -> None:
        """向後相容入口；現在會依檔案類型分派。"""
        self.load_media(path)

    def _load_video(self, path: str) -> None:
        """切換至影片頁面並交由 Qt Multimedia 播放。"""
        self._pending_image_path = None
        self._finish_image_load_cursor()
        self._remove_progress_bar()
        self._cleanup_image_resources()
        self.video_controller.clear()
        self.model.set_current_media(path)
        self.is_video_mode = True
        self.central_stack.setCurrentWidget(self.video_page)
        self.startup_container.setVisible(False)
        self._display_exif_data(None)
        self.histogram_widget.update_histogram(None)
        self._update_file_list()
        self.video_controller.open(path)
        self._update_ui_state()
        logging.info(f"開始載入影片: {path}")

    @pyqtSlot(int)
    def _update_load_progress(self, value: int):
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self.progress_bar.setValue(value)

    @pyqtSlot(object, str)
    def _on_image_loaded(self, new_image: Image.Image, path: str):
        if self._close_after_image_load:
            new_image.close()
            self.image_loader_thread.quit()
            QTimer.singleShot(0, self.close)
            return
        if path != self._pending_image_path:
            new_image.close()
            logging.info(f"忽略已過期的圖片載入結果: {path}")
            return
        self._pending_image_path = None
        if hasattr(self, 'progress_bar') and self.progress_bar is not None:
            self.progress_bar.setValue(100)
            QTimer.singleShot(500, self._remove_progress_bar)

        self.video_controller.clear()
        self.is_video_mode = False
        self.central_stack.setCurrentWidget(self.scroll_area)
        self._cleanup_image_resources()

        # Update Model
        self.model.load_new_image(new_image, path)

        self._reset_image_state()
        self._update_file_list()

        try:
            exif_data = new_image.getexif()
            self._display_exif_data(exif_data)
        except Exception as e:
            logging.warning(f"讀取 EXIF 時發生錯誤: {e}")
            self._display_exif_data(None)

        self.histogram_widget.update_histogram(new_image)

        if self.is_fit_to_window_mode:
            self.fit_to_window()
        else:
            self.set_scale(1.0, is_manual_zoom=False)

        logging.info(f"成功載入圖片: {path}")
        self._finish_image_load_cursor()
        self.update_status_bar()
        self._update_ui_state()

    @pyqtSlot(str, str)
    def _on_load_failed(self, error_message: str, path: str):
        if self._close_after_image_load:
            self.image_loader_thread.quit()
            QTimer.singleShot(0, self.close)
            return
        if path != self._pending_image_path:
            logging.info(f"忽略已過期的圖片載入錯誤: {path}")
            return
        self._pending_image_path = None
        self._remove_progress_bar()
        self._handle_load_error(f"載入失敗: {os.path.basename(path)}", error_message, path)
        self._finish_image_load_cursor()
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

    def _finish_image_load_cursor(self) -> None:
        if self._image_load_cursor_active:
            QApplication.restoreOverrideCursor()
            self._image_load_cursor_active = False

    def _cleanup_image_resources(self):
        """統一的資源清理方法 (UI 層級，圖片實體已移至 Model)"""
        self._cached_pixmaps.clear()
        self._base_pixmap = None
        gc.collect()

    # --- Model Event Handlers ---
    @pyqtSlot()
    def _on_model_image_loaded(self):
        self._cached_pixmaps.clear()
        self._base_pixmap = None
        self._display_image()
        self.histogram_widget.update_histogram(self.model.image)

    @pyqtSlot()
    def _on_model_image_cleared(self):
        self.image_label.clear()
        self.histogram_widget.update_histogram(None)
        self.update_status_bar()

    @pyqtSlot(float)
    def _on_model_scale_changed(self, new_scale: float):
        self._display_image()
        self.update_status_bar()

    @pyqtSlot(bool)
    def _on_model_unsaved_changes_changed(self, has_changes: bool):
        title = self.config.BASE_WINDOW_TITLE
        self.setWindowTitle(f"*{title}" if has_changes else title)

    @pyqtSlot()
    def open_file_dialog(self, checked: bool = False):
        if not self._prompt_to_save_if_needed():
            return
        img_exts = " ".join([f"*{ext}" for ext in self.config.SUPPORTED_IMAGE_EXTENSIONS])
        video_exts = " ".join([f"*{ext}" for ext in self.config.SUPPORTED_VIDEO_EXTENSIONS])
        arc_exts = " ".join([f"*{ext}" for ext in self.config.SUPPORTED_ARCHIVE_EXTENSIONS])
        all_exts = (
            f"支援的檔案 ({img_exts} {video_exts} {arc_exts});;"
            f"圖片 ({img_exts});;影片 ({video_exts});;"
            f"壓縮檔 ({arc_exts});;所有檔案 (*.*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "開啟檔案", os.path.dirname(
            self.model.current_path) if self.model.current_path else "", all_exts)
        if path:
            self.load_media(path)

    def save_image(self, checked: bool = False) -> bool:
        return self._execute_save(self.model.current_path) if self.model.current_path else self.save_image_as()

    def save_image_as(self, checked: bool = False) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "圖片另存為", self.model.current_path or "",
                                              "PNG (*.png);;JPEG (*.jpg *.jpeg);;All Files (*)")
        return self._execute_save(path) if path else False

    def push_undo(self) -> None:
        self.model.push_undo()
        self._update_ui_state()

    def undo(self, *, is_effect_failure: bool = False, checked: bool = False) -> None:
        if checked is not False:
            is_effect_failure = False

        if not self.model.undo(is_effect_failure):
            self.status_bar.showMessage("沒有更多操作可以復原。", 2000)
            return

        self.ui_manager.reset_adjustment_sliders()

        if not is_effect_failure:
            self.status_bar.showMessage("已復原上一個操作。", 2000)

        self._update_ui_state()

    def _apply_effect(self, effect_func: Callable) -> None:
        base_image = self.model.get_base_image_for_effects()
        if not base_image:
            logging.warning("_apply_effect: base_image 為 None。")
            return
        if self.effect_controller.is_busy:
            base_image.close()
            self.status_bar.showMessage("正在處理效果，請稍候...", 2000)
            return
        try:
            if not self._stop_effect_thread():
                base_image.close()
                self.status_bar.showMessage("上一個效果仍在結束中，請稍後再試。", 3000)
                return
            self.push_undo()
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            if not self.effect_controller.start(base_image, effect_func):
                base_image.close()
                QApplication.restoreOverrideCursor()
                self.undo(is_effect_failure=True)
        except Exception as e:
            logging.error(f"啟動效果執行緒時出錯: {e}")
            QApplication.restoreOverrideCursor()
            self.undo(is_effect_failure=True)

    def _display_image(self) -> None:
        if not self.model.image:
            self.image_label.clear()
            return
        try:
            pixmap = self._get_scaled_pixmap(self.model.scale)
            self.image_label.setPixmap(pixmap)
            if self.magnifier_enabled and self.magnifier_window:
                self.magnifier_window.set_magnifier_params(self.model.image, self.model.scale, self.magnifier_factor)
                if self.image_label.underMouse():
                    self.update_magnifier_position_and_content(self.image_label.mapFromGlobal(QCursor.pos()))
        except Exception as e:
            logging.error(f"顯示圖片時出錯: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "顯示錯誤", f"無法顯示圖片: {e}")
            self.model.clear()
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
        if not self.model.image:
            return QPixmap()
        if self._base_pixmap is None:
            try:
                self._base_pixmap = QPixmap.fromImage(ImageQt(self.model.image))
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
            self._cached_pixmaps.popitem(last=False)  # 移除最久未使用的項目 (第一個)

        self._cached_pixmaps[scale] = scaled_pixmap
        return scaled_pixmap

    def fit_to_window(self) -> None:
        if not self.model.image:
            return
        vp_size = self.scroll_area.viewport().size()
        if vp_size.width() <= 0 or vp_size.height() <= 0:
            return
        img_size = self.model.image.size
        if img_size[0] == 0 or img_size[1] == 0:
            return
        w_scale, h_scale = vp_size.width() / img_size[0], vp_size.height() / img_size[1]
        self.set_scale(min(w_scale, h_scale), is_manual_zoom=False)

    def set_scale(self, new_scale: float, is_manual_zoom: bool = True) -> None:
        if not self.model.image:
            return
        self.model.scale = new_scale
        if is_manual_zoom and self.is_fit_to_window_mode:
            self.toggle_fit_to_window_mode(False)

    def update_status_bar(self) -> None:
        if not self.model.image or not self.model.current_path:
            self.status_bar.clearMessage()
            if hasattr(self, 'zoom_entry'):
                self.zoom_entry.setText("")
            return
        w, h = self.model.image.size
        filename = os.path.basename(self.model.current_path)
        status_text = f"檔名: {filename} | 尺寸: {w}x{h} | 縮放: {self.model.scale * 100:.1f}%"
        self.status_bar.showMessage(status_text)
        if hasattr(self, 'zoom_entry'):
            if not self.zoom_entry.hasFocus():
                self.zoom_entry.setText(f"{self.model.scale * 100:.1f}%")

    def set_unsaved_changes(self, has_changes: bool) -> None:
        self.model.set_unsaved_changes(has_changes)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._prompt_to_save_if_needed():
            logging.info("開始關閉應用程式...")
            self.video_fullscreen_controller.exit()
            self.video_controller.clear()
            self._finish_image_load_cursor()
            if not self._stop_effect_thread():
                logging.info("效果執行緒仍在執行，延後關閉應用程式。")
                event.ignore()
                return
            if self.archive_extract_thread and self.archive_extract_thread.isRunning():
                self._close_after_archive = True
                self.status_bar.showMessage("正在完成壓縮檔處理，完成後將關閉程式...")
                event.ignore()
                return
            if self.image_loader_thread and self.image_loader_thread.isRunning():
                logging.info("正在停止圖片載入執行緒...")
                self.image_loader_thread.quit()
                if not self.image_loader_thread.wait(3000):
                    logging.warning("圖片載入執行緒未在3秒內停止；完成後再關閉程式。")
                    self._close_after_image_load = True
                    event.ignore()
                    return
            logging.info("正在等待縮圖執行緒池完成...")
            if not self.filmstrip_controller.shutdown(2000):
                logging.warning("縮圖執行緒池未在2秒內完成。")
            logging.info("正在清理圖片資源...")
            self._cleanup_image_resources()
            logging.info("正在清理壓縮檔暫存資料夾...")
            self.archive_manager.cleanup()
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
        if self.model.image and self.is_fit_to_window_mode:
            self.fit_to_window()
        if hasattr(self, 'startup_container') and self.startup_label.isVisible():
            self.startup_container.setGeometry(self.scroll_area.viewport().rect())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        has_control = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if has_control and event.key() == Qt.Key.Key_Left:
            self.prev_media()
        elif has_control and event.key() == Qt.Key.Key_Right:
            self.next_media()
        elif self.is_video_mode and event.key() == Qt.Key.Key_Space:
            self.video_controller.toggle_playback()
        elif self.is_video_mode and event.key() == Qt.Key.Key_Left:
            self.video_controller.seek_relative(-5000)
        elif self.is_video_mode and event.key() == Qt.Key.Key_Right:
            self.video_controller.seek_relative(5000)
        elif self.is_video_mode and event.key() == Qt.Key.Key_Up:
            self.video_volume_slider.setValue(
                min(100, self.video_volume_slider.value() + 5)
            )
        elif self.is_video_mode and event.key() == Qt.Key.Key_Down:
            self.video_volume_slider.setValue(
                max(0, self.video_volume_slider.value() - 5)
            )
        elif self.is_video_mode and event.key() == Qt.Key.Key_M:
            self.video_controller.toggle_muted()
        elif event.key() == Qt.Key.Key_Left:
            self.prev_media()
        elif event.key() == Qt.Key.Key_Right:
            self.next_media()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.model.image and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()

    def eventFilter(self, source: Any, event: QEvent) -> bool:
        try:
            if source == self.image_label:
                if event.type() == QEvent.Type.MouseMove and self.magnifier_enabled:
                    logging.debug(f"MouseMove triggered at {event.pos()}")
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
                    if self.model.image and self.is_fit_to_window_mode:
                        self.fit_to_window()
        except Exception as e:
            logging.error(f"事件過濾器發生錯誤: {e}")
        return super().eventFilter(source, event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and first_supported_file(
            (url.toLocalFile() for url in event.mimeData().urls()),
            self.config,
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        path = first_supported_file(paths, self.config)
        if path and self._prompt_to_save_if_needed():
            self.load_media(path)
            event.acceptProposedAction()
        elif not path:
            self.status_bar.showMessage("拖放內容中沒有支援的檔案。", 3000)

    def _populate_filmstrip(self) -> None:
        """向後相容入口；Filmstrip 細節由 controller 管理。"""
        self.filmstrip_controller.populate()

    def _execute_save(self, path: str) -> bool:
        if not self.model.image:
            return False
        try:
            save_image = self.model.image.convert('RGB') if path.lower().endswith(
                ('.jpg', '.jpeg')) and self.model.image.mode == 'RGBA' else self.model.image
            save_image.save(path)
            self.status_bar.showMessage(f"圖片已儲存至: {os.path.basename(path)}", 3000)
            if os.path.normcase(path) != os.path.normcase(self.model.current_path or ""):
                self.model.current_path = os.path.normcase(os.path.normpath(path))
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
        self.filmstrip_controller.refresh(rescan)

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
            # 當快取超過 100 筆時整體清除，避免記憶體無限成長
            self._exif_decode_cache.clear()
        self._exif_decode_cache[data] = result
        return result

    def _prompt_to_save_if_needed(self) -> bool:
        if not self.model.has_unsaved_changes:
            return True
        ret = QMessageBox.question(self, "儲存變更", "您有未儲存的變更，要儲存嗎？", QMessageBox.StandardButton.Save |
                                   QMessageBox.StandardButton.Discard
                                   | QMessageBox.StandardButton.Cancel,
                                   QMessageBox.StandardButton.Save)
        if ret == QMessageBox.StandardButton.Save:
            return self.save_image()
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
        except Exception as e:
            logging.error(f"檢查記憶體時出錯: {e}")

    def _handle_load_error(self, title: str, msg: str, path: str = ""):
        if path:
            logging.error(f"載入失敗 (路徑: {path}): {title} - {msg}")
        else:
            logging.error(f"圖片處理錯誤: {title} - {msg}")
        QMessageBox.critical(self, title, msg)

    @pyqtSlot(str)
    def _on_video_status(self, message: str) -> None:
        if self.is_video_mode:
            self.status_bar.showMessage(message)

    @pyqtSlot(str)
    def _on_video_error(self, message: str) -> None:
        logging.error(f"影片播放失敗 ({self.model.current_path}): {message}")
        QMessageBox.critical(self, "影片播放失敗", message)
        self.status_bar.showMessage("影片播放失敗", 5000)

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
            <li><b>Ctrl+&larr; / Ctrl+&rarr;</b>: 上一個/下一個媒體</li>
            <li><b>Space</b>: 影片播放/暫停</li>
            <li><b>&larr; / &rarr;</b>: 影片後退/前進 5 秒</li>
            <li><b>M</b>: 影片靜音切換</li>
            <li><b>滑鼠滾輪</b>: 縮放</li>
        </ul>
        """
        QMessageBox.about(self, "關於", f"""
            <h3>{self.config.BASE_WINDOW_TITLE}</h3>
            <p>一個使用 PyQt6 和 Pillow 打造的圖片瀏覽、編輯與影片播放工具。</p>
            {shortcuts_html}
        """)

    @pyqtSlot(QListWidgetItem)
    def on_filmstrip_item_selected(self, current: QListWidgetItem):
        if self.filmstrip_controller.is_programmatic_selection or not current:
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path and path != self.model.current_path and self._prompt_to_save_if_needed():
            self.load_media(path)

    def prev_media(self, checked: bool = False):
        prev_path = self.model.get_prev_media_path()
        if prev_path and self._prompt_to_save_if_needed():
            self.load_media(prev_path)

    def next_media(self, checked: bool = False):
        next_path = self.model.get_next_media_path()
        if next_path and self._prompt_to_save_if_needed():
            self.load_media(next_path)

    def prev_image(self, checked: bool = False):
        """向後相容別名。"""
        self.prev_media(checked)

    def next_image(self, checked: bool = False):
        """向後相容別名。"""
        self.next_media(checked)

    def zoom_in(self, checked: bool = False):
        self.set_scale(self.model.scale * self.config.ZOOM_IN_FACTOR)

    def zoom_out(self, checked: bool = False):
        self.set_scale(self.model.scale * self.config.ZOOM_OUT_FACTOR)

    def open_duplicate_checker(self, checked: bool = False) -> None:
        """開啟重複圖片檢查工具。"""
        if getattr(self, 'duplicate_checker_window', None) is None:
            from image_viewer.duplicate_checker.ui.main_window import MainWindow as DuplicateCheckerWindow
            self.duplicate_checker_window = DuplicateCheckerWindow()
        self.duplicate_checker_window.show()
        self.duplicate_checker_window.raise_()
        self.duplicate_checker_window.activateWindow()

    @pyqtSlot(bool)
    def toggle_fit_to_window_mode(self, checked: bool):
        self.is_fit_to_window_mode = checked
        self.fit_to_window_action.setChecked(checked)
        policy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff if checked else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        self.scroll_area.setHorizontalScrollBarPolicy(policy)
        self.scroll_area.setVerticalScrollBarPolicy(policy)
        if checked and self.model.image:
            self.fit_to_window()

    @pyqtSlot(bool)
    def toggle_magnifier(self, checked: bool):
        if checked and not self.model.image:
            QMessageBox.information(self, "提示", "請先載入圖片以使用放大鏡。")
            self.toggle_magnifier_action.setChecked(False)
            return
        self.magnifier_enabled = checked
        if checked:
            if not self.magnifier_window:
                # [Fix] 傳遞 config 和 parent
                self.magnifier_window = MagnifierWindow(self, self.config)

            self.magnifier_window.set_magnifier_params(self.model.image, self.model.scale, self.magnifier_factor)
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
        if not self.model.has_base_image:
            return
        temp, tint = self.temp_slider.value(), self.tint_slider.value()
        self._apply_effect(build_white_balance_effect(temp, tint))

    @requires_image
    def _on_fine_tune_slider_released(self):
        if not self.model.has_base_image:
            return
        try:
            b_val = self.brightness_slider.value()
            c_val = self.contrast_slider.value()
            s_val = self.saturation_slider.value()

            b, c, s = compute_fine_tune_factors(
                brightness_value=b_val,
                contrast_value=c_val,
                saturation_value=s_val,
                adjustment_default=self.config.ADJUSTMENT_DEFAULT,
                adjustment_max=self.config.ADJUSTMENT_RANGE[1],
            )

            self._apply_effect(build_fine_tune_effect(b, c, s))
        except Exception as e:
            logging.error(f"細緻調整時發生錯誤: {e}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "調整失敗", f"無法應用調整: {e}")

    @pyqtSlot(object)
    def _handle_effect_result(self, new_image: Image.Image):
        try:
            # We must use model.set_image rather than directly accessing self.image.
            self.model.set_image(new_image)
            # The model's _on_model_image_loaded will clear caches and trigger display
        except Exception as e:
            logging.critical(f"處理效果結果時更新模型失敗: {e}")
            QMessageBox.critical(self, "嚴重錯誤", f"無法更新圖片狀態: {e}。建議重新載入圖片。")
            self._cleanup_image_resources()
            self._update_ui_state()
        finally:
            QApplication.restoreOverrideCursor()

    @pyqtSlot(str)
    def _handle_effect_error(self, error_msg: str):
        QApplication.restoreOverrideCursor()
        QMessageBox.critical(self, "效果套用失敗", error_msg)
        try:
            self.undo(is_effect_failure=True)
        except Exception as e:
            logging.error(f"效果失敗後復原時出錯: {e}")

    def _stop_effect_thread(self) -> bool:
        stopped = self.effect_controller.stop()
        if stopped and QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        return stopped

    def update_magnifier_position_and_content(self, pos: QPoint):
        if not self.magnifier_window or not self.model.image:
            return
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
            if not text:
                return
            has_percent = '%' in text
            clean_text = re.sub(r'[^\d.]', '', text.replace('%', ''))
            if not clean_text or clean_text == '.' or clean_text.count('.') > 1:
                self.status_bar.showMessage("無效的縮放值", 2000)
                self.zoom_entry.setText(f"{self.model.scale * 100:.1f}%")
                return
            value = float(clean_text)
            if value <= 0:
                self.status_bar.showMessage("縮放值必須大於 0", 2000)
                self.zoom_entry.setText(f"{self.model.scale * 100:.1f}%")
                return
            scale: float
            if has_percent:
                scale = value / 100.0
            elif value >= 10:
                scale = value / 100.0
            else:
                scale = value
            if scale < 0.01:
                self.status_bar.showMessage("縮放值過小 (最小 1%)", 2000)
                scale = 0.01
            elif scale > 10.0:
                self.status_bar.showMessage("縮放值過大 (最大 1000%)", 2000)
                scale = 10.0
            self.set_scale(scale)
            self.zoom_entry.setText(f"{self.model.scale * 100:.1f}%")
        except ValueError as e:
            self.status_bar.showMessage("無效的縮放值", 2000)
            logging.warning(f"無效的縮放輸入: '{self.zoom_entry.text()}' - {e}")
            self.zoom_entry.setText(f"{self.model.scale * 100:.1f}%")
        except Exception as e:
            logging.error(f"處理縮放輸入時發生錯誤: {e}")
            self.status_bar.showMessage("處理縮放輸入時出錯", 2000)
            self.zoom_entry.setText(f"{self.model.scale * 100:.1f}%")
