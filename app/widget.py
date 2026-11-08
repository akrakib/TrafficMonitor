"""The floating glass widget."""
import logging, os
from PySide6.QtCore import QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget)

from . import winutils
from .config import STATS
from .network import fmt_bytes, fmt_speed

log = logging.getLogger(__name__)
TITLES = dict(STATS)
GOOD, BAD = "#34D399", "#F87171"
ALIGN = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight}
EMPTY = {"down_bps": 0, "up_bps": 0, "total_down": 0, "total_up": 0, "daily_down": 0,
         "daily_up": 0, "daily_total": 0, "connected": None, "adapter": "", "kind": ""}


class MonitorWidget(QWidget):
    menuRequested = Signal(QPoint)
    modeToggleRequested = Signal()

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self._data = dict(EMPTY)
        self._drag = None
        self._moved = False
        self._flags_applied = None
        self._anim = None
        self._light = winutils.taskbar_is_light()
        self._styled, self.vl = [], {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("TrafficMonitor")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.body = QWidget()
        self.outer.addWidget(self.body)

        self._apply_timer = QTimer(self, singleShot=True, interval=25, timeout=self._apply)
        self._native_timer = QTimer(self, singleShot=True, interval=0, timeout=self._apply_native)
        self._top_timer = QTimer(self, interval=3000, timeout=self._keep_on_top)
        self._top_timer.start()
        settings.changed.connect(self._on_setting)
        self._apply(initial=True)

    # ---------- settings -> view ----------
    def _on_setting(self, key):
        if key not in ("x", "y"):
            self._apply_timer.start()

    def _flags(self):
        f = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        return f | Qt.WindowStaysOnTopHint if self.s["always_on_top"] else f

    def _apply(self, initial=False):
        try:
            flags = self._flags()
            if flags != self._flags_applied:
                vis = self.isVisible()
                self.setWindowFlags(flags)
                self._flags_applied = flags
                if vis:
                    self.show()
            self._build()
            self._resize()
            if not self._anim:
                self.setWindowOpacity(self.s["opacity"] / 100)
            if initial or self.s["position"] != "custom":
                self._place()
            self.update()
            self._native_timer.start()
        except Exception:
            log.exception("apply failed")

    def _visible_keys(self):
        s = self.s
        if s["mode"] == "compact":
            keys = [k for k in ("down_speed", "up_speed") if s[f"show_{k}"]]
            if keys:
                return keys
        return [k for k, _ in STATS if s[f"show_{k}"]]

    # ---------- building ----------
    def _mk(self, text, role, align=None):
        lbl = QLabel(text)
        if align:
            lbl.setAlignment(align)
        self._styled.append((lbl, role))
        return lbl

    def _font(self, size, bold=False, spacing=0):
        f = QFont(self.s["font_family"])
        f.setPointSizeF(max(6.0, size))
        f.setBold(bold)
        if spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        return f

    def _colors(self):
        """(text, accent): auto black/white from the Windows taskbar theme, or the user's choice."""
        s = self.s
        if s["auto_text_color"]:
            c = "#111111" if self._light else "#FFFFFF"
            return c, c
        return s["text_color"], s["accent_color"]

    def _style_all(self):
        s = self.s
        tc, acc = self._colors()
        fs, txt = s["font_size"], QColor(tc)
        muted = f"rgba({txt.red()},{txt.green()},{txt.blue()},185)"
        horiz = s["layout"] == "horizontal"
        spec = {"name": (self._font(fs + (1 if horiz else 6), True, 1.5 if horiz else 2), acc), "sub": (self._font(fs - 3, False, 0.6 if horiz else 1.6), muted),
                "title": (self._font(fs - 2, False, 1), muted), "speed": (self._font(fs + 1, True), acc),
                "value": (self._font(fs), tc)}
        for lbl, role in self._styled:
            font, color = spec[role]
            lbl.setFont(font)
            lbl.setStyleSheet(f"color:{color};background:transparent;")
        # stable widths so the widget never jitters while numbers change
        sp, da = QFontMetrics(spec["speed"][0]), QFontMetrics(spec["value"][0])
        for k, lbl in self.vl.items():
            if k in ("down_speed", "up_speed"):
                lbl.setMinimumWidth(sp.horizontalAdvance("0000.00 MB/s"))
            elif k in ("status", "adapter"):
                lbl.setFixedWidth(da.horizontalAdvance("0" * 18))
            else:
                lbl.setMinimumWidth(da.horizontalAdvance("0000.00 GB"))

    def _icon_label(self):
        s = self.s
        path = s["icon_path"]
        if not path or not os.path.isfile(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        size, dpr = s["icon_size"], self.devicePixelRatioF()
        pm = pm.scaled(int(size * dpr), int(size * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        lbl = QLabel()
        lbl.setPixmap(pm)
        lbl.setFixedSize(size, size)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("background:transparent;")
        return lbl

    def _brand(self):
        s = self.s
        text = QWidget()
        tl = QVBoxLayout(text)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)
        al = ALIGN[s["brand_align"]]
        if s["brand_name"].strip():
            tl.addWidget(self._mk(s["brand_name"], "name", al))
        if s["brand_subtitle"].strip():
            tl.addWidget(self._mk(s["brand_subtitle"], "sub", al))
        icon = self._icon_label()
        if tl.count() == 0 and not icon:
            return None
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        if icon:
            h.addWidget(icon, 0, Qt.AlignVCenter)
        if tl.count():
            h.addWidget(text, 1)
        pol = QSizePolicy.Preferred if s["layout"] == "horizontal" else QSizePolicy.Expanding
        box.setSizePolicy(pol, QSizePolicy.Preferred)
        return box

    def _tile(self, key):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._mk(TITLES[key], "title"))
        self.vl[key] = self._mk("", "speed" if key in ("down_speed", "up_speed") else "value")
        lay.addWidget(self.vl[key])
        return box

    def _row(self, key):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mk(TITLES[key], "title"))
        lay.addStretch(1)
        self.vl[key] = self._mk("", "speed" if key in ("down_speed", "up_speed") else "value",
                                Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.vl[key])
        return box

    def _build(self):
        s = self.s
        self.outer.removeWidget(self.body)
        self.body.deleteLater()
        self.body = QWidget()
        self.outer.addWidget(self.body)
        self._styled, self.vl = [], {}
        keys = self._visible_keys()
        brand = self._brand() if s["brand_visible"] else None
        m = max(12, s["corner_radius"] // 2 + 6)
        layout = s["layout"]
        if layout == "horizontal":
            lay = QHBoxLayout(self.body)
            lay.setSpacing(20)
            if brand:
                lay.addWidget(brand)
            for k in keys:
                lay.addWidget(self._tile(k))
        elif layout == "grid":
            lay = QGridLayout(self.body)
            lay.setHorizontalSpacing(24)
            lay.setVerticalSpacing(8)
            r = 0
            if brand:
                lay.addWidget(brand, 0, 0, 1, 2)
                r = 1
            for i, k in enumerate(keys):
                lay.addWidget(self._tile(k), r + i // 2, i % 2)
        else:
            lay = QVBoxLayout(self.body)
            lay.setSpacing(5)
            if brand:
                lay.addWidget(brand)
                lay.addSpacing(4)
            for k in keys:
                lay.addWidget(self._row(k))
        if not brand and not keys:
            lay.addWidget(self._mk("Nothing to show", "title"))
        vm = max(3, s["corner_radius"] // 4) if layout == "horizontal" else m - 2   # slim strip fits a 48px taskbar
        lay.setContentsMargins(m + 2, vm, m + 2, vm)
        self._style_all()
        self._refresh_values()
        self.body.show()     # widgets (re)built while the window is visible start hidden

    def _resize(self):
        if self.s["auto_size"]:
            self.outer.invalidate()
            self.outer.activate()
            sh = self.outer.sizeHint()
            self.setFixedSize(max(sh.width(), 80), max(sh.height(), 32))
        else:
            self.setFixedSize(self.s["width"], self.s["height"])

    # ---------- data ----------
    def update_data(self, d):
        self._data = d
        self._refresh_values()

    def _text(self, k, lbl):
        d = self._data
        if k == "down_speed": return fmt_speed(d["down_bps"])
        if k == "up_speed": return fmt_speed(d["up_bps"])
        if k in ("total_down", "total_up", "daily_down", "daily_up", "daily_total"): return fmt_bytes(d[k])
        if k == "status":
            return "● Detecting…" if d["connected"] is None else ("● Connected" if d["connected"] else "● Disconnected")
        name = d["adapter"] or "No adapter"
        if d["kind"] and d["kind"] not in name and d["adapter"]:
            name = f"{d['kind']} · {name}"
        return QFontMetrics(lbl.font()).elidedText(name, Qt.ElideRight, lbl.width() or 200)

    def _refresh_values(self):
        for k, lbl in self.vl.items():
            t = self._text(k, lbl)
            if lbl.text() != t:
                lbl.setText(t)
            if k == "status":
                c = self._data["connected"]
                col = self._colors()[1] if c is None else (GOOD if c else BAD)
                css = f"color:{col};background:transparent;"
                if lbl.styleSheet() != css:
                    lbl.setStyleSheet(css)
            if k == "adapter":
                lbl.setToolTip(self._data["adapter"])

    # ---------- painting & native effects ----------
    def paintEvent(self, _):
        s = self.s
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if s["transparent_bg"]:
            # 1/255 alpha: visually invisible, but keeps the window clickable/draggable on Windows
            p.fillRect(self.rect(), QColor(0, 0, 0, 1))
            return
        bw, r = s["border_width"], s["corner_radius"]
        rect = QRectF(self.rect()).adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2)
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        bg = QColor(s["bg_color"])
        bg.setAlphaF(1 - s["bg_transparency"] / 100)
        p.fillPath(path, bg)
        sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        sheen.setColorAt(0, QColor(255, 255, 255, 30))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(path, sheen)
        if bw > 0:
            acc = QColor(s["accent_color"])
            acc.setAlpha(110)
            edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
            edge.setColorAt(0, QColor(255, 255, 255, 90))
            edge.setColorAt(1, acc)
            p.setPen(QPen(edge, bw))
            p.drawPath(path)

    def _apply_native(self):
        if not winutils.IS_WIN or not self.isVisible():
            return
        try:
            s, hwnd = self.s, int(self.winId())
            c = QColor(s["bg_color"])
            blur = s["blur_enabled"] and not s["transparent_bg"]
            winutils.set_blur(hwnd, blur, (c.red(), c.green(), c.blue()), int(s["blur_strength"] * 2))
            if blur:
                dpr = self.devicePixelRatioF()
                winutils.set_round_region(hwnd, int(self.width() * dpr), int(self.height() * dpr),
                                          int(s["corner_radius"] * dpr))
            else:
                winutils.clear_region(hwnd)
        except Exception:
            log.exception("native effects failed")

    def showEvent(self, e):
        super().showEvent(e)
        self._native_timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._native_timer.start()

    def _keep_on_top(self):
        light = winutils.taskbar_is_light()
        if light != self._light:                 # Windows theme switched
            self._light = light
            self._apply_timer.start()
        if self.s["always_on_top"] and self.isVisible():
            winutils.bring_topmost(int(self.winId()))

    # ---------- placement ----------
    def _on_screen(self, x, y):
        r = self.frameGeometry().translated(x - self.x(), y - self.y())
        return any(sc.availableGeometry().intersects(r) or sc.geometry().intersects(r)
                   for sc in QGuiApplication.screens())

    def _place(self):
        s, pos = self.s, self.s["position"]
        scr = (self.screen() if self.isVisible() else None) or QGuiApplication.primaryScreen()
        g, a = scr.geometry(), scr.availableGeometry()
        w, h, m = self.width(), self.height(), 8
        if pos == "custom":
            x, y = s["x"], s["y"]
            if not self._on_screen(x, y):
                x, y = a.left() + m, a.top() + m
        elif pos == "left":
            x, y = a.left() + m, a.top() + (a.height() - h) // 2
        elif pos == "right":
            x, y = a.right() - w - m + 1, a.top() + (a.height() - h) // 2
        elif pos == "top":
            x, y = a.left() + (a.width() - w) // 2, a.top() + m
        elif pos == "bottom":
            x, y = a.left() + (a.width() - w) // 2, a.bottom() - h - m + 1
        else:  # taskbar_left: sit on the taskbar, at its left end
            tb, tt = g.bottom() - a.bottom(), a.top() - g.top()
            tl, tr = a.left() - g.left(), g.right() - a.right()
            if tb > 0:   x, y = g.left() + 6, a.bottom() + 1 + (tb - h) // 2
            elif tt > 0: x, y = g.left() + 6, g.top() + (tt - h) // 2
            elif tl > 0: x, y = g.left() + (tl - w) // 2, g.bottom() - h - 6
            elif tr > 0: x, y = a.right() + 1 + (tr - w) // 2, g.bottom() - h - 6
            else:        x, y = g.left() + 6, g.bottom() - h - 6   # auto-hidden taskbar
        self.move(x, y)

    # ---------- interaction ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.s["locked"]:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self._moved = True
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            if self._moved:
                p = self.pos()
                self.s.update({"position": "custom", "x": p.x(), "y": p.y()})

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.modeToggleRequested.emit()

    def contextMenuEvent(self, e):
        self.menuRequested.emit(e.globalPos())

    # ---------- fade animations ----------
    def fade_in(self):
        self.setWindowOpacity(0.0)
        self.show()
        self._fade(0.0, self.s["opacity"] / 100, None)

    def fade_out(self):
        self._fade(self.windowOpacity(), 0.0, self.hide)

    def _fade(self, a, b, done):
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(200)
        anim.setStartValue(a)
        anim.setEndValue(b)
        def finished():
            self._anim = None
            if done:
                done()
                self.setWindowOpacity(self.s["opacity"] / 100)
        anim.finished.connect(finished)
        self._anim = anim
        anim.start()