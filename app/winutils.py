"""Windows-specific helpers (acrylic blur, topmost, autostart). No-ops on other OSes."""
import logging, os, sys

log = logging.getLogger(__name__)
IS_WIN = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "AKabirLiveInternetMonitor"
_SetWCA = None

if IS_WIN:
    import ctypes, winreg
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

    class WCA_DATA(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]

    try:
        _SetWCA = user32.SetWindowCompositionAttribute
        _SetWCA.argtypes = [wintypes.HWND, ctypes.POINTER(WCA_DATA)]
        _SetWCA.restype = wintypes.BOOL
    except AttributeError:
        _SetWCA = None
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long


def set_blur(hwnd, enable, rgb, alpha):
    """Acrylic blur-behind (Windows 10 1803+ / Windows 11). alpha 1..255 = tint strength."""
    if not IS_WIN or _SetWCA is None:
        return False
    try:
        r, g, b = rgb
        policy = ACCENT_POLICY(4 if enable else 0, 2, (max(1, min(255, alpha)) << 24) | (b << 16) | (g << 8) | r, 0)
        data = WCA_DATA(19, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p), ctypes.sizeof(policy))
        return bool(_SetWCA(int(hwnd), ctypes.byref(data)))
    except Exception:
        log.exception("set_blur failed")
        return False


def set_round_region(hwnd, w, h, radius):
    """Clip the window (and its blur) to a rounded rectangle; radius<=0 clears the clip."""
    if not IS_WIN:
        return
    try:
        rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius * 2, radius * 2) if radius > 0 else None
        user32.SetWindowRgn(int(hwnd), rgn, True)
    except Exception:
        log.exception("set_round_region failed")


def clear_region(hwnd):
    if IS_WIN:
        try:
            user32.SetWindowRgn(int(hwnd), None, True)
        except Exception:
            pass


_raise_logged = 0
_debug_left = 40
log.info("winutils loaded: topmost-fix v2 (diagnostic)")


def debug_state(hwnd, tag):
    """Diagnostic: log which window is in front and whether the taskbar is above the widget (first 40 times)."""
    global _debug_left
    if not IS_WIN or _debug_left <= 0:
        return
    _debug_left -= 1
    try:
        fg = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(fg, buf, 128)
        ex = user32.GetWindowLongW(int(hwnd), -20)
        log.info("%s: foreground=%s widget_topmost=%s taskbar_above_widget=%s",
                 tag, buf.value, bool(ex & 0x8), _taskbar_above(int(hwnd)))
    except Exception:
        log.exception("debug_state failed")


def _taskbar_above(hwnd):
    """True if a taskbar window sits above hwnd in the z-order (i.e. it is covering the widget)."""
    bars = set()
    for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        h = user32.FindWindowW(cls, None)
        if h:
            bars.add(int(h))
    if not bars:
        return True                      # no taskbar found: just keep asserting TOPMOST
    h, n = user32.GetWindow(hwnd, 3), 0  # GW_HWNDPREV = the window directly above us
    while h and n < 200:
        if int(h) in bars:
            return True
        h, n = user32.GetWindow(h, 3), n + 1
    return False


def bring_topmost(hwnd):
    """Lift the widget above the taskbar again when the taskbar has been clicked.
    A plain SetWindowPos(HWND_TOPMOST) is ignored for a window that is already topmost, so when the taskbar
    really is above us we drop TOPMOST first and set it again, which forces a fresh z-order position."""
    global _raise_logged
    if not IS_WIN:
        return
    try:
        flags = 0x0001 | 0x0002 | 0x0010 | 0x0040        # NOSIZE|NOMOVE|NOACTIVATE|SHOWWINDOW
        if not _taskbar_above(int(hwnd)):
            return
        if _raise_logged < 5:
            _raise_logged += 1
            log.info("Taskbar was above the widget; re-raising it")
        user32.SetWindowPos(int(hwnd), wintypes.HWND(-2), 0, 0, 0, 0, flags)   # HWND_NOTOPMOST
        user32.SetWindowPos(int(hwnd), wintypes.HWND(-1), 0, 0, 0, 0, flags)   # HWND_TOPMOST
    except Exception:
        log.exception("bring_topmost failed")


_hook = None
_hook_proc = None


def watch_foreground(callback):
    """Call callback() whenever the foreground window changes (e.g. the taskbar was clicked).
    Runs on the Qt thread (needs the Qt message loop). Used to lift the widget above the taskbar again."""
    global _hook, _hook_proc
    if not IS_WIN or _hook:
        return False
    try:
        PROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                  wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def _cb(*_args):
            try:
                callback()
            except Exception:
                pass
        _hook_proc = PROC(_cb)          # keep a reference or it gets garbage-collected
        user32.SetWinEventHook.restype = wintypes.HANDLE
        user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, PROC,
                                           wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        # EVENT_SYSTEM_FOREGROUND = 0x0003, WINEVENT_OUTOFCONTEXT = 0
        _hook = user32.SetWinEventHook(0x0003, 0x0003, None, _hook_proc, 0, 0, 0)
        return bool(_hook)
    except Exception:
        log.exception("watch_foreground failed")
        return False


def _startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}"'


def set_startup(enabled):
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        log.exception("set_startup failed")
        return False


def taskbar_is_light():
    """True when Windows uses the light taskbar theme (so dark text is needed)."""
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False