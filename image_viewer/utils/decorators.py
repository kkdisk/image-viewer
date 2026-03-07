from functools import wraps
from typing import Any, Callable
from PyQt6.QtWidgets import QMessageBox

def requires_image(func: Callable) -> Callable:
    """裝飾器，檢查 self.model.image 是否存在。
    支援 ImageEditorWindow (self.model.image) 和 UIManager (self.win.model.image)。
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        # 優先檢查 self.model.image，若無則檢查 self.win.model.image (for UIManager)
        has_image = False
        parent = self
        
        if hasattr(self, 'model') and getattr(self.model, 'image', None) is not None:
            has_image = True
        elif hasattr(self, 'win') and hasattr(self.win, 'model') and getattr(self.win.model, 'image', None) is not None:
            has_image = True
            parent = self.win
            
        if not has_image:
            QMessageBox.information(parent, "操作提示", "請先載入圖片。")
            return None
        return func(self, *args, **kwargs)
    return wrapper
