# TrafficMonitor  `v1.0.0`

A lightweight, fully customizable glassmorphism network-speed widget for Windows 10/11.
It shows **real** download/upload speed (updated every second), total and daily usage, connection status
and the active adapter, and can sit at the left end of the Windows taskbar.

Built with **Python + PySide6 + psutil**. All numbers come from the OS network counters — nothing is simulated.

## Features
- Live download / upload speed (KB/s → MB/s), refreshed every second
- Total download/upload (persisted across restarts) and daily download / upload / combined usage
- Connection status and automatic active-adapter detection (Wi-Fi and Ethernet; virtual/VPN/Hyper-V/VMware adapters are ignored to avoid double counting)
- Premium dark glass UI: real Windows acrylic blur, rounded corners, gradient edge, fade animations
- Settings panel (live-applying, auto-saved): size, position, transparency, blur, colors, font, radius, border, opacity, per-stat visibility, branding (name, subtitle, alignment, visibility), layout (vertical / horizontal / grid), compact & expanded modes
- Always on top, start with Windows, lock position, drag to move, system tray, restores last position
- Low footprint: one 1-second timer, no polling threads, repaints only when text changes

## Project structure
```
TrafficMonitor/
├── main.py                 entry point (single-instance lock, logging, error hook)
├── requirements.txt
├── build.bat               one-click EXE build
├── run.bat                 run without a console window
├── README.md
├── app/
│   ├── __init__.py         name / version / brand constants
│   ├── config.py           defaults, validation, JSON settings, auto-save, logging
│   ├── network.py          psutil monitor, adapter detection, usage store, formatters
│   ├── widget.py           glass widget: painting, layouts, drag, docking, animations
│   ├── settings_dialog.py  tabbed settings panel
│   ├── traffic_monitor.py  controller: tray, menus, actions
│   ├── application.py     compatibility import for older code
│   ├── winutils.py         acrylic blur, topmost, startup registry (Windows APIs)
│   └── icon.py             generated app/tray icon
├── tools/make_icon.py      creates assets/icon.ico for the EXE
└── assets/
```

## Install & run (step by step)
1. Install **Python 3.10+ (64-bit)** from python.org (tick *Add python.exe to PATH*).
2. Open PowerShell / Command Prompt in the project folder.
3. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python main.py` (or double-click `run.bat` for no console window).

The widget appears on the left of the screen. **Right-click** it for the menu, **drag** it anywhere, **double-click** to toggle compact/expanded.

### Put it on the taskbar (left side)
Right-click the widget → **Dock to taskbar (left)** (or Settings → Layout → *Dock to taskbar*). This switches to a compact horizontal strip and aligns it with the left end of the taskbar.
- On **Windows 11** the Widgets/weather button lives at the left of the taskbar. Turn it off in *Settings → Personalization → Taskbar → Widgets* so the monitor has the space (with centered icons the left side is otherwise free).
- Keep **Always on top** enabled; the app re-asserts its z-order every few seconds because the taskbar can cover it.
- Auto-hide taskbars can't be measured, so the widget falls back to the bottom-left corner.

## Settings overview
| Tab | What you can change |
|---|---|
| Appearance | background/text/accent colors, background transparency, glass blur + tint, opacity, corner radius, border, font family/size |
| Layout | vertical / horizontal / grid, expanded / compact, position (taskbar-left, left, right, top, bottom, custom), auto-size or fixed width/height |
| Statistics | show/hide each of the 9 statistics |
| Branding | show/hide, brand name, subtitle, alignment |
| General | always on top, start with Windows, lock position, start minimized to tray, reset statistics, restore defaults |

Data files live in `%APPDATA%\AKabirLiveMonitor\`: `settings.json`, `usage.json`, `monitor.log`.

## Build a Windows EXE
Inside the activated venv, from the project folder:
```
build.bat
```
Result: `dist\TrafficMonitor.exe` (single file, no console window, custom icon). Equivalent manual command:
```
python tools\make_icon.py
pyinstaller --noconfirm --clean --onefile --windowed --name TrafficMonitor --icon assets\icon.ico main.py
```
Tips: use `--onedir` instead of `--onefile` for faster startup (and keep the whole `dist\TrafficMonitor` folder). If antivirus flags a fresh PyInstaller EXE, that is a common false positive — build from source on your own machine.

## Notes & troubleshooting
- **How speed is measured:** bytes received/sent on all connected physical adapters between two 1-second ticks, divided by the real elapsed time.
- **"Total" means since the last reset** (persisted); "Today" resets at midnight automatically.
- **Blur looks square / not blurred?** Acrylic needs Windows 10 1803+ or Windows 11. If a driver/policy disables transparency (*Settings → Personalization → Colors → Transparency effects*), turn it on, or disable blur in the panel.
- **Start with Windows** writes `HKCU\...\Run\AKabirLiveInternetMonitor`; untick the option to remove it.
- **Something wrong?** Check `%APPDATA%\AKabirLiveMonitor\monitor.log`. Deleting `settings.json` restores defaults.
