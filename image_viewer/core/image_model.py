import uuid
import logging
from typing import Optional, List
from PyQt6.QtCore import QObject, pyqtSignal
from PIL import Image
from image_viewer.core.edit_history import EditHistory


class ImageModel(QObject):
    """
    核心圖片資料模型，負責管理圖片狀態（縮放比例、復原堆疊、影像實體等），
    並透過 PyQt Signals 與 UI 層溝通，達到解耦目的。
    """

    # --- Signals ---
    image_loaded = pyqtSignal()
    image_cleared = pyqtSignal()
    preview_changed = pyqtSignal()
    scale_changed = pyqtSignal(float)
    unsaved_changes_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str, str)  # title, message

    def __init__(self, config):
        super().__init__()
        self.config = config

        self.image: Optional[Image.Image] = None
        self.current_path: Optional[str] = None
        self.media_list: List[str] = []
        self.current_index: int = -1

        self.history = EditHistory(config.MAX_UNDO_STEPS)
        self.original_snapshot = None
        self.preview_image = None
        self.document_version = 0
        self.state_id = uuid.uuid4().hex
        self.saved_state_id = self.state_id
        self._scale: float = 1.0
        self._has_unsaved_changes: bool = False

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, new_scale: float):
        clamped_scale = max(0.01, min(new_scale, 10.0))
        if self._scale != clamped_scale:
            self._scale = clamped_scale
            self.scale_changed.emit(self._scale)

    @property
    def has_unsaved_changes(self) -> bool:
        return self._has_unsaved_changes

    def set_unsaved_changes(self, has_changes: bool):
        if not has_changes:
            self.saved_state_id = self.state_id
        if self._has_unsaved_changes != has_changes:
            self._has_unsaved_changes = has_changes
            self.unsaved_changes_changed.emit(self._has_unsaved_changes)

    def load_new_image(self, pil_image: Image.Image, path: str):
        """載入新圖片並重置狀態"""
        history = EditHistory(self.config.MAX_UNDO_STEPS)
        try:
            original = history.write(pil_image, "original")
        except Exception as error:
            history.clear()
            pil_image.close()
            self.error_occurred.emit("載入失敗", str(error))
            return False
        self.clear()
        self.history = history
        self.image = pil_image
        self.current_path = path
        self.original_snapshot = original
        self._scale = 1.0
        self._has_unsaved_changes = False

        self.image_loaded.emit()
        self.scale_changed.emit(self._scale)
        self.unsaved_changes_changed.emit(self._has_unsaved_changes)
        return True

    def _safe_close_image(self, img: Optional[Image.Image]) -> None:
        """安全地關閉 PIL 圖片實體，忽略任何例外。"""
        if img:
            try:
                img.close()
            except Exception as e:
                logging.debug(f"Error closing image: {e}")

    def set_image(self, pil_image: Image.Image, is_effect_failure: bool = False):
        """更新當前圖片（例如套用濾鏡、復原等操作後）"""
        self.document_version += 1
        self._safe_close_image(self.preview_image)
        self.preview_image = None
        self._safe_close_image(self.image)
        self.image = pil_image

        if not is_effect_failure:
            self.state_id = uuid.uuid4().hex
            self.set_unsaved_changes(True)

        self.image_loaded.emit()

    @property
    def undo_stack(self):
        return [entry.path for entry in self.history.undo]

    @property
    def redo_stack(self):
        return [entry.path for entry in self.history.redo]

    @property
    def display_image(self):
        return self.preview_image if self.preview_image is not None else self.image

    def set_preview(self, image):
        self._safe_close_image(self.preview_image)
        self.preview_image = image
        self.preview_changed.emit()

    def get_original_image(self):
        return self.history.read(self.original_snapshot) if self.original_snapshot else None

    def push_undo(self):
        if self.image is None:
            return False
        try:
            self.history.push(self.image, self.state_id)
            return True
        except Exception as error:
            self.error_occurred.emit("無法儲存復原狀態", str(error))
            return False

    def undo(self, is_effect_failure=False, *, redo=False):
        if self.image is None:
            return False
        try:
            result = self.history.move(self.image, self.state_id, redo=redo, rollback=is_effect_failure)
            if result is None:
                return False
            image, state = result
            self.set_image(image, is_effect_failure=True)
            self.state_id = state
            self._has_unsaved_changes = state != self.saved_state_id
            self.unsaved_changes_changed.emit(self._has_unsaved_changes)
            return True
        except Exception as error:
            self.error_occurred.emit("復原失敗", str(error))
            return False

    def clear(self):
        self.document_version += 1
        self._safe_close_image(self.preview_image)
        self.preview_image = None
        self._safe_close_image(self.image)
        self.image = None
        self.history.clear()
        self.original_snapshot = None
        self.state_id = uuid.uuid4().hex
        self.saved_state_id = self.state_id
        self.current_path = None
        self.current_index = -1
        self._scale = 1.0
        self._has_unsaved_changes = False
        self.image_cleared.emit()
        self.unsaved_changes_changed.emit(False)

    @property
    def image_list(self) -> List[str]:
        """向後相容別名；新程式應使用 media_list。"""
        return self.media_list

    @image_list.setter
    def image_list(self, paths: List[str]) -> None:
        self.media_list = paths

    def set_current_media(self, path: str) -> None:
        """切換至非圖片媒體，清除圖片狀態但保留共用列表。"""
        self.clear()
        self.current_path = path
        self.sync_current_index()

    def update_gallery(self, media_list: List[str]) -> None:
        """更新目前資料夾的媒體列表，並同步目前索引。"""
        self.media_list = media_list
        self.sync_current_index()

    def clear_gallery(self) -> None:
        """清空圖庫列表與索引。"""
        self.media_list = []
        self.current_index = -1

    def sync_current_index(self) -> int:
        """依 current_path 同步 current_index。找不到時回傳 -1。"""
        if not self.current_path:
            self.current_index = -1
            return self.current_index
        try:
            self.current_index = self.media_list.index(self.current_path)
        except ValueError:
            self.current_index = -1
        return self.current_index

    def get_prev_image_path(self) -> Optional[str]:
        """向後相容別名。"""
        return self.get_prev_media_path()

    def get_prev_media_path(self) -> Optional[str]:
        """取得上一個媒體路徑，若不存在則回傳 None。"""
        if self.current_index > 0:
            return self.media_list[self.current_index - 1]
        return None

    def get_next_image_path(self) -> Optional[str]:
        """向後相容別名。"""
        return self.get_next_media_path()

    def get_next_media_path(self) -> Optional[str]:
        """取得下一個媒體路徑，若不存在則回傳 None。"""
        if 0 <= self.current_index < len(self.media_list) - 1:
            return self.media_list[self.current_index + 1]
        return None

    @property
    def has_base_image(self) -> bool:
        """檢查是否有基礎效果圖片（不複製，僅用於判斷）。"""
        return self.image is not None

    def get_base_image_for_effects(self) -> Optional[Image.Image]:
        """獲取用於套用效果的基礎圖片拷貝"""
        if self.image is None:
            return None
        return self.image.copy()
