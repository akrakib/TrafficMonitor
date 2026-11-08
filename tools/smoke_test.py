"""Headless smoke test: python tools/smoke_test.py  (needs internet for the traffic check)."""
import os, sys, time, json, threading, urllib.request, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
from app.traffic_monitor import TrafficMonitor
from app.network import fmt_speed, fmt_bytes

qapp = QApplication(sys.argv)
def spin(ms):
    l = QEventLoop(); QTimer.singleShot(ms, l.quit); l.exec()

# generate real traffic in background
def traffic():
    try:
        for _ in range(3):
            urllib.request.urlopen("https://pypi.org/simple/", timeout=10).read()
    except Exception as e: print("traffic err", e)
threading.Thread(target=traffic, daemon=True).start()

a = TrafficMonitor(qapp); w = a.widget; s = a.settings
spin(3500)
d = w._data
print("DATA:", {k: (round(v,1) if isinstance(v,float) else v) for k,v in d.items()})
print("labels:", {k: l.text() for k,l in w.vl.items()})
assert d["connected"] is not None
assert fmt_speed(500) == "0.5 KB/s" and fmt_speed(2*1024*1024) == "2.00 MB/s" and fmt_bytes(5*1024**3) == "5.00 GB"
w.grab().save(tempfile.gettempdir() + "/shot_vertical.png")

for name, vals in {"horizontal_compact": dict(layout="horizontal", mode="compact"),
                   "grid": dict(layout="grid", mode="expanded", brand_align="center"),
                   "custom_look": dict(layout="vertical", accent_color="#A78BFA", bg_color="#201030", bg_transparency=10,
                                       corner_radius=28, border_width=3, font_size=12, brand_name="MY NET", brand_subtitle="HOME", brand_align="right"),
                   "fixed_size": dict(auto_size=False, width=420, height=300, layout="vertical", brand_visible=False, show_adapter=False, show_total_up=False)}.items():
    s.update(vals); spin(150); w.grab().save(tempfile.gettempdir() + f"/shot_{name}.png"); print(name, w.size().width(), w.size().height(), list(w.vl))

s.update(dict(position="taskbar_left", layout="horizontal", mode="compact", auto_size=True, brand_visible=True,
              show_adapter=True, show_total_up=True, accent_color="#22D3EE", bg_color="#0B1220", brand_name="A KABIR", brand_subtitle="LIVE NETWORK MONITOR", corner_radius=16, border_width=1, font_size=10, bg_transparency=35))
spin(150); print("taskbar pos", w.pos().x(), w.pos().y(), w.size().width(), w.size().height()); w.grab().save(tempfile.gettempdir() + "/shot_taskbar.png")
for pos in ("right","top","bottom","left"):
    s.set("position", pos); spin(100); print(pos, w.pos().x(), w.pos().y())

# drag simulation
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QPoint
w.show(); w.move(300, 200)
QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10));
QTest.mouseMove(w, QPoint(60, 50)); QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, QPoint(60, 50))
spin(100); print("after drag:", s["position"], s["x"], s["y"], w.pos())
s.set("locked", True); p = w.pos()
QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, QPoint(10,10)); QTest.mouseMove(w, QPoint(80,80)); QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, QPoint(80,80))
print("locked blocked drag:", w.pos() == p); s.set("locked", False)

# always on top flag toggle
s.set("always_on_top", False); spin(100); print("topmost off ->", bool(w.windowFlags() & Qt.WindowStaysOnTopHint), "visible", w.isVisible())
s.set("always_on_top", True); spin(100); print("topmost on  ->", bool(w.windowFlags() & Qt.WindowStaysOnTopHint))

# settings dialog: drive controls
a.show_settings(); dlg = a.dialog; spin(100)
from PySide6.QtWidgets import QCheckBox, QLineEdit, QSpinBox, QComboBox
cb = [c for c in dlg.findChildren(QCheckBox) if c.text() == "Daily upload"][0]; cb.setChecked(False); spin(100); print("hide daily_up ->", "daily_up" in w.vl, "(mode compact so n/a)" )
s.set("mode", "expanded"); spin(100); print("daily_up visible in expanded:", "daily_up" in w.vl)
le = dlg.findChildren(QLineEdit); le[0].setText("TEST BRAND"); spin(100); print("brand edit applied:", any(l.text()=="TEST BRAND" for l,_ in w._styled))
dlg.findChildren(QComboBox)[0].setCurrentIndex(2); spin(100); print("layout via combo:", s["layout"])
dlg.grab().save(tempfile.gettempdir() + "/shot_dialog.png")
# reset stats
a.usage.reset(); spin(1200); print("after reset totals:", w._data["total_down"], w._data["daily_down"] )
# persistence
s.save(); a.usage.save()
saved = json.load(open(s.path)); print("saved settings keys:", len(saved), "brand_name:", saved["brand_name"], "x,y:", saved["x"], saved["y"])
s2 = type(s)(); print("reload brand:", s2["brand_name"], "pos:", s2["position"])
# corrupt file
open(s.path, "w").write("{broken"); s3 = type(s)(); print("corrupt-> defaults:", s3["brand_name"])
w.fade_out(); spin(400); print("hidden after fade_out:", not w.isVisible()); w.fade_in(); spin(400); print("shown after fade_in:", w.isVisible(), w.windowOpacity())
a.quit(); print("OK")
