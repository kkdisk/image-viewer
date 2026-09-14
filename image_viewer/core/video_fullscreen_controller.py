"""影片全螢幕模式與控制列自動隱藏行為。"""

from typing import Dict, Iterable

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QDockWidget, QToolBar, QWidget


class VideoFullscreenController(QObject):
    """管理全螢幕 chrome、控制列與滑鼠游標狀態。"""

    def __init__(
        self,
        window,
        video_widget: QWidget,
        video_page: QWidget,
        controls: QWidget,
        hide_delay_ms: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.window = window
        self.video_widget = video_widget
        self.video_page = video_page
        self.controls = controls
        self.hide_delay_ms = hide_delay_ms
        self.is_active = False
        self._was_maximized = False
        self._chrome_visibility: Dict[QWidget, bool] = {}
        self._menu_was_visible = True
        self._status_was_visible = True

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_controls)

        watched_widgets = [window, video_page, video_widget, controls]
        watched_widgets.extend(controls.findChildren(QWidget))
        for widget in watched_widgets:
            widget.installEventFilter(self)
            widget.setMouseTracking(True)

        if hasattr(window, "video_position_slider"):
            window.video_position_slider.sliderPressed.connect(
                self._hide_timer.stop
            )
            window.video_position_slider.sliderReleased.connect(
                self.show_controls
            )

    def toggle(self) -> None:
        if self.is_active:
            self.exit()
        else:
            self.enter()

    def enter(self) -> None:
        if self.is_active or not getattr(self.window, "is_video_mode", False):
            return
        self.is_active = True
        self._was_maximized = self.window.isMaximized()
        self._menu_was_visible = self.window.menuBar().isVisible()
        self._status_was_visible = self.window.statusBar().isVisible()
        self._chrome_visibility = {
            widget: widget.isVisible()
            for widget in self._chrome_widgets()
        }

        self.window.menuBar().hide()
        self.window.statusBar().hide()
        for widget in self._chrome_visibility:
            widget.hide()
        self.window.showFullScreen()
        self.show_controls()

    def exit(self) -> None:
        if not self.is_active:
            return
        self.is_active = False
        self._hide_timer.stop()
        self.controls.show()
        self.video_widget.unsetCursor()
        self.window.showNormal()
        if self._was_maximized:
            self.window.showMaximized()

        self.window.menuBar().setVisible(self._menu_was_visible)
        self.window.statusBar().setVisible(self._status_was_visible)
        for widget, was_visible in self._chrome_visibility.items():
            widget.setVisible(was_visible)
        self._chrome_visibility.clear()

    def show_controls(self) -> None:
        if not self.is_active:
            return
        self.controls.show()
        self.video_widget.unsetCursor()
        if not self.window.video_position_slider.isSliderDown():
            self._hide_timer.start(self.hide_delay_ms)

    def hide_controls(self) -> None:
        if not self.is_active or self.window.video_position_slider.isSliderDown():
            return
        self.controls.hide()
        self.video_widget.setCursor(Qt.CursorShape.BlankCursor)

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        if (
            source is self.video_widget
            and event.type() == QEvent.Type.MouseButtonDblClick
        ):
            self.toggle()
            return True

        if self.is_active and event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
        ):
            self.show_controls()
        if (
            self.is_active
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.exit()
            return True
        return super().eventFilter(source, event)

    def _chrome_widgets(self) -> Iterable[QWidget]:
        yield from self.window.findChildren(QToolBar)
        yield from self.window.findChildren(QDockWidget)
