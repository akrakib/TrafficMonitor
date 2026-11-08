"""Settings model: defaults, validation, JSON persistence with debounced auto-save."""
import json, logging, os, tempfile
from logging.handlers import RotatingFileHandler
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor

log = logging.getLogger(__name__)

# (key, title) in display order
STATS = [
    ("down_speed", "DOWNLOAD"), ("up_speed", "UPLOAD"),
    ("total_down", "TOTAL DOWN"), ("total_up", "TOTAL UP"),
    ("daily_down", "TODAY DOWN"), ("daily_up", "TODAY UP"),
    ("daily_total", "TODAY TOTAL"), ("status", "STATUS"), ("adapter", "ADAPTER"),
]

# Slim, transparent taskbar look: white text, name + tagline, only Download/Upload
TASKBAR_PRESET = {
    "position": "taskbar_left", "layout": "horizontal", "mode": "compact", "auto_size": True,
    "always_on_top": True, "transparent_bg": True, "auto_text_color": True, "bg_transparency": 98, "blur_enabled": False,
    "text_color": "#FFFFFF", "accent_color": "#FFFFFF",
    "font_size": 9, "corner_radius": 0, "border_width": 0,
    "brand_visible": True, "brand_name": "TrafficMonitor", "brand_subtitle": "LIVE TRAFFIC",
    "brand_align": "left",
    "show_down_speed": True, "show_up_speed": True, "show_total_down": False, "show_total_up": False,
    "show_daily_down": False, "show_daily_up": False, "show_daily_total": False,
    "show_status": False, "show_adapter": False,
}

_BASE = {
    "width": 320, "height": 240, "auto_size": True,
    "position": "left", "x": 100, "y": 100,
    "layout": "vertical", "mode": "expanded",
    "bg_transparency": 35, "blur_enabled": True, "blur_strength": 30,
    "bg_color": "#0B1220", "text_color": "#E6F1FF", "accent_color": "#22D3EE",
    "font_family": "Segoe UI", "font_size": 10,
    "corner_radius": 16, "border_width": 1, "opacity": 100,
    **{f"show_{k}": True for k, _ in STATS},
    "brand_visible": True, "brand_name": "TrafficMonitor",
    "brand_subtitle": "LIVE TRAFFIC", "brand_align": "left",
    "always_on_top": True, "start_with_windows": True,
    "locked": False, "start_minimized": False,
    "icon_path": "", "icon_size": 26, "auto_text_color": True, "transparent_bg": True,
}
DEFAULTS = {**_BASE, **TASKBAR_PRESET}
RANGES = {"width": (120, 900), "height": (32, 900), "bg_transparency": (0, 99),
          "blur_strength": (0, 100), "font_size": (7, 24), "corner_radius": (0, 40),
          "border_width": (0, 6), "icon_size": (12, 64), "opacity": (20, 100), "x": (-20000, 20000), "y": (-20000, 20000)}
CHOICES = {"position": ("taskbar_left", "left", "right", "top", "bottom", "custom"),
           "layout": ("vertical", "horizontal", "grid"),
           "mode": ("expanded", "compact"),
           "brand_align": ("left", "center", "right")}
COLOR_KEYS = ("bg_color", "text_color", "accent_color")


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "AKabirLiveMonitor")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.join(tempfile.gettempdir(), "AKabirLiveMonitor")
        os.makedirs(path, exist_ok=True)
    return path


def setup_logging():
    try:
        h = RotatingFileHandler(os.path.join(data_dir(), "monitor.log"), maxBytes=200_000, backupCount=1, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[h],
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    except Exception:
        logging.basicConfig(level=logging.WARNING)


def _clean(key, value):
    """Coerce a loaded value to the right type; fall back to default if invalid."""
    d = DEFAULTS[key]
    try:
        if isinstance(d, bool):
            return bool(value)
        if isinstance(d, int):
            lo, hi = RANGES.get(key, (-10**9, 10**9))
            return max(lo, min(hi, int(value)))
        if key in CHOICES:
            return value if value in CHOICES[key] else d
        if key in COLOR_KEYS:
            return value if QColor(str(value)).isValid() else d
        return str(value)
    except (TypeError, ValueError):
        return d


class Settings(QObject):
    changed = Signal(str)

    def __init__(self, path=None):
        super().__init__()
        self.path = path or os.path.join(data_dir(), "settings.json")
        self.data = dict(DEFAULTS)
        self._timer = QTimer(self, singleShot=True, interval=600)
        self._timer.timeout.connect(self.save)
        self.load()

    def __getitem__(self, key):
        return self.data[key]

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k in DEFAULTS:
                if k in raw:
                    self.data[k] = _clean(k, raw[k])
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("Corrupt settings file; using defaults")
            try:
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            log.exception("Could not save settings")

    def set(self, key, value):
        if key not in DEFAULTS:
            return
        value = _clean(key, value)
        if self.data[key] == value:
            return
        self.data[key] = value
        self.changed.emit(key)
        self._timer.start()          # auto-save, debounced

    def update(self, values):
        for k, v in values.items():
            self.set(k, v)