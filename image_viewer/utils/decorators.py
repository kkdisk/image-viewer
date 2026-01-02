from functools import wraps
from typing import Any, Callable
from PyQt6.QtWidgets import QMessageBox

def requires_image(func: Callable) -> Callable:
    """裝飾器，檢查 self.image 是否存在。
    支援 ImageEditorWindow (self.image) 和 UIManager (self.win.image)。
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        # 優先檢查 self.image，若無則檢查 self.win.image (for UIManager)
        image = getattr(self, 'image', None)
        parent = self
        if image is None and hasattr(self, 'win'):
            image = getattr(self.win, 'image', None)
            parent = self.win
        
        if image is None:
            QMessageBox.information(parent, "操作提示", "請先載入圖片。")
            return None
        return func(self, *args, **kwargs)
    return wrapper
