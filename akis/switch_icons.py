"""Small painted icons for the sidebar switches (no emoji: they render unevenly across Windows fonts)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

SIZE = 16


def _canvas():
    pixmap = QPixmap(SIZE * 2, SIZE * 2)          # drawn at twice the size: sharp on high-DPI screens
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(2)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def moon(colour) -> QIcon:
    pixmap, p = _canvas()
    disc = QPainterPath()
    disc.addEllipse(QRectF(2.5, 2.5, 11, 11))
    bite = QPainterPath()
    bite.addEllipse(QRectF(6.5, 0.5, 10, 10))
    p.fillPath(disc.subtracted(bite), QColor(colour))
    p.end()
    return QIcon(pixmap)


def dot(colour) -> QIcon:
    """The record button's mark: a filled circle in a ring."""
    pixmap, p = _canvas()
    p.setPen(QPen(QColor(colour), 1.3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(8, 8), 6.2, 6.2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(colour))
    p.drawEllipse(QPointF(8, 8), 3.6, 3.6)
    p.end()
    return QIcon(pixmap)


def sun(colour) -> QIcon:
    pixmap, p = _canvas()
    p.setBrush(QColor(colour))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(8, 8), 3.2, 3.2)
    pen = QPen(QColor(colour), 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for step in range(8):
        angle = step * math.pi / 4
        p.drawLine(QPointF(8 + 5.2 * math.cos(angle), 8 + 5.2 * math.sin(angle)),
                   QPointF(8 + 6.9 * math.cos(angle), 8 + 6.9 * math.sin(angle)))
    p.end()
    return QIcon(pixmap)
