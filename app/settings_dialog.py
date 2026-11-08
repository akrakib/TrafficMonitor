"""Settings panel. Every control writes straight to Settings, so changes apply live."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QColorDialog, QComboBox, QDialog, QFontComboBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from . import APP_NAME, APP_VERSION
import glob, os, shutil, time
from .config import STATS, data_dir
from .icon import make_icon

QSS = """
QDialog,QWidget{background:#0F172A;color:#E2E8F0;font-family:"Segoe UI";font-size:10pt}
QLabel{background:transparent}
QTabWidget::pane{border:1px solid #1E293B;border-radius:8px;top:-1px}
QTabBar::tab{padding:8px 14px;background:transparent;color:#94A3B8;border-bottom:2px solid transparent}
QTabBar::tab:selected{color:#22D3EE;border-bottom:2px solid #22D3EE}
QLineEdit,QComboBox,QSpinBox,QFontComboBox{background:#111C33;border:1px solid #243049;border-radius:6px;padding:4px 8px;min-height:20px}
QComboBox QAbstractItemView{background:#111C33;selection-background-color:#164E63;border:1px solid #243049}
QSlider::groove:horizontal{height:4px;background:#243049;border-radius:2px}
QSlider::sub-page:horizontal{background:#22D3EE;border-radius:2px}
QSlider::handle:horizontal{background:#E6F1FF;width:14px;margin:-6px 0;border-radius:7px}
QCheckBox{spacing:8px}
QCheckBox::indicator{width:16px;height:16px;border-radius:4px;border:1px solid #334155;background:#111C33}
QCheckBox::indicator:checked{background:#22D3EE;border-color:#22D3EE}
QPushButton{background:#16233F;border:1px solid #243049;border-radius:6px;padding:7px 14px}
QPushButton:hover{border-color:#22D3EE}
"""
EXTERNAL = {"position", "layout", "mode", "locked", "always_on_top", "auto_size"}


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.setFixedSize(84, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.set_color("#000000")
        self.clicked.connect(self._pick)

    def set_color(self, c):
        self._c = c
        q = QColor(c)
        fg = "#000" if (0.299 * q.red() + 0.587 * q.green() + 0.114 * q.blue()) > 150 else "#fff"
        self.setText(c.upper())
        self.setStyleSheet(f"background:{c};color:{fg};border:1px solid rgba(255,255,255,90);border-radius:6px;padding:0;")

    def _pick(self):
        col = QColorDialog.getColor(QColor(self._c), self.window(), "Choose color")
        if col.isValid():
            self.set_color(col.name())
            self.colorChanged.emit(col.name())


class SliderRow(QWidget):
    valueChanged = Signal(int)

    def __init__(self, lo, hi, suffix=""):
        super().__init__()
        self.suffix = suffix
        self.sl = QSlider(Qt.Horizontal)
        self.sl.setRange(lo, hi)
        self.lbl = QLabel()
        self.lbl.setFixedWidth(48)
        self.lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.sl, 1)
        lay.addWidget(self.lbl)
        self.sl.valueChanged.connect(self._on)

    def _on(self, v):
        self.lbl.setText(f"{v}{self.suffix}")
        self.valueChanged.emit(v)

    def setValue(self, v):
        self.sl.blockSignals(True)
        self.sl.setValue(v)
        self.sl.blockSignals(False)
        self.lbl.setText(f"{v}{self.suffix}")


class SettingsDialog(QDialog):
    def __init__(self, settings, app):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.s, self.app, self._sync = settings, app, []
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.setWindowIcon(make_icon())
        self.setStyleSheet(QSS)
        self.setMinimumWidth(480)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        for title, fn in (("Appearance", self._appearance), ("Layout", self._layout), ("Statistics", self._stats),
                          ("Branding", self._branding), ("General", self._general)):
            tabs.addTab(fn(), title)
        root.addWidget(tabs)
        foot = QLabel(f"{APP_NAME}  •  v{APP_VERSION}  •  changes apply instantly and save automatically")
        foot.setStyleSheet("color:#64748B;font-size:8pt")
        root.addWidget(foot)
        settings.changed.connect(lambda k: self.refresh() if k in EXTERNAL else None)
        self.refresh()

    # ---- control factories (each registers a setter used by refresh()) ----
    def _reg(self, w, fn):
        def f():
            w.blockSignals(True)
            fn()
            w.blockSignals(False)
        self._sync.append(f)

    def _check(self, key, text):
        w = QCheckBox(text)
        w.toggled.connect(lambda v: self.s.set(key, v))
        self._reg(w, lambda: w.setChecked(self.s[key]))
        return w

    def _slider(self, key, lo, hi, suffix=""):
        w = SliderRow(lo, hi, suffix)
        w.valueChanged.connect(lambda v: self.s.set(key, v))
        self._sync.append(lambda: w.setValue(self.s[key]))
        return w

    def _spin(self, key, lo, hi, step=1):
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.valueChanged.connect(lambda v: self.s.set(key, v))
        self._reg(w, lambda: w.setValue(self.s[key]))
        return w

    def _combo(self, key, items):
        w = QComboBox()
        for label, val in items:
            w.addItem(label, val)
        w.currentIndexChanged.connect(lambda i: self.s.set(key, w.itemData(i)))
        self._reg(w, lambda: w.setCurrentIndex(max(0, w.findData(self.s[key]))))
        return w

    def _color(self, key):
        w = ColorButton()
        w.colorChanged.connect(lambda c: self.s.set(key, c))
        self._sync.append(lambda: w.set_color(self.s[key]))
        return w

    def _line(self, key):
        w = QLineEdit()
        w.textChanged.connect(lambda t: self.s.set(key, t))
        def setter():
            if w.text() != self.s[key]:
                w.setText(self.s[key])
        self._reg(w, setter)
        return w

    def _form(self, rows):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(16, 16, 16, 16)
        form.setVerticalSpacing(11)
        for label, w in rows:
            form.addRow(label, w) if label else form.addRow(w)
        return page

    # ---- tabs ----
    def _appearance(self):
        font = QFontComboBox()
        font.currentFontChanged.connect(lambda f: self.s.set("font_family", f.family()))
        self._reg(font, lambda: font.setCurrentFont(QFont(self.s["font_family"])))
        return self._form([
            (None, self._check("transparent_bg", "Transparent background (blends with the taskbar)")),
            (None, self._check("auto_text_color", "Auto text color (white/black from Windows theme)")),
            ("Background color", self._color("bg_color")), ("Text color", self._color("text_color")),
            ("Accent color", self._color("accent_color")),
            ("Background transparency", self._slider("bg_transparency", 0, 99, "%")),
            (None, self._check("blur_enabled", "Glass blur effect (acrylic)")),
            ("Blur tint strength", self._slider("blur_strength", 0, 100, "%")),
            ("Widget opacity", self._slider("opacity", 20, 100, "%")),
            ("Corner radius", self._slider("corner_radius", 0, 40, " px")),
            ("Border thickness", self._slider("border_width", 0, 6, " px")),
            ("Font family", font), ("Font size", self._spin("font_size", 7, 24)),
        ])

    def _layout(self):
        self._w_spin, self._h_spin = self._spin("width", 120, 900, 10), self._spin("height", 32, 900, 10)
        preset = QPushButton("Dock to taskbar (left) — compact strip")
        preset.clicked.connect(self.app.dock_taskbar)
        return self._form([
            ("Layout", self._combo("layout", [("Vertical card", "vertical"), ("Horizontal strip", "horizontal"), ("Grid", "grid")])),
            ("Mode", self._combo("mode", [("Expanded (all selected stats)", "expanded"), ("Compact (speeds only)", "compact")])),
            ("Position", self._combo("position", [("Taskbar — left end", "taskbar_left"), ("Screen left", "left"),
                                                  ("Screen right", "right"), ("Screen top", "top"),
                                                  ("Screen bottom", "bottom"), ("Custom (dragged)", "custom")])),
            (None, self._check("auto_size", "Auto-size to content")),
            ("Width", self._w_spin), ("Height", self._h_spin), (None, preset),
        ])

    def _stats(self):
        names = dict(zip([k for k, _ in STATS], ["Download speed", "Upload speed", "Total download", "Total upload",
                 "Daily download", "Daily upload", "Combined daily usage", "Connection status", "Adapter name"]))
        return self._form([(None, self._check(f"show_{k}", names[k])) for k, _ in STATS])

    def _branding(self):
        return self._form([
            (None, self._check("brand_visible", "Show branding")),
            ("Brand name", self._line("brand_name")), ("Subtitle", self._line("brand_subtitle")),
            ("Text alignment", self._combo("brand_align", [("Left", "left"), ("Center", "center"), ("Right", "right")])),
            ("Icon / photo", self._icon_row()), ("Icon size", self._slider("icon_size", 12, 64, " px")),
        ])

    def _icon_row(self):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        pick, clear = QPushButton("Choose image…"), QPushButton("Remove")
        pick.clicked.connect(self._pick_icon)
        clear.clicked.connect(lambda: self._set_icon(""))
        self._icon_lbl = QLabel()
        self._icon_lbl.setStyleSheet("color:#94A3B8")
        h.addWidget(pick)
        h.addWidget(clear)
        h.addWidget(self._icon_lbl, 1)
        return row

    def _pick_icon(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an icon or photo", "",
                                              "Images (*.png *.jpg *.jpeg *.ico *.bmp *.webp *.gif *.svg)")
        if path:
            # keep a private copy so the icon survives if the original file moves
            dst = os.path.join(data_dir(), f"brand_icon_{int(time.time())}{os.path.splitext(path)[1].lower()}")
            try:
                shutil.copyfile(path, dst)
            except OSError:
                dst = path
            self._set_icon(dst)

    def _set_icon(self, path):
        old = self.s["icon_path"]
        self.s.set("icon_path", path)
        if old and old != path and os.path.basename(old).startswith("brand_icon_"):
            try:
                os.remove(old)
            except OSError:
                pass
        self.refresh()

    def _general(self):
        rst = QPushButton("Reset statistics…")
        rst.clicked.connect(self.app.reset_stats)
        dfl = QPushButton("Restore default settings…")
        dfl.clicked.connect(self.app.reset_settings)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(rst)
        h.addWidget(dfl)
        return self._form([
            (None, self._check("always_on_top", "Always on top")),
            (None, self._check("start_with_windows", "Start with Windows")),
            (None, self._check("locked", "Lock widget position")),
            (None, self._check("start_minimized", "Start minimized to tray")),
            (None, row),
        ])

    def refresh(self):
        for f in self._sync:
            f()
        self._icon_lbl.setText(os.path.basename(self.s["icon_path"]) if self.s["icon_path"] else "No image")
        auto = self.s["auto_size"]
        self._w_spin.setEnabled(not auto)
        self._h_spin.setEnabled(not auto)