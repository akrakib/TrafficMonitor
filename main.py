"""TrafficMonitor — entry point."""
import logging, os, sys, tempfile, traceback

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, APP_VERSION
from app.config import setup_logging
from app.icon import make_icon


def main():
    setup_logging()
    log = logging.getLogger("main")

    def hook(t, v, tb):
        log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(t, v, tb)))
    sys.excepthook = hook

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AKabir.LiveInternetMonitor.1")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationVersion(APP_VERSION)
    qapp.setWindowIcon(make_icon())
    qapp.setQuitOnLastWindowClosed(False)

    lock = QLockFile(os.path.join(tempfile.gettempdir(), "akabir_live_monitor.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "TrafficMonitor is already running.\n"
                                                "Look for its icon in the system tray.")
        return 0

    from app.traffic_monitor import TrafficMonitor
    try:
        window_owner = TrafficMonitor(qapp)       # keep a reference alive
    except Exception:
        log.exception("Startup failed")
        QMessageBox.critical(None, APP_NAME, "Startup failed. See monitor.log in %APPDATA%\\AKabirLiveMonitor.")
        return 1
    code = qapp.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
