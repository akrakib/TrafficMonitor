"""Generates assets/icon.ico (used by the EXE build)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtGui import QGuiApplication
from app.icon import make_pixmap

app = QGuiApplication(sys.argv)
out = os.path.join(ROOT, "assets", "icon.ico")
ok = make_pixmap(256).toImage().save(out, "ICO")
print("icon written:" if ok else "FAILED:", out)
