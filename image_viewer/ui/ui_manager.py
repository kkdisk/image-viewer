from PIL import Image, ImageOps, ImageFilter

from PyQt6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QWidget, QVBoxLayout
from PyQt6.QtWidgets import QStyle, QDoubleSpinBox, QTreeWidget, QDockWidget
from PyQt6.QtWidgets import QListWidget, QFormLayout, QLineEdit, QGroupBox, QPushButton
from PyQt6.QtWidgets import QSlider, QHBoxLayout, QMessageBox, QApplication

from PyQt6.QtGui import QIcon, QKeySequence, QAction
from PyQt6.QtCore import Qt, QSize

from image_viewer.config import Config, LANCZOS_RESAMPLE
from image_viewer.ui.widgets import HistogramWidget, ResizeDialog
from image_viewer.utils.decorators import requires_image

class UIManager:
    def __init__(self, main_window, config: Config): 
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
        has_image = hasattr(self.win, 'model') and self.win.model.image is not None
        self.win.startup_container.setVisible(not has_image)
        actions_to_toggle = [self.win.save_action, self.win.save_as_action, self.win.zoom_in_action, self.win.zoom_out_action, self.win.fit_to_window_action, self.win.resize_action, self.win.rotate_left_action, self.win.rotate_right_action, self.win.flip_horizontal_action, self.win.flip_vertical_action, self.win.toggle_magnifier_action]
        for action in actions_to_toggle: action.setEnabled(has_image)
        
        can_undo = hasattr(self.win, 'model') and bool(self.win.model.undo_stack)
        self.win.undo_action.setEnabled(can_undo)
        self.win.prev_action.setEnabled(
            has_image and self.win.model.get_prev_image_path() is not None
        )
        self.win.next_action.setEnabled(
            has_image and self.win.model.get_next_image_path() is not None
        )
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

    @requires_image
    def _open_resize_dialog(self, main_window=None):
        dialog = ResizeDialog(QSize(self.win.model.image.width, self.win.model.image.height), self.win)
        if new_size := dialog.get_dimensions():
            self.win._apply_effect(lambda img: img.resize((new_size.width(), new_size.height()), LANCZOS_RESAMPLE))
