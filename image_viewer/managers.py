# ==============================================================================
# managers.py - 管理器類別
# ==============================================================================
"""
包含資源、UI、主題管理器：ResourceManager、UIManager、ThemeManager
"""

import sys
import os
import logging
from typing import Optional, Dict, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication, QLabel, QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QFormLayout, QDockWidget, QSizePolicy, QListWidget,
    QPushButton, QSlider, QGroupBox, QLineEdit, QDoubleSpinBox, QStyle
)
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPalette, QColor
from PyQt6.QtCore import Qt, QSize

from PIL import Image, ImageOps, ImageFilter

from .config import Config, LANCZOS_RESAMPLE
from .widgets import HistogramWidget, ResizeDialog

if TYPE_CHECKING:
    from .main_window import ImageEditorWindow


# ==============================================================================
# ResourceManager - 資源管理器
# ==============================================================================
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


# ==============================================================================
# UIManager - UI 管理器
# ==============================================================================
class UIManager:
    def __init__(self, main_window: 'ImageEditorWindow', config: Config): 
        self.win = main_window
        self.config = config 

    def setup_ui(self):
        self.win.image_label = QLabel()
        self.win.image_label.setObjectName("imageLabel")
        self.win.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.win.image_label.setMouseTracking(True)
        self.win.image_label.setToolTip(
            "滑鼠滾輪: 縮放\n"
            "左鍵拖曳: 平移\n"
            "Ctrl+M: 開啟/關閉放大鏡"
        )
        self.win.scroll_area = QScrollArea()
        self.win.scroll_area.setObjectName("scrollArea")
        self.win.scroll_area.setWidget(self.win.image_label)
        self.win.scroll_area.setWidgetResizable(True)
        self.win.setCentralWidget(self.win.scroll_area)
        self.win.startup_container = QWidget(self.win.scroll_area.viewport())
        startup_layout = QVBoxLayout(self.win.startup_container)
        startup_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        startup_layout.setContentsMargins(0,0,0,0)
        self.win.startup_label = QLabel("拖曳圖片至此，或點擊左上角「開啟」")
        self.win.startup_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win.startup_label.setStyleSheet("""
            color: #888;
            font-size: 20px;
            padding: 20px;
            background-color: transparent;
        """)
        startup_layout.addWidget(self.win.startup_label)
        self.win.startup_container.setStyleSheet("background-color: transparent;")
        self.win.startup_container.lower()
        self.win.startup_container.setVisible(True)
        self.win.startup_container.setGeometry(self.win.scroll_area.viewport().rect())

    def create_actions(self):
        self.icon_map = {
            "document-open": QStyle.StandardPixmap.SP_DialogOpenButton,
            "document-save": QStyle.StandardPixmap.SP_DialogSaveButton,
            "document-save-as": QStyle.StandardPixmap.SP_DialogSaveButton,
            "application-exit": QStyle.StandardPixmap.SP_DialogCloseButton,
            "edit-undo": QStyle.StandardPixmap.SP_ArrowBack,
            "zoom-in": QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton,
            "zoom-out": QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton,
            "zoom-fit-best": QStyle.StandardPixmap.SP_DesktopIcon,
            "zoom-original": QStyle.StandardPixmap.SP_ComputerIcon,
            "go-previous": QStyle.StandardPixmap.SP_ArrowBack,
            "go-next": QStyle.StandardPixmap.SP_ArrowForward,
            "object-rotate-left": QStyle.StandardPixmap.SP_ArrowLeft,
            "object-rotate-right": QStyle.StandardPixmap.SP_ArrowRight,
            "help-about": QStyle.StandardPixmap.SP_MessageBoxInformation,
        }
        self.win.open_action = self._create_action("開啟...", "document-open", QKeySequence.StandardKey.Open, self.win.open_file_dialog)
        self.win.save_action = self._create_action("儲存", "document-save", QKeySequence.StandardKey.Save, self.win.save_image)
        self.win.save_as_action = self._create_action("另存為...", "document-save-as", QKeySequence.StandardKey.SaveAs, self.win.save_image_as)
        self.win.exit_action = self._create_action("離開", "application-exit", None, self.win.close)
        self.win.undo_action = self._create_action("復原", "edit-undo", QKeySequence.StandardKey.Undo, self.win.undo)
        self.win.zoom_in_action = self._create_action("放大", "zoom-in", QKeySequence.StandardKey.ZoomIn, self.win.zoom_in)
        self.win.zoom_out_action = self._create_action("縮小", "zoom-out", QKeySequence.StandardKey.ZoomOut, self.win.zoom_out)
        self.win.fit_to_window_action = self._create_action("最適化顯示", "zoom-fit-best", None, self.win.toggle_fit_to_window_mode, is_checkable=True, checked=True)
        self.win.toggle_magnifier_action = self._create_action("放大鏡", "zoom-original", "Ctrl+M", self.win.toggle_magnifier, is_checkable=True)
        
        self.win.toggle_theme_action = self._create_action("切換主題", "preferences-desktop-theme", "Ctrl+T", self.win.theme_manager.toggle_theme)
        
        self.win.prev_action = self._create_action("上一張", "go-previous", Qt.Key.Key_Left, self.win.prev_image)
        self.win.next_action = self._create_action("下一張", "go-next", Qt.Key.Key_Right, self.win.next_image)
        self.win.resize_action = self._create_action("調整尺寸...", "transform-scale", None, lambda: self._open_resize_dialog())
        self.win.rotate_left_action = self._create_action("向左旋轉", "object-rotate-left", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.ROTATE_90)))
        self.win.rotate_right_action = self._create_action("向右旋轉", "object-rotate-right", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.ROTATE_270)))
        self.win.flip_horizontal_action = self._create_action("水平翻轉", "object-flip-horizontal", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))
        self.win.flip_vertical_action = self._create_action("垂直翻轉", "object-flip-vertical", None, lambda: self.win._apply_effect(lambda img: img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)))
        self.win.about_action = self._create_action("關於", "help-about", None, self.win._show_about_dialog)

    def create_menus(self):
        mb = self.win.menuBar()
        mb.addMenu("&檔案").addActions([self.win.open_action, self.win.save_action, self.win.save_as_action, self.win.exit_action])
        edit_menu = mb.addMenu("&編輯"); edit_menu.addAction(self.win.undo_action); edit_menu.addSeparator()
        transform_menu = edit_menu.addMenu("變換"); transform_menu.addActions([self.win.resize_action, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action])
        view_menu = mb.addMenu("&檢視"); view_menu.addActions([self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action]); view_menu.addSeparator()
        view_menu.addAction(self.win.toggle_magnifier_action); view_menu.addSeparator()
        view_menu.addActions([self.win.exif_dock.toggleViewAction(), self.win.effects_dock.toggleViewAction(), self.win.filmstrip_dock.toggleViewAction(), self.win.histogram_dock.toggleViewAction()])
        view_menu.addSeparator(); view_menu.addAction(self.win.toggle_theme_action)
        help_menu = mb.addMenu("&說明")
        help_menu.addAction(self.win.about_action)

    def create_toolbars(self):
        self._create_toolbar("檔案", [self.win.open_action, self.win.save_action])
        view_tb = self._create_toolbar("檢視", [self.win.prev_action, self.win.next_action, None, self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action, None, self.win.toggle_magnifier_action])
        self.win.magnifier_factor_spinbox = QDoubleSpinBox()
        self.win.magnifier_factor_spinbox.setRange(*self.config.MAGNIFIER_FACTOR_RANGE)
        self.win.magnifier_factor_spinbox.setSingleStep(0.5)
        self.win.magnifier_factor_spinbox.setValue(self.win.magnifier_factor)
        self.win.magnifier_factor_spinbox.setPrefix("放大: ")
        self.win.magnifier_factor_spinbox.setSuffix("x")
        self.win.magnifier_factor_spinbox.valueChanged.connect(lambda v: setattr(self.win, 'magnifier_factor', v))
        view_tb.addWidget(self.win.magnifier_factor_spinbox)
        self._create_toolbar("變換", [self.win.undo_action, None, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action])

    def create_docks(self):
        self.win.exif_tree = QTreeWidget(); self.win.exif_tree.setHeaderLabels(["標籤", "值"]); self.win.exif_tree.setColumnWidth(0, 150)
        self.win.exif_dock = self._create_dock("EXIF 資訊", Qt.DockWidgetArea.RightDockWidgetArea, self.win.exif_tree, visible=False)
        self.win.effects_dock = self._create_dock("效果與調整", Qt.DockWidgetArea.RightDockWidgetArea, self._create_effects_panel())
        
        self.win.histogram_widget = HistogramWidget(self.config)
        self.win.histogram_dock = self._create_dock("直方圖", Qt.DockWidgetArea.RightDockWidgetArea, self.win.histogram_widget, visible=False)
        
        self.win.filmstrip_widget = QListWidget()
        self.win.filmstrip_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.win.filmstrip_widget.setFlow(QListWidget.Flow.LeftToRight)
        self.win.filmstrip_widget.setMovement(QListWidget.Movement.Static)
        thumbnail_qsize = QSize(*self.config.THUMBNAIL_SIZE)
        self.win.filmstrip_widget.setIconSize(thumbnail_qsize)
        self.win.filmstrip_widget.setSpacing(10)
        self.win.filmstrip_widget.setGridSize(QSize(thumbnail_qsize.width() + 12, thumbnail_qsize.height() + 12))
        self.win.filmstrip_widget.setWrapping(False)
        self.win.filmstrip_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.win.filmstrip_widget.currentItemChanged.connect(self.win.on_filmstrip_item_selected)
        self.win.filmstrip_dock = self._create_dock("預覽", Qt.DockWidgetArea.BottomDockWidgetArea, self.win.filmstrip_widget)
        self.win.filmstrip_dock.setFixedHeight(160)

    def update_ui_state(self):
        has_image = self.win.image is not None
        self.win.startup_container.setVisible(not has_image)
        actions_to_toggle = [self.win.save_action, self.win.save_as_action, self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action, self.win.resize_action, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action, self.win.toggle_magnifier_action]
        for action in actions_to_toggle: action.setEnabled(has_image)
        self.win.undo_action.setEnabled(bool(self.win.undo_stack))
        self.win.prev_action.setEnabled(has_image and self.win.current_index > 0)
        self.win.next_action.setEnabled(has_image and self.win.current_index < len(self.win.image_list) - 1)
        if hasattr(self.win, 'effects_dock'): self.win.effects_dock.widget().setEnabled(has_image)
        if hasattr(self.win, 'magnifier_factor_spinbox'): self.win.magnifier_factor_spinbox.setEnabled(has_image and self.win.magnifier_enabled)

    def reset_adjustment_sliders(self):
        if not hasattr(self.win, 'temp_slider'):
            return
        sliders = [self.win.temp_slider, self.win.tint_slider, self.win.brightness_slider, self.win.contrast_slider, self.win.saturation_slider]
        for slider in sliders: slider.blockSignals(True)
        
        adj_default = self.config.ADJUSTMENT_DEFAULT
        self.win.temp_slider.setValue(0)
        self.win.tint_slider.setValue(0)
        self.win.brightness_slider.setValue(adj_default)
        self.win.contrast_slider.setValue(adj_default)
        self.win.saturation_slider.setValue(adj_default)
        
        if hasattr(self.win, 'temp_value_label'): self.win.temp_value_label.setText("0")
        if hasattr(self.win, 'tint_value_label'): self.win.tint_value_label.setText("0")
        if hasattr(self.win, 'brightness_value_label'): self.win.brightness_value_label.setText(f"{adj_default}%")
        if hasattr(self.win, 'contrast_value_label'): self.win.contrast_value_label.setText(f"{adj_default}%")
        if hasattr(self.win, 'saturation_value_label'): self.win.saturation_value_label.setText(f"{adj_default}%")
        
        for slider in sliders: slider.blockSignals(False)

    def _create_action(self, text, icon_name, shortcut, slot, is_checkable=False, checked=False):
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull() and icon_name in self.icon_map:
            icon = self.win.style().standardIcon(self.icon_map[icon_name])
        action = QAction(icon, text, self.win)
        if shortcut: action.setShortcut(shortcut)
        if slot: action.triggered.connect(slot)
        if is_checkable: action.setCheckable(True); action.setChecked(checked)
        return action
        
    def _create_toolbar(self, title, actions):
        toolbar = self.win.addToolBar(title); toolbar.setIconSize(QSize(22, 22))
        for action in actions:
            if action: toolbar.addAction(action)
            else: toolbar.addSeparator()
        return toolbar
        
    def _create_dock(self, title, area, widget, visible=True):
        dock = QDockWidget(title, self.win); dock.setWidget(widget)
        self.win.addDockWidget(area, dock); dock.setVisible(visible)
        return dock
        
    def _create_effects_panel(self) -> QWidget:
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        zoom_layout = QFormLayout(); self.win.zoom_entry = QLineEdit()
        self.win.zoom_entry.setFixedWidth(70)
        self.win.zoom_entry.returnPressed.connect(self.win._on_zoom_entry_submit)
        zoom_layout.addRow("指定縮放:", self.win.zoom_entry); layout.addLayout(zoom_layout)

        self.win.fine_tune_group = self._create_slider_group(
            "細緻調整", 
            [("亮度", "brightness", self.win._on_fine_tune_slider_released), 
             ("對比", "contrast", self.win._on_fine_tune_slider_released), 
             ("飽和", "saturation", self.win._on_fine_tune_slider_released)], 
            range=self.config.ADJUSTMENT_RANGE, 
            default=self.config.ADJUSTMENT_DEFAULT, 
            suffix="%"
        )
        layout.addWidget(self.win.fine_tune_group)

        self.win.white_balance_group = self._create_slider_group(
            "白平衡", 
            [("色溫", "temp", self.win._on_white_balance_slider_released), 
             ("色調", "tint", self.win._on_white_balance_slider_released)], 
            range=self.config.WHITE_BALANCE_TEMP_RANGE, 
            default=0
        )
        layout.addWidget(self.win.white_balance_group)

        filters_group = QGroupBox("濾鏡"); filters_layout = QVBoxLayout(filters_group)
        effect_configs = [
            {"name": "反轉圖片", "func": lambda img: ImageOps.invert(img.convert("RGB")).convert("RGBA")},
            {"name": "轉為灰階", "func": lambda img: img.convert("L").convert("RGBA")},
            {"name": "模糊", "func": lambda img: img.filter(ImageFilter.GaussianBlur(radius=self.config.BLUR_RADIUS))},
            {"name": "銳化", "func": lambda img: img.filter(ImageFilter.SHARPEN)},
            {"name": "懷舊", "func": lambda img: ImageOps.colorize(img.convert("L"), "#704214", "#C0A080").convert("RGBA")}
        ]
        for config in effect_configs:
            btn = QPushButton(config["name"])
            btn.clicked.connect(lambda _, f=config["func"]: self.win._apply_effect(f))
            filters_layout.addWidget(btn)
        layout.addWidget(filters_group)
        return panel
        
    def _create_slider_group(self, title, sliders_config, range, default, suffix=""):
        group_box = QGroupBox(title); group_layout = QFormLayout(group_box)
        for label, name, slot in sliders_config:
            slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(*range); slider.setValue(default)
            slider.sliderReleased.connect(slot)
            value_label = QLabel(f"{default}{suffix}")
            value_label.setFixedWidth(40)
            slider.valueChanged.connect(lambda v, lbl=value_label, s=suffix: lbl.setText(f"{v}{s}"))
            row_layout = QHBoxLayout(); row_layout.addWidget(slider); row_layout.addWidget(value_label)
            group_layout.addRow(f"{label}:", row_layout)
            setattr(self.win, f"{name}_slider", slider); setattr(self.win, f"{name}_value_label", value_label)
        return group_box

    def _open_resize_dialog(self):
        if not self.win.image: return
        dialog = ResizeDialog(QSize(self.win.image.width, self.win.image.height), self.win)
        if new_size := dialog.get_dimensions():
            self.win._apply_effect(lambda img: img.resize((new_size.width(), new_size.height()), LANCZOS_RESAMPLE))


# ==============================================================================
# ThemeManager - 主題管理器
# ==============================================================================
class ThemeManager:
    def __init__(self, app: QApplication): 
        self.app = app
        self.original_palette = app.style().standardPalette()
        self._fallback_dark_stylesheet = self._get_fallback_stylesheet()
        self.themes = ["light", "dark"]
        self.current_theme_name = self.themes[0] 

    def apply_theme(self, theme_name: str):
        """套用指定名稱的主題"""
        if theme_name not in self.themes:
            logging.warning(f"未知的主題: {theme_name}。退回至 'light'。")
            theme_name = "light"
            
        self.current_theme_name = theme_name
        
        if theme_name == "dark":
            self._apply_dark_palette()
            stylesheet = self._load_stylesheet_from_file("dark_theme.qss")
            if stylesheet is None:
                logging.warning("dark_theme.qss 載入失敗，使用內嵌備份樣式。")
                stylesheet = self._fallback_dark_stylesheet
            self.app.setStyleSheet(stylesheet)
            
        elif theme_name == "light":
            self.app.setPalette(self.original_palette)
            self.app.setStyleSheet("")
            
        logging.info(f"已切換主題至: {theme_name}")

    def toggle_theme(self):
        """循環切換到下一個可用的主題"""
        try:
            current_index = self.themes.index(self.current_theme_name)
        except ValueError:
            current_index = 0
            
        next_index = (current_index + 1) % len(self.themes)
        next_theme = self.themes[next_index]
        
        self.apply_theme(next_theme)

    def _apply_dark_palette(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(37, 37, 37))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        self.app.setPalette(dark_palette)

    def _load_stylesheet_from_file(self, file_path: str) -> Optional[str]:
        """嘗試從檔案讀取 QSS 字串"""
        try:
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            # 往上一層找 dark_theme.qss
            full_path = os.path.join(os.path.dirname(base_path), file_path)
            if not os.path.exists(full_path):
                full_path = os.path.join(base_path, file_path)

            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logging.warning(f"樣式表檔案未找到: {file_path}")
            return None
        except Exception as e:
            logging.error(f"讀取樣式表時發生錯誤: {e}", exc_info=True)
            return None

    def _get_fallback_stylesheet(self) -> str:
        """返回內嵌的備份 QSS 樣式表"""
        return """
        /* === General === */
        QWidget {
            color: #dcdcdc;
            font-family: 'Segoe UI', 'Microsoft JhengHei', 'Helvetica', sans-serif;
        }
        QMainWindow, QDialog {
            background-color: #252525;
        }
        QScrollArea#scrollArea { border: none; background-color: #1e1e1e; }
        QLabel#imageLabel { background-color: #1e1e1e; }
        QDockWidget::title { background-color: #333333; padding: 8px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }
        QDockWidget > QWidget { border: 1px solid #3c3c3c; border-top: none; }
        QTreeWidget, QListWidget { background-color: #2c2c2c; border: 1px solid #3c3c3c; padding: 5px; border-radius: 4px; }
        QListWidget::item { border-radius: 4px; padding: 4px; }
        QListWidget::item:hover { background-color: #383838; }
        QListWidget::item:selected { background-color: rgba(0, 120, 215, 0.5); border: 1px solid #0078d7; color: #ffffff; }
        QHeaderView::section { background-color: #383838; padding: 6px; border: none; border-bottom: 1px solid #454545; }
        QPushButton { background-color: #3e3e3e; border: 1px solid #555555; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
        QPushButton:hover { background-color: #4a4a4a; border-color: #6a6a6a; }
        QPushButton:pressed { background-color: #333333; }
        QPushButton:disabled { background-color: #303030; color: #777777; border-color: #444444; }
        QSlider::groove:horizontal { height: 4px; background: #444444; margin: 2px 0; border-radius: 2px; }
        QSlider::handle:horizontal { background: #0078d7; border: 1px solid #0078d7; width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; }
        QGroupBox { border: 1px solid #3c3c3c; border-radius: 6px; margin-top: 1ex; font-weight: bold; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
        QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #333333; padding: 6px; border: 1px solid #444444; border-radius: 4px; }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #0078d7; }
        QToolBar { background-color: #2d2d2d; border: none; padding: 4px; spacing: 6px; }
        QStatusBar { background-color: #2d2d2d; border-top: 1px solid #3c3c3c; }
        QStatusBar QProgressBar { background-color: #3e3e3e; border: 1px solid #555; border-radius: 4px; text-align: center; color: #dcdcdc; }
        QStatusBar QProgressBar::chunk { background-color: #0078d7; border-radius: 4px; }
        QMenuBar { background-color: #2d2d2d; }
        QMenuBar::item:selected { background-color: #3e3e3e; }
        QMenu { background-color: #2c2c2c; border: 1px solid #444444; padding: 4px; }
        QMenu::item:selected { background-color: #0078d7; }
        QScrollBar:vertical { border: none; background: #2c2c2c; width: 12px; margin: 0px 0px 0px 0px; }
        QScrollBar:horizontal { border: none; background: #2c2c2c; height: 12px; margin: 0px 0px 0px 0px; }
        QScrollBar::handle:vertical { background: #555555; min-height: 25px; border-radius: 6px; }
        QScrollBar::handle:horizontal { background: #555555; min-width: 25px; border-radius: 6px; }
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #6a6a6a; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
        QToolTip { background-color: #1e1e1e; color: #dcdcdc; border: 1px solid #3c3c3c; padding: 5px; border-radius: 4px; }
        """
