"""Real network monitoring with psutil: speeds, totals, daily usage, adapter detection."""
import json, logging, os, socket, time
from datetime import date
import psutil
from PySide6.QtCore import QObject, QTimer, Qt, Signal

log = logging.getLogger(__name__)

VIRTUAL_HINTS = ("loopback", "vethernet", "virtualbox", "vmware", "vmnet", "hyper-v", "tap-",
                 "tap ", "bluetooth", "pseudo", "docker", "wsl", "npcap", "tailscale", "zerotier",
                 "wireguard", "miniport", "isatap", "teredo", "host-only", "veth", "br-", "virbr")


def fmt_speed(bps):
    kb = bps / 1024
    return f"{kb:.1f} KB/s" if kb < 1000 else f"{kb / 1024:.2f} MB/s"


def fmt_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def adapter_kind(name):
    n = name.lower()
    if any(t in n for t in ("wi-fi", "wifi", "wlan", "wireless", "wl")):
        return "Wi-Fi"
    if any(t in n for t in ("ethernet", "eth", "lan", "en0", "enp", "eno")):
        return "Ethernet"
    return "Other"


def _valid_ipv4(ip):
    return bool(ip) and not ip.startswith(("169.254.", "127.", "0."))


class UsageStore:
    """Persistent totals + per-day usage (JSON)."""

    def __init__(self, path):
        self.path = path
        self.total_down = self.total_up = 0
        self.days = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.total_down = int(raw.get("total_down", 0))
            self.total_up = int(raw.get("total_up", 0))
            self.days = {k: [int(v[0]), int(v[1])] for k, v in raw.get("days", {}).items()}
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("Could not read usage file; starting fresh")

    def add(self, down, up):
        self.total_down += down
        self.total_up += up
        d = self.days.setdefault(date.today().isoformat(), [0, 0])
        d[0] += down
        d[1] += up

    def today(self):
        return tuple(self.days.get(date.today().isoformat(), (0, 0)))

    def reset(self):
        self.total_down = self.total_up = 0
        self.days = {}
        self.save()

    def save(self):
        try:
            keep = sorted(self.days)[-62:]
            payload = {"total_down": self.total_down, "total_up": self.total_up,
                       "days": {k: self.days[k] for k in keep}}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
        except Exception:
            log.exception("Could not save usage")


class NetworkMonitor(QObject):
    updated = Signal(dict)

    def __init__(self, usage):
        super().__init__()
        self.usage = usage
        self._prev, self._cand, self._primary = {}, [], None
        self._t, self._n = 0.0, 0
        self._timer = QTimer(self, interval=1000)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self.tick)

    def start(self):
        self.tick()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.usage.save()

    def _refresh_candidates(self):
        stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
        real, virt = [], []
        for name, st in stats.items():
            if not st.isup:
                continue
            if not any(a.family == socket.AF_INET and _valid_ipv4(a.address) for a in addrs.get(name, [])):
                continue
            (virt if any(h in name.lower() for h in VIRTUAL_HINTS) else real).append(name)
        # Prefer physical adapters (counting only them avoids double-counting VPN/virtual traffic)
        self._cand = sorted(real or virt, key=lambda n: (adapter_kind(n) == "Other", n))

    def tick(self):
        try:
            now = time.monotonic()
            dt = max(now - self._t, 0.25) if self._t else 1.0
            self._t = now
            if not self._cand or self._n % 5 == 0:
                self._refresh_candidates()
            self._n += 1

            deltas = {}
            for name, c in psutil.net_io_counters(pernic=True).items():
                prev = self._prev.get(name)
                if prev is not None:
                    di, do = c.bytes_recv - prev[0], c.bytes_sent - prev[1]
                    deltas[name] = (di if di >= 0 else c.bytes_recv, do if do >= 0 else c.bytes_sent)
                self._prev[name] = (c.bytes_recv, c.bytes_sent)

            din = sum(deltas.get(n, (0, 0))[0] for n in self._cand)
            dout = sum(deltas.get(n, (0, 0))[1] for n in self._cand)
            self.usage.add(din, dout)

            load = lambda n: sum(deltas.get(n, (0, 0)))
            best = max(self._cand, key=load, default=None)
            if self._primary not in self._cand:
                self._primary = best
            elif best != self._primary and load(best) > 2 * load(self._primary) + 50_000:
                self._primary = best

            dd, du = self.usage.today()
            name = self._primary or ""
            self.updated.emit({
                "down_bps": din / dt, "up_bps": dout / dt,
                "total_down": self.usage.total_down, "total_up": self.usage.total_up,
                "daily_down": dd, "daily_up": du, "daily_total": dd + du,
                "connected": bool(self._cand), "adapter": name,
                "kind": adapter_kind(name) if name else "",
            })
            if self._n % 30 == 0:
                self.usage.save()
        except Exception:
            log.exception("Network tick failed")
