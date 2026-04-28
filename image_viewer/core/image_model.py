import os
import tempfile
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
        
        self.undo_stack: List[str] = []  # 現在儲存暫存檔案路徑
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
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

    def _safe_close_image(self, img: Optional[Image.Image]) -> None:
        """安全地關閉 PIL 圖片實體，忽略任何例外。"""
        if img:
            try:
                img.close()
            except Exception as e:
                logging.debug(f"Error closing image: {e}")

    def set_image(self, pil_image: Image.Image, is_effect_failure: bool = False):
        """更新當前圖片（例如套用濾鏡、復原等操作後）"""
        self._safe_close_image(self.image)
        self.image = pil_image
        
        # 更新效果基準圖
        self._safe_close_image(self._base_image_for_effects)
        
        try:
            self._base_image_for_effects = self.image.copy()
        except Exception as e:
             logging.error(f"Copying base image failed during set_image: {e}")
             self.error_occurred.emit("圖片處理錯誤", f"無法複製圖片狀態: {e}")
        
        if not is_effect_failure:
             self.set_unsaved_changes(True)
             
        self.image_loaded.emit()

    def push_undo(self):
        """將當前圖片存入硬碟暫存區，作為復原點"""
        if not self.image:
            return
        try:
            if not self._temp_dir:
                self._temp_dir = tempfile.TemporaryDirectory(prefix="image_viewer_undo_")

            # 限制堆疊大小
            if len(self.undo_stack) >= self.config.MAX_UNDO_STEPS:
                oldest_path = self.undo_stack.pop(0)
                if os.path.exists(oldest_path):
                    try: os.remove(oldest_path)
                    except Exception: pass
            
            # 建立暫存檔名 (使用索引確保唯一性)
            temp_filename = f"step_{len(self.undo_stack)}_{id(self.image)}.png"
            temp_path = os.path.join(self._temp_dir.name, temp_filename)
            
            # 將目前影像存入暫存檔 (使用無損壓縮或直接存儲像素)
            self.image.save(temp_path, "PNG")
            self.undo_stack.append(temp_path)
            
            logging.debug(f"Undo point saved to disk: {temp_path}")
        except Exception as e:
            logging.error(f"儲存復原點至硬碟時出錯: {e}")
            self.error_occurred.emit("錯誤", "無法儲存復原狀態，磁碟空間可能不足。")

    def undo(self, is_effect_failure: bool = False) -> bool:
        """從硬碟讀回影像執行復原操作"""
        if not self.undo_stack:
            return False
            
        temp_path = self.undo_stack.pop()
        try:
            with Image.open(temp_path) as img:
                previous_image = img.copy() # 建立獨立副本，因為原本的會被 close
            
            self.set_image(previous_image, is_effect_failure)
            
            # 使用後刪除暫存檔
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return True
        except Exception as e:
            logging.error(f"從暫存檔復原影像時出錯: {e}")
            self.error_occurred.emit("復原失敗", f"無法從硬碟讀取復原狀態: {e}")
            return False

    def clear(self):
        """清理所有資源"""
        self._safe_close_image(self.image)
        self.image = None
            
        self._safe_close_image(self._base_image_for_effects)
        self._base_image_for_effects = None
            
        for path in self.undo_stack:
            if os.path.exists(path):
                try: os.remove(path)
                except Exception: pass
        self.undo_stack.clear()

        if self._temp_dir:
            try: self._temp_dir.cleanup()
            except Exception: pass
            self._temp_dir = None

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

    @property
    def has_base_image(self) -> bool:
        """檢查是否有基礎效果圖片（不複製，僅用於判斷）。"""
        return self._base_image_for_effects is not None

    def get_base_image_for_effects(self) -> Optional[Image.Image]:
        """獲取用於套用效果的基礎圖片拷貝"""
        if not self._base_image_for_effects:
            return None
        return self._base_image_for_effects.copy()
