import logging
from typing import Optional, List
from PyQt6.QtCore import QObject, pyqtSignal
from PIL import Image

class ImageModel(QObject):
    """
    核心圖片資料模型，負責管理圖片狀態（縮放比例、復原堆疊、影像實體等），
    並透過 PyQt Signals 與 UI 層溝通，達到解耦目的。
    """
    
    # --- Signals ---
    image_loaded = pyqtSignal()
    image_cleared = pyqtSignal()
    scale_changed = pyqtSignal(float)
    unsaved_changes_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str, str) # title, message

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.image: Optional[Image.Image] = None
        self.current_path: Optional[str] = None
        self._base_image_for_effects: Optional[Image.Image] = None
        self.image_list: List[str] = []
        self.current_index: int = -1
        
        self.undo_stack: List[Image.Image] = []
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
        if self._has_unsaved_changes != has_changes:
            self._has_unsaved_changes = has_changes
            self.unsaved_changes_changed.emit(self._has_unsaved_changes)

    def load_new_image(self, pil_image: Image.Image, path: str):
        """載入新圖片並重置狀態"""
        self.clear()
        
        self.image = pil_image
        self.current_path = path
        try:
            self._base_image_for_effects = self.image.copy()
        except Exception as e:
            logging.error(f"Copying base image failed: {e}")
            
        self._scale = 1.0
        self._has_unsaved_changes = False
        
        self.image_loaded.emit()
        self.scale_changed.emit(self._scale)
        self.unsaved_changes_changed.emit(self._has_unsaved_changes)

    def set_image(self, pil_image: Image.Image, is_effect_failure: bool = False):
        """更新當前圖片（例如套用濾鏡、復原等操作後）"""
        if self.image:
            try:
                self.image.close()
            except Exception as e:
                logging.warning(f"Error closing previous image: {e}")
                
        self.image = pil_image
        
        # 更新效果基準圖
        if self._base_image_for_effects:
            try:
                self._base_image_for_effects.close()
            except Exception as e:
                pass
        
        try:
            self._base_image_for_effects = self.image.copy()
        except Exception as e:
             logging.error(f"Copying base image failed during set_image: {e}")
             self.error_occurred.emit("圖片處理錯誤", f"無法複製圖片狀態: {e}")
        
        if not is_effect_failure:
             self.set_unsaved_changes(True)
             
        self.image_loaded.emit()

    def push_undo(self):
        """將當前圖片存入復原堆疊"""
        if not self.image:
            return
        try:
            if len(self.undo_stack) >= self.config.MAX_UNDO_STEPS:
                oldest_img = self.undo_stack.pop(0)
                try:
                    oldest_img.close()
                except Exception: pass
                
            self.undo_stack.append(self.image.copy())
        except Exception as e:
            logging.error(f"壓入復原堆疊時出錯: {e}")
            self.error_occurred.emit("錯誤", "無法儲存復原狀態，可能是記憶體不足。")

    def undo(self, is_effect_failure: bool = False) -> bool:
        """執行復原操作"""
        if not self.undo_stack:
            return False
            
        previous_image = self.undo_stack.pop()
        self.set_image(previous_image, is_effect_failure)
        return True

    def clear(self):
        """清理所有資源"""
        if self.image:
            try: self.image.close()
            except Exception: pass
            self.image = None
            
        if self._base_image_for_effects:
            try: self._base_image_for_effects.close()
            except Exception: pass
            self._base_image_for_effects = None
            
        for img in self.undo_stack:
            try: img.close()
            except Exception: pass
        self.undo_stack.clear()
        self.current_path = None
        self.current_index = -1
        self._scale = 1.0
        self._has_unsaved_changes = False
        
        self.image_cleared.emit()

    def update_gallery(self, image_list: List[str]) -> None:
        """更新目前資料夾的圖片列表，並同步目前索引。"""
        self.image_list = image_list
        self.sync_current_index()

    def clear_gallery(self) -> None:
        """清空圖庫列表與索引。"""
        self.image_list = []
        self.current_index = -1

    def sync_current_index(self) -> int:
        """依 current_path 同步 current_index。找不到時回傳 -1。"""
        if not self.current_path:
            self.current_index = -1
            return self.current_index
        try:
            self.current_index = self.image_list.index(self.current_path)
        except ValueError:
            self.current_index = -1
        return self.current_index

    def get_prev_image_path(self) -> Optional[str]:
        """取得上一張圖片路徑，若不存在則回傳 None。"""
        if self.current_index > 0:
            return self.image_list[self.current_index - 1]
        return None

    def get_next_image_path(self) -> Optional[str]:
        """取得下一張圖片路徑，若不存在則回傳 None。"""
        if 0 <= self.current_index < len(self.image_list) - 1:
            return self.image_list[self.current_index + 1]
        return None

    def get_base_image_for_effects(self) -> Optional[Image.Image]:
        """獲取用於套用效果的基礎圖片拷貝"""
        if not self._base_image_for_effects:
            return None
        return self._base_image_for_effects.copy()
