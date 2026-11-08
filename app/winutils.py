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


def bring_topmost(hwnd):
    """Re-assert TOPMOST (the taskbar can steal z-order). NOSIZE|NOMOVE|NOACTIVATE|SHOWWINDOW."""
    if IS_WIN:
        try:
            user32.SetWindowPos(int(hwnd), wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
        except Exception:
            pass


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