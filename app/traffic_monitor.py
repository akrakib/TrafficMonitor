"""Wires everything together: settings, monitor, widget, tray, menus."""
import logging, os
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, APP_VERSION, winutils
from .config import DEFAULTS, TASKBAR_PRESET, Settings, data_dir
from .icon import make_icon
from .network import NetworkMonitor, UsageStore
from .settings_dialog import SettingsDialog
from .widget import MonitorWidget

log = logging.getLogger(__name__)
MENU_QSS = """QMenu{background:#0F172A;color:#E2E8F0;border:1px solid #243049;border-radius:8px;padding:6px;font-family:"Segoe UI";font-size:10pt}
QMenu::item{padding:6px 22px;border-radius:5px}QMenu::item:selected{background:#164E63}
QMenu::separator{height:1px;background:#243049;margin:5px 8px}"""


class TrafficMonitor:
    def __init__(self, qapp):
        self.qapp = qapp
        self.settings = Settings()
        self.usage = UsageStore(os.path.join(data_dir(), "usage.json"))
        self.monitor = NetworkMonitor(self.usage)
        self.widget = MonitorWidget(self.settings)
        self.dialog = None
        self._hint_shown = False
        self.monitor.updated.connect(self.widget.update_data)
        self.widget.menuRequested.connect(self._widget_menu)
        self.widget.modeToggleRequested.connect(self.toggle_mode)
        self.settings.changed.connect(self._on_setting)
        winutils.set_startup(self.settings["start_with_windows"])   # keep registry in sync

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(make_icon(), qapp)
            self.tray.setToolTip(f"{APP_NAME} v{APP_VERSION}")
            menu = QMenu()
            menu.setStyleSheet(MENU_QSS)
            menu.aboutToShow.connect(lambda: self._fill(menu))
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda r: self.toggle_visible()
                                        if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
            self.tray.show()
            self._tray_menu = menu
        self.monitor.start()
        if self.tray and self.settings["start_minimized"]:
            pass
        else:
            self.widget.fade_in()

    # ---- menus ----
    def _fill(self, menu):
        s = self.settings
        menu.clear()
        menu.addAction("Hide widget" if self.widget.isVisible() else "Show widget", self.toggle_visible)
        menu.addAction("Settings…", self.show_settings)
        menu.addSeparator()
        for text, key in (("Lock position", "locked"), ("Always on top", "always_on_top")):
            a = menu.addAction(text)
            a.setCheckable(True)
            a.setChecked(s[key])
            a.triggered.connect(lambda c, k=key: s.set(k, c))
        a = menu.addAction("Compact mode")
        a.setCheckable(True)
        a.setChecked(s["mode"] == "compact")
        a.triggered.connect(lambda _: self.toggle_mode())
        menu.addSeparator()
        menu.addAction("Dock to taskbar (left)", self.dock_taskbar)
        menu.addAction("Reset statistics…", self.reset_stats)
        menu.addSeparator()
        menu.addAction("Exit", self.quit)

    def _widget_menu(self, pos):
        menu = QMenu()
        menu.setStyleSheet(MENU_QSS)
        self._fill(menu)
        menu.exec(pos)

    # ---- actions ----
    def show_settings(self):
        if self.dialog is None:
            self.dialog = SettingsDialog(self.settings, self)
        self.dialog.refresh()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def toggle_visible(self):
        if self.widget.isVisible():
            self.widget.fade_out()
            if self.tray and not self._hint_shown:
                self._hint_shown = True
                self.tray.showMessage(APP_NAME, "Still running in the system tray. Click the icon to show the widget.",
                                      QSystemTrayIcon.Information, 3000)
        else:
            self.widget.fade_in()

    def toggle_mode(self):
        self.settings.set("mode", "compact" if self.settings["mode"] == "expanded" else "expanded")

    def dock_taskbar(self):
        self.settings.update(TASKBAR_PRESET)
        if not self.widget.isVisible():
            self.widget.fade_in()

    def _confirm(self, text):
        box = QMessageBox(self.dialog or self.widget)
        box.setWindowTitle(APP_NAME)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.setStyleSheet("QWidget{background:#0F172A;color:#E2E8F0;font-family:'Segoe UI'}"
                          "QPushButton{background:#16233F;border:1px solid #243049;border-radius:6px;padding:6px 16px}")
        return box.exec() == QMessageBox.Yes

    def reset_stats(self):
        if self._confirm("Reset total and daily usage statistics?"):
            self.usage.reset()

    def reset_settings(self):
        if self._confirm("Restore all settings to their defaults?"):
            self.settings.update(DEFAULTS)

    def _on_setting(self, key):
        if key == "start_with_windows":
            if not winutils.set_startup(self.settings[key]) and winutils.IS_WIN and self.tray:
                self.tray.showMessage(APP_NAME, "Could not change the Windows startup entry.", QSystemTrayIcon.Warning)

    def quit(self):
        self.monitor.stop()
        self.settings.save()
        if self.tray:
            self.tray.hide()
        self.qapp.quit()


Application = TrafficMonitor
