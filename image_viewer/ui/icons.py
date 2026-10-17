"""以目前主題色繪製左右分割的雙圖比較圖示。"""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QIcon, QIconEngine, QPalette, QPen
from PyQt6.QtWidgets import QApplication


class ComparisonIconEngine(QIconEngine):
    def clone(self):
        return ComparisonIconEngine()

    def paint(self, painter, rect, mode, state):
        group = QPalette.ColorGroup.Disabled if mode == QIcon.Mode.Disabled else QPalette.ColorGroup.Active
        role = QPalette.ColorRole.Highlight if state == QIcon.State.On else QPalette.ColorRole.ButtonText
        color = QApplication.palette().color(group, role)
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            size = min(rect.width(), rect.height())
            painter.translate(rect.center().x() - size / 2, rect.center().y() - size / 2)
            painter.scale(size / 24, size / 24)
            painter.setPen(QPen(color, 1.5))
            painter.drawRoundedRect(QRectF(2, 4, 8, 16), 1, 1)
            painter.drawRoundedRect(QRectF(14, 4, 8, 16), 1, 1)
            painter.drawLine(12, 3, 12, 21)
        finally:
            painter.restore()
