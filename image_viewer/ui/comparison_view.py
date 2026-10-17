"""雙圖比較的顯示與正規化視圖同步。"""

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QSplitter, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QCheckBox, QLabel, QSizePolicy,
)


class ImageViewport(QGraphicsView):
    view_changed = pyqtSignal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setScene(QGraphicsScene(self))
        self.item = self.scene().addPixmap(QPixmap())
        self._updating = False
        self.fit_mode = True
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        tile = QPixmap(24, 24)
        tile.fill(QColor("#dddddd"))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 12, 12, QColor("#aaaaaa"))
        painter.fillRect(12, 12, 12, 12, QColor("#aaaaaa"))
        painter.end()
        self.setBackgroundBrush(QBrush(tile))

    def state(self):
        rect = self.sceneRect()
        center = self.mapToScene(self.viewport().rect().center())
        return (self.transform().m11(), center.x() / max(1, rect.width()), center.y() / max(1, rect.height()))

    def set_state(self, scale, x=0.5, y=0.5):
        self._updating = True
        try:
            self.fit_mode = False
            self.setTransform(QTransform.fromScale(max(0.01, min(10.0, scale)), max(0.01, min(10.0, scale))))
            rect = self.sceneRect()
            self.centerOn(QPointF(rect.width() * max(0, min(1, x)), rect.height() * max(0, min(1, y))))
        finally:
            self._updating = False

    def set_image(self, image):
        state = self.state()
        fit = self.fit_mode
        self._updating = True
        self.item.setPixmap(QPixmap.fromImage(ImageQt(image).copy()) if image is not None else QPixmap())
        self.setSceneRect(self.item.boundingRect())
        self._updating = False
        if fit:
            self.fit_image()
        else:
            self.set_state(*state)

    def fit_image(self):
        self._updating = True
        self.fit_mode = True
        if not self.sceneRect().isEmpty():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._updating = False

    def _notify(self):
        if not getattr(self, "_updating", True):
            self.view_changed.emit(*self.state())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.fit_mode = False
            self._notify()

    def wheelEvent(self, event):
        scale, x, y = self.state()
        self.set_state(scale * (1.25 if event.angleDelta().y() > 0 else 0.8), x, y)
        self._notify()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit_image()


class ComparisonView(QWidget):
    reference_requested = pyqtSignal()
    original_requested = pyqtSignal()
    status_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.left = ImageViewport()
        self.right = ImageViewport()
        self.left_label = QLabel("原圖（唯讀）")
        self.right_label = QLabel("目前結果")
        for label in (self.left_label, self.right_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        for title, callback in [("選擇參考圖片", self.reference_requested.emit),
                                ("恢復原圖參考", self.original_requested.emit),
                                ("符合視窗", self.fit_images), ("100%", self.actual_size)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            tools.addWidget(button)
        self.sync = QCheckBox("同步縮放與平移")
        self.sync.setChecked(True)
        self.sync.toggled.connect(self._sync_enabled)
        tools.addWidget(self.sync)
        layout.addLayout(tools)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        for label, viewport in [(self.left_label, self.left), (self.right_label, self.right)]:
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.addWidget(label)
            column.addWidget(viewport)
            splitter.addWidget(panel)
        splitter.setSizes([500, 500])
        layout.addWidget(splitter)
        self.left.view_changed.connect(lambda *state: self._sync_to(self.right, state))
        self.right.view_changed.connect(lambda *state: self._sync_to(self.left, state))

    def _sync_to(self, target, state):
        if self.sync.isChecked():
            target.set_state(*state)

    def _sync_enabled(self, enabled):
        if enabled:
            self.left.set_state(*self.right.state())

    def fit_images(self):
        self.left.fit_image()
        self.right.fit_image()
        self.status_changed.emit()

    def actual_size(self):
        self.left.set_state(1.0)
        self.right.set_state(1.0)
        self.right._notify()
