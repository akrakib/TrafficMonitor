from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap


def make_pixmap(size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#0F2A44"))
    g.setColorAt(1, QColor("#0B1220"))
    p.setBrush(g)
    p.setPen(QColor(34, 211, 238, 200))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), size * 0.24, size * 0.24)
    p.setFont(QFont("Segoe UI", int(size * 0.42), QFont.Bold))
    p.setPen(QColor("#22D3EE"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "A")
    p.end()
    return pm


def make_icon():
    return QIcon(make_pixmap(64))
