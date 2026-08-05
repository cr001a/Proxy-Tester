"""
ProxyTester - a proxy testing GUI.

Made by codyrandolph.

Copyright 2026 Cody Randolph. Licensed under the PolyForm Noncommercial
License 1.0.0 (see LICENSE). Noncommercial use only - no commercial use or
resale without the author's written permission.

Required Notice: Copyright 2026 Cody Randolph

Two tabs:
  1. ASN Tester (Oxylabs mobile) - tests carrier/ASN targeting.
  2. Proxy Tester (general)      - plain reachability/latency testing.

Standard library only (tkinter, urllib, threading, concurrent.futures, ...).
Package with:
    pyinstaller --onefile --windowed --name ProxyTester proxy_tester.py
"""

import base64
import csv
import json
import os
import queue
import random
import re
import shutil
import socket
import ssl
import statistics
import string
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urlsplit

# macOS system Tk (8.5) prints a deprecation warning on import when running from
# source. It's harmless and only noise in the Terminal - silence it. Must be set
# before tkinter loads. No effect on Windows or the packaged build.
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from logo_assets import LOGO_HEADER_B64, LOGO_ICON_B64
except ImportError:  # logo is optional
    LOGO_HEADER_B64 = LOGO_ICON_B64 = None

DEFAULT_TIMEOUT = 15   # seconds, per request
MAX_WORKERS = 6        # legacy default (kept for reference)
DEFAULT_WORKERS = 200  # parallel workers; overridable on the Settings tab
USER_AGENT = "ProxyTester/1.0"

APP_VERSION = "4.4"                    # single source of truth (CI tags v<this>)
UPDATE_REPO = "cr001a/Proxy-Tester"     # public repo required for auto-update


def _make_ssl_context():
    """A verifying TLS context that works in a frozen .exe. PyInstaller apps
    can't rely on the OS trust store, so use certifi's CA bundle when present,
    falling back to the system default otherwise."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None


SSL_CTX = _make_ssl_context()

# --------------------------------------------------------------------------- #
# Theme - a dark, slightly-purple palette (inspired by Catppuccin Mocha /
# Dracula), not pitch black. One mauve accent, semantic status colors.
# --------------------------------------------------------------------------- #
BASE = "#1e1e2e"      # window background
MANTLE = "#181825"    # deeper panels / tables
SURFACE = "#313244"   # inputs, buttons
SURFACE2 = "#45475a"  # borders / hover
TEXT = "#cdd6f4"      # primary text
SUBTEXT = "#a6adc8"   # muted text
MAUVE = "#cba6f7"     # primary purple accent
LAVENDER = "#b4befe"  # accent hover
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"

UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"


def apply_theme(root):
    root.configure(bg=BASE)
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BASE, foreground=TEXT,
                    fieldbackground=SURFACE, bordercolor=SURFACE2,
                    lightcolor=SURFACE, darkcolor=SURFACE, troughcolor=MANTLE,
                    insertcolor=TEXT, font=(UI_FONT, 10))
    style.configure("TFrame", background=BASE)
    style.configure("TLabel", background=BASE, foreground=TEXT)
    style.configure("Muted.TLabel", background=BASE, foreground=SUBTEXT)
    style.configure("Header.TLabel", background=BASE, foreground=MAUVE,
                    font=(UI_FONT + " Semibold", 15))
    style.configure("Warn.TLabel", background=BASE, foreground=YELLOW,
                    font=(UI_FONT + " Semibold", 11))

    style.configure("TButton", background=SURFACE, foreground=TEXT,
                    bordercolor=SURFACE2, focuscolor=BASE, padding=(12, 6),
                    relief="flat")
    style.map("TButton",
              background=[("active", SURFACE2), ("disabled", MANTLE)],
              foreground=[("disabled", SUBTEXT)])
    style.configure("Accent.TButton", background=MAUVE, foreground=BASE,
                    font=(UI_FONT + " Semibold", 10), padding=(14, 6))
    style.map("Accent.TButton",
              background=[("active", LAVENDER), ("disabled", SURFACE2)],
              foreground=[("disabled", SUBTEXT)])
    style.configure("Stop.TButton", background=RED, foreground=BASE,
                    font=(UI_FONT + " Semibold", 10), padding=(14, 6))
    style.map("Stop.TButton",
              background=[("active", "#eba0ac"), ("disabled", SURFACE2)],
              foreground=[("disabled", SUBTEXT)])

    style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT,
                    bordercolor=SURFACE2, insertcolor=TEXT, padding=4)
    style.map("TEntry", bordercolor=[("focus", MAUVE)])

    style.configure("TMenubutton", background=BASE, foreground=SUBTEXT,
                    arrowcolor=SUBTEXT, relief="flat", padding=2)
    style.map("TMenubutton", background=[("active", SURFACE)],
              foreground=[("active", MAUVE)])
    # Settings gear: a filled button matching Save/Delete height, larger glyph.
    style.configure("Gear.TButton", background=SURFACE2, foreground=TEXT,
                    bordercolor=SURFACE2, relief="flat", anchor="center",
                    font=(UI_FONT, 13), padding=(8, 6))
    style.map("Gear.TButton",
              background=[("active", MAUVE)],
              foreground=[("active", BASE)])

    style.configure("TRadiobutton", background=BASE, foreground=TEXT,
                    indicatorcolor=SURFACE, padding=4)
    style.map("TRadiobutton",
              background=[("active", BASE)],
              indicatorcolor=[("selected", MAUVE)],
              foreground=[("active", MAUVE)])
    style.configure("TCheckbutton", background=BASE, foreground=TEXT,
                    indicatorcolor=SURFACE, focuscolor=BASE, padding=2)
    style.map("TCheckbutton",
              background=[("active", BASE)],
              indicatorcolor=[("selected", MAUVE)],
              foreground=[("active", MAUVE)])

    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                    foreground=TEXT, arrowcolor=TEXT, bordercolor=SURFACE2,
                    padding=4)
    style.map("TCombobox",
              fieldbackground=[("readonly", SURFACE)],
              bordercolor=[("focus", MAUVE)])
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", MAUVE)
    root.option_add("*TCombobox*Listbox.selectForeground", BASE)

    style.configure("TNotebook", background=BASE, bordercolor=SURFACE2,
                    tabmargins=(6, 6, 6, 0))
    style.configure("TNotebook.Tab", background=MANTLE, foreground=SUBTEXT,
                    padding=(16, 8), font=(UI_FONT, 10))
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE), ("active", SURFACE2)],
              foreground=[("selected", MAUVE)])

    style.configure("Treeview", background=MANTLE, fieldbackground=MANTLE,
                    foreground=TEXT, bordercolor=SURFACE2, rowheight=26,
                    font=(UI_FONT, 10))
    style.map("Treeview", background=[("selected", SURFACE2)],
              foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", background=SURFACE, foreground=MAUVE,
                    relief="flat", font=(UI_FONT + " Semibold", 10),
                    padding=6)
    style.map("Treeview.Heading", background=[("active", SURFACE2)])

    style.configure("TScrollbar", background=SURFACE, troughcolor=MANTLE,
                    bordercolor=BASE, arrowcolor=TEXT)
    style.map("TScrollbar", background=[("active", SURFACE2)])


def style_text(widget):
    """Apply the dark palette to a plain tk.Text (not themed by ttk)."""
    widget.configure(background=SURFACE, foreground=TEXT, insertbackground=TEXT,
                     selectbackground=SURFACE2, selectforeground=TEXT,
                     relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=SURFACE2, highlightcolor=MAUVE,
                     padx=8, pady=6, font=(MONO_FONT, 10))


def paste_appends_to_end(text_widget, after=None):
    """<<Paste>> handler with two modes:
      - text is SELECTED  -> replace the selection (typical paste; so Ctrl+A then
        paste swaps the whole list);
      - nothing selected  -> append the clipboard to the END on a fresh line, so
        you can paste list after list without them running together.
    `after` is an optional callback (e.g. a count refresh) run once text is in."""
    def _handler(_event=None):
        try:
            clip = text_widget.clipboard_get()
        except tk.TclError:
            return "break"
        if text_widget.tag_ranges("sel"):
            # Replace the highlighted text with the clipboard, at the selection.
            text_widget.delete("sel.first", "sel.last")
            text_widget.insert("insert", clip)
        else:
            cur = text_widget.get("1.0", "end-1c").rstrip("\n")
            parts = [p for p in (cur, clip.strip("\n")) if p]
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", "\n".join(parts) + "\n")
            text_widget.mark_set("insert", "end-1c")
        text_widget.see("insert")
        if after:
            after()
        return "break"
    text_widget.bind("<<Paste>>", _handler)


def reveal_on_focus(entry):
    """Show the password while the field is focused, mask it otherwise."""
    entry.bind("<FocusIn>", lambda e: entry.configure(show=""))
    entry.bind("<FocusOut>", lambda e: entry.configure(show="•"))


def status_tag(status):
    s = str(status).lower()
    if s == "ok":
        return "ok"
    if s.startswith("testing"):
        return "muted"
    if s == "stopped":
        return "muted"
    # Access-denied / restricted / auth-limit -> yellow; other errors -> red.
    if (s.startswith(("403", "407")) or "access denied" in s
            or "forbidden" in s or "restricted" in s):
        return "warn"
    return "bad"


def attach_copy_menu(widget, copy_fn, label="Copy selected", extra=None):
    """Right-click 'Copy' menu for a results table or list.

    Ctrl+C on its own isn't enough: a Mac keyboard driving a Windows box over
    RDP sends Cmd, which Windows never sees as Control, so the keystroke
    silently does nothing and copying looks broken. A menu always works.
    `extra` is an optional list of (label, callback) appended to the menu.
    """
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label=label, command=copy_fn)
    menu.add_separator()

    def _select_all():
        if isinstance(widget, ttk.Treeview):
            widget.selection_set(widget.get_children())
        else:
            widget.selection_set(0, "end")
        widget.focus_set()

    menu.add_command(label="Select all", command=_select_all)
    for lbl, fn in (extra or []):
        menu.add_command(label=lbl, command=fn)

    def popup(event):
        try:
            # Right-clicking OUTSIDE the current selection moves the selection
            # to that row; inside it, the whole multi-row selection is kept.
            if isinstance(widget, ttk.Treeview):
                row = widget.identify_row(event.y)
                if row and row not in widget.selection():
                    widget.selection_set(row)
            else:
                idx = widget.nearest(event.y)
                if idx >= 0 and idx not in widget.curselection():
                    widget.selection_clear(0, "end")
                    widget.selection_set(idx)
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    # Button-3 is right-click on Windows/X11; Button-2 covers remote sessions
    # that remap the trackpad's secondary click. Control-Button-1 is
    # deliberately NOT bound - that's how ctrl+click extends a selection.
    for seq in ("<Button-3>", "<Button-2>"):
        widget.bind(seq, popup)
    return menu


def tag_tree(tree):
    tree.tag_configure("ok", foreground=GREEN)
    tree.tag_configure("bad", foreground=RED)
    tree.tag_configure("warn", foreground=YELLOW)
    tree.tag_configure("muted", foreground=SUBTEXT)


def enable_drag_select(tree):
    """Let the user click-and-drag to highlight a range of rows in a Treeview
    (not supported natively). Ctrl/Shift-click keep their native behavior."""
    SHIFT, CTRL = 0x0001, 0x0004

    def on_press(event):
        # Only engage drag-select for a plain click on a body cell. Presses on a
        # heading/separator must be left to the native column-resize handler,
        # and Ctrl/Shift-clicks to the native toggle/extend.
        if event.state & (SHIFT | CTRL):
            tree._drag_anchor = None
            return
        if tree.identify_region(event.x, event.y) != "cell":
            tree._drag_anchor = None
            return
        tree._drag_anchor = tree.identify_row(event.y) or None

    def on_drag(event):
        anchor = getattr(tree, "_drag_anchor", None)
        if not anchor or (event.state & (SHIFT | CTRL)):
            return None
        current = tree.identify_row(event.y)
        if not current:
            return None
        items = list(tree.get_children())
        try:
            lo, hi = sorted((items.index(anchor), items.index(current)))
        except ValueError:
            return None
        tree.selection_set(items[lo:hi + 1])
        return "break"

    tree.bind("<Button-1>", on_press, add="+")
    tree.bind("<B1-Motion>", on_drag)


# --------------------------------------------------------------------------- #
# Networking helpers (stdlib only, no shelling out)
# --------------------------------------------------------------------------- #
def _random_sessid(length=8):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def build_proxy_url(host, port, user=None, password=None):
    """
    Build an http proxy URL, percent-encoding credentials so passwords with
    special characters (@ : / ~ etc.) survive urllib's proxy URL parsing.
    """
    if user:
        u = quote(user, safe="")
        p = quote(password, safe="") if password is not None else ""
        return f"http://{u}:{p}@{host}:{port}"
    return f"http://{host}:{port}"


def normalize_url(url):
    """Default to https:// when the user omits the scheme (e.g. 'walmart.com')."""
    url = url.strip()
    if url and "://" not in url:
        return "https://" + url
    return url


def do_request(proxy_url, url, timeout=DEFAULT_TIMEOUT):
    """
    Perform a single request through the given proxy.

    Returns a dict:
        ok      : bool  - True on a 2xx/3xx response
        code    : int|None - HTTP status code if the server answered
        ms      : float - latency in milliseconds
        body    : bytes|None - response body on success
        error   : None|'http'|'conn' - failure class
        reason  : str   - human readable reason (for conn errors)
    """
    handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    https = urllib.request.HTTPSHandler(context=SSL_CTX) if SSL_CTX else None
    opener = (urllib.request.build_opener(handler, https) if https
              else urllib.request.build_opener(handler))
    req = urllib.request.Request(normalize_url(url), headers={"User-Agent": USER_AGENT})

    def _xerr(headers):
        # X-Error-Description is an Oxylabs-specific header; absent for other
        # providers, in which case this is just "".
        try:
            return (headers.get("x-error-description") or "").strip()
        except Exception:
            return ""

    start = time.perf_counter()
    try:
        resp = opener.open(req, timeout=timeout)
        body = resp.read()
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"ok": True, "code": resp.getcode(), "ms": elapsed, "body": body,
                "error": None, "reason": "", "xerr": _xerr(resp.headers),
                "http_reason": ""}
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "code": e.code, "ms": elapsed, "body": None,
                "error": "http", "reason": "", "xerr": _xerr(e.headers),
                "http_reason": str(getattr(e, "reason", "") or "")}
    except urllib.error.URLError as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "code": None, "ms": elapsed, "body": None,
                "error": "conn", "reason": str(getattr(e, "reason", e)),
                "xerr": "", "http_reason": ""}
    except (socket.timeout, ConnectionResetError, OSError) as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "code": None, "ms": elapsed, "body": None,
                "error": "conn", "reason": str(e), "xerr": "", "http_reason": ""}
    except Exception as e:  # never let a worker crash the app
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "code": None, "ms": elapsed, "body": None,
                "error": "conn", "reason": str(e), "xerr": "", "http_reason": ""}


# Proxy CONNECT failures for HTTPS targets surface as
# "Tunnel connection failed: <code> <phrase>" - parse the real status out.
_TUNNEL_RE = re.compile(r"tunnel connection failed:\s*(\d{3})\s*(.*)", re.I)


def response_code(r):
    """The HTTP status code, incl. codes hidden inside a tunnel-failure reason."""
    if r.get("code") is not None:
        return r["code"]
    m = _TUNNEL_RE.search(r.get("reason") or "")
    return int(m.group(1)) if m else None


def response_label(r):
    """Exact response for the status column. Universal (HTTP code / connection
    reason); the Oxylabs X-Error-Description is appended only when present."""
    if r.get("ok"):
        return "OK"
    xerr = (r.get("xerr") or "").strip()
    code = r.get("code")
    if code is not None:
        detail = xerr or (r.get("http_reason") or "").strip()
        return f"{code} {detail}".strip()[:60]
    reason = (r.get("reason") or "").strip()
    m = _TUNNEL_RE.search(reason)
    if m:
        detail = xerr or m.group(2).strip()
        return f"{m.group(1)} {detail}".strip()[:60]
    low = reason.lower()
    if "timed out" in low or "timeout" in low:
        return "timeout"
    if "refused" in low:
        return "refused"
    if "reset" in low:
        return "conn reset"
    if any(k in low for k in ("getaddrinfo", "name or service",
                              "resolve", "nodename")):
        return "DNS error"
    return (reason or "error")[:60]


def _parse_json_field(body, field):
    """Best-effort pull of a field out of a JSON body; '' if unavailable."""
    if not body:
        return ""
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return ""
    if isinstance(data, dict):
        value = data.get(field, "")
        return str(value) if value is not None else ""
    return ""


def _fmt_ms(value):
    return f"{value:.0f}" if value is not None else "-"


def _fmt_elapsed(seconds):
    """Human wall-clock duration for a finished run's status line, e.g. '850ms',
    '12.3s', '4m 07s', '1h 02m'. Precise enough to actually compare runs."""
    s = max(0.0, seconds)
    if s < 1:
        return f"{s * 1000:.0f}ms"
    if s < 60:
        return f"{s:.1f}s"
    m, rem = divmod(int(s), 60)
    if m < 60:
        return f"{m}m {rem:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


# --------------------------------------------------------------------------- #
# Site ping (latency to a website's edge)
# --------------------------------------------------------------------------- #
# Common retail / release targets. Handy for gauging your baseline network
# latency to each site's edge before a drop, or comparing server locations.
RETAIL_SITES = [
    ("Walmart", "www.walmart.com"),
    ("Target", "www.target.com"),
    ("Best Buy", "www.bestbuy.com"),
    ("Nike", "www.nike.com"),
    ("Foot Locker", "www.footlocker.com"),
    ("Adidas", "www.adidas.com"),
    ("Amazon", "www.amazon.com"),
    ("GameStop", "www.gamestop.com"),
    ("Pokemon Center", "www.pokemoncenter.com"),
    ("Costco", "www.costco.com"),
    ("Newegg", "www.newegg.com"),
    ("Shopify", "www.shopify.com"),
]


def _host_port_from_target(target):
    """Pull (host, port) out of a URL or a bare host[:port]. Defaults to 443."""
    t = target.strip()
    if "://" in t:
        t = t.split("://", 1)[1]
    t = t.split("/", 1)[0]
    if "@" in t:
        t = t.rsplit("@", 1)[1]
    port = 443
    if ":" in t:
        h, p = t.rsplit(":", 1)
        if p.isdigit():
            t, port = h, int(p)
    return t, port


def tcp_ping(host, port=443, timeout=DEFAULT_TIMEOUT):
    """One TCP-connect round-trip to host:port, in milliseconds (or None on
    failure). A raw connect - not an HTTP request - so bot-protection 403s
    never skew the number; it measures pure network latency to the edge."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - start) * 1000.0
    except Exception:
        return None


def ping_site(name, target, runs, timeout=DEFAULT_TIMEOUT, stop_event=None):
    """Ping a site `runs` times and aggregate min/median/max latency."""
    host, port = _host_port_from_target(target)
    lat = []
    fails = 0
    for _ in range(max(1, runs)):
        if stop_event is not None and stop_event.is_set():
            break
        ms = tcp_ping(host, port, timeout)
        if ms is None:
            fails += 1
        else:
            lat.append(ms)
    ran = len(lat) + fails
    if not lat:
        return {"name": name, "host": f"{host}:{port}", "status": "unreachable",
                "median": None, "min": None, "max": None,
                "success": 0, "runs": ran or runs}
    return {"name": name, "host": f"{host}:{port}", "status": "OK",
            "median": statistics.median(lat), "min": min(lat), "max": max(lat),
            "success": len(lat), "runs": ran}


def proxy_connect_ping(proxy, host, port, timeout=DEFAULT_TIMEOUT):
    """Time an HTTP CONNECT tunnel through `proxy` to host:port - the exact
    transport handshake every real HTTPS session through this proxy performs
    before any TLS or HTTP. Returns (ms, code, err): ms = round-trip until the
    proxy answers '200 Connection established' (None on failure); code = the
    CONNECT status the proxy returned (200 ok, 407 auth, 502/504 upstream, ...);
    err = short reason on failure. NO HTTP request is ever sent to the target,
    so its bot defences (PerimeterX, Akamai) never engage - a pure, PX-safe
    latency probe of the proxy's path to the retailer edge."""
    p_host = proxy["host"]
    try:
        p_port = int(proxy["port"])
    except (TypeError, ValueError, KeyError):
        return None, None, "bad proxy port"
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
    if proxy.get("user") and proxy.get("pw") is not None:
        token = base64.b64encode(
            f"{proxy['user']}:{proxy['pw']}".encode("utf-8")).decode("ascii")
        req += f"Proxy-Authorization: Basic {token}\r\n"
    req += "\r\n"
    start = time.perf_counter()
    sock = None
    try:
        sock = socket.create_connection((p_host, p_port), timeout=timeout)
        sock.settimeout(timeout)
        sock.sendall(req.encode("ascii"))
        # Read only up to the end of the status line - that's the moment the
        # tunnel is (or isn't) established; we don't send anything through it.
        buf = b""
        while b"\r\n" not in buf and len(buf) < 4096:
            chunk = sock.recv(256)
            if not chunk:
                break
            buf += chunk
        ms = (time.perf_counter() - start) * 1000.0
        line = buf.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = line.split(None, 2)          # "HTTP/1.1 200 Connection ..."
        code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        if code == 200:
            return ms, 200, None
        return None, code, (f"HTTP {code}" if code else "bad response")
    except socket.timeout:
        return None, None, "timeout"
    except Exception:
        return None, None, "network"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def ping_site_via_proxy(proxy, name, target, runs, timeout=DEFAULT_TIMEOUT,
                        stop_event=None):
    """Ping `target` through `proxy` `runs` times via CONNECT tunnels and
    aggregate min/median/max latency - the per-proxy transport latency to the
    retailer edge, with no HTTP request sent (PX-safe)."""
    host, port = _host_port_from_target(target)
    if proxy.get("user") and proxy.get("pw") is not None:
        display = f"{proxy['host']}:{proxy['port']}:{proxy['user']}:****"
        full = f"{proxy['host']}:{proxy['port']}:{proxy['user']}:{proxy['pw']}"
    else:
        display = f"{proxy['host']}:{proxy['port']}"
        full = display
    lat = []
    last_code = None
    err = ""
    ran = 0
    for _ in range(max(1, runs)):
        if stop_event is not None and stop_event.is_set():
            break
        ran += 1
        ms, code, e = proxy_connect_ping(proxy, host, port, timeout)
        if code is not None:
            last_code = code
        if ms is not None:
            lat.append(ms)
        elif e:
            err = e
    base = {"_pping": True, "proxy": display, "full": full, "name": name,
            "target": f"{host}:{port}",
            "code": last_code, "success": len(lat), "runs": ran or runs}
    if lat:
        base.update(status="OK", median=statistics.median(lat),
                    min=min(lat), max=max(lat))
    else:
        base.update(status=(err or "failed"), median=None, min=None, max=None)
    return base


# --------------------------------------------------------------------------- #
# IP quality / trust scoring
# --------------------------------------------------------------------------- #
# A proxy is only as good as the reputation of the IP it exits on. We measure
# that two ways: IPQualityScore (paid, best-in-class fraud/bot/proxy scoring)
# and Spamhaus ZEN (free DNS blocklist, no key). Both feed a single 0-100
# Trust score - higher is cleaner / more likely to pass anti-bot queues.
IPINFO_URL = "https://ipinfo.io/json"


class _RateLimiter:
    """Thread-safe request pacer: spaces calls evenly to a target rate, so
    throughput is capped by a documented-safe number regardless of how many
    worker threads are calling it. This is what lets concurrency be raised
    generously without risking a vendor's hard per-second limit - the limiter,
    not the thread count, is what actually governs requests/sec."""

    def __init__(self, rate_per_sec):
        self._interval = 1.0 / rate_per_sec
        self._lock = threading.Lock()
        self._next = time.perf_counter()

    def wait(self):
        with self._lock:
            now = time.perf_counter()
            self._next = max(self._next, now) + self._interval
            delay = self._next - now
        if delay > 0:
            time.sleep(delay)


def http_get_json_ex(url, timeout=DEFAULT_TIMEOUT, extra_headers=None):
    """Direct (no-proxy) HTTPS GET. Returns (data_or_None, error_or_None) where
    error is a short human string so callers can tell WHY it failed: 'HTTP 401'
    (bad/expired key), 'HTTP 429' (rate limited), 'timeout', 'bad json', etc."""
    try:
        headers = {"User-Agent": USER_AGENT}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers)
        opener = (urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=SSL_CTX)) if SSL_CTX
            else urllib.request.build_opener())
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        try:
            return json.loads(raw), None
        except ValueError:
            return None, "bad json"
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except socket.timeout:
        return None, "timeout"
    except Exception:
        return None, "network"


def http_get_json(url, timeout=DEFAULT_TIMEOUT, extra_headers=None):
    """Direct (no-proxy) HTTPS GET returning parsed JSON, or None on any error."""
    return http_get_json_ex(url, timeout, extra_headers)[0]


# Spamhaus ZEN answer codes -> which sublist the IP is on. These mean very
# different things for a residential proxy: XBL = a compromised/exploited host
# (botnet - a real 'dirty IP' signal); SBL = a known spam source; PBL = a
# dynamic/residential policy range, which describes virtually EVERY consumer IP
# and is NOT an abuse signal for web bot-detection. The Trust score weights them
# accordingly (see _trust_score) instead of docking a flat penalty for any hit.
_SPAMHAUS_ZONES = {
    "127.0.0.2": "SBL", "127.0.0.3": "SBL", "127.0.0.9": "SBL",
    "127.0.0.4": "XBL", "127.0.0.5": "XBL", "127.0.0.6": "XBL",
    "127.0.0.7": "XBL", "127.0.0.10": "PBL", "127.0.0.11": "PBL",
}


def spamhaus_lookup(ip):
    """Spamhaus ZEN DNSBL check (free, no key). Returns a dict:
      blacklisted    : True listed / False clean / None couldn't tell
      blacklist_kind : 'XBL' (botnet) / 'SBL' (spam) / 'PBL' (residential policy)
                       or a '+'-joined combo, worst-first; '' when not listed.
    A 127.255.255.x answer means a public/cloud resolver refused the query
    ('unknown', NOT a listing) - treating those as listed is what made rows flip
    listed/clean run to run."""
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return {"blacklisted": None, "blacklist_kind": ""}
    query = ".".join(reversed(parts)) + ".zen.spamhaus.org"
    try:
        answers = socket.gethostbyname_ex(query)[2]
    except socket.gaierror:
        return {"blacklisted": False, "blacklist_kind": ""}   # NXDOMAIN => clean
    except OSError:
        return {"blacklisted": None, "blacklist_kind": ""}
    kinds = []
    for a in answers:
        z = _SPAMHAUS_ZONES.get(a)
        if z and z not in kinds:
            kinds.append(z)
    if kinds:
        kinds.sort(key=lambda k: {"XBL": 0, "SBL": 1, "PBL": 2}.get(k, 9))
        return {"blacklisted": True, "blacklist_kind": "+".join(kinds)}
    if any(a.startswith("127.0.0.") for a in answers):
        return {"blacklisted": True, "blacklist_kind": ""}    # listed, zone n/a
    return {"blacklisted": None, "blacklist_kind": ""}        # resolver refused


def ipqs_lookup(ip, api_key, timeout=DEFAULT_TIMEOUT):
    """Query IPQualityScore for an IP. IPQS uses honeypot networks + real-time
    behavioral analysis (like Spur did), not just passive lists, so it catches
    live residential-proxy pools that IPinfo misses. We run it AGGRESSIVELY:
    strictness=2, no lighter penalties, and do NOT whitelist public access
    points - all of which maximize residential-proxy flagging. A detected proxy
    is the burnt signal, so we force its fraud score high if IPQS under-rates it.
    Returns a normalized dict or None."""
    url = ("https://ipqualityscore.com/api/json/ip/"
           f"{quote(api_key, safe='')}/{quote(ip, safe='')}"
           "?strictness=2&allow_public_access_points=false"
           "&lighter_penalties=false&fast=false")
    data = http_get_json(url, timeout)
    if not isinstance(data, dict) or not data.get("success", False):
        return None
    is_proxy = bool(data.get("proxy"))
    fraud = data.get("fraud_score")
    # A detected proxy that IPQS scored soft still means "seen proxying" -> burnt.
    if is_proxy and isinstance(fraud, (int, float)) and fraud < 85:
        fraud = 90
    return {
        "fraud_score": fraud,
        "connection_type": data.get("connection_type", ""),
        "recent_abuse": bool(data.get("recent_abuse")) or is_proxy,
        "bot_status": bool(data.get("bot_status")),
        "proxy": is_proxy,
        "vpn": bool(data.get("vpn")) or bool(data.get("active_vpn")),
        "tor": bool(data.get("tor")) or bool(data.get("active_tor")),
        "isp": data.get("ISP", "") or data.get("organization", ""),
        "country": data.get("country_code", ""),
        "flag_extra": (["proxy"] if is_proxy else []),
    }


def _trust_score(q):
    """Fold the reputation signals into a single 0-100 Trust score (higher is
    better). `proxy=True` is expected (these ARE proxies) so it isn't penalized;
    the discriminators are fraud score, connection type, abuse and blacklists."""
    fs = q.get("fraud_score")
    score = (100 - fs) if isinstance(fs, (int, float)) else 50
    ct = (q.get("connection_type") or "").lower()
    if any(k in ct for k in ("mobile", "wireless", "cellular")):
        score += 12
    elif "residential" in ct:
        score += 6
    elif any(k in ct for k in ("corporate", "business")):
        score -= 4
    elif any(k in ct for k in ("data center", "datacenter", "hosting")):
        score -= 25
    if q.get("recent_abuse"):
        score -= 15
    if q.get("bot_status"):
        score -= 15
    if q.get("vpn"):
        score -= 8
    if q.get("tor"):
        score -= 30
    if q.get("blacklisted") is True:
        # Weight by which Spamhaus sublist. XBL = compromised/botnet host
        # (genuinely burnt) tanks it; SBL = spam source is heavy; PBL =
        # dynamic/residential policy range is benign for web bot-detection but
        # still drops it out of a perfect green score. Unknown zone: moderate.
        kind = (q.get("blacklist_kind") or "").upper()
        if "XBL" in kind:
            score -= 55
        elif "SBL" in kind:
            score -= 40
        elif "PBL" in kind:
            score -= 15
        else:
            score -= 25
    lat = q.get("latency_ms")
    if isinstance(lat, (int, float)) and lat > 2500:
        score -= 5
    return max(0, min(100, int(round(score))))


# proxycheck.io's documented per-second limits (API docs, "Service Limits"):
#   NA 875 soft / 1,000 hard - EU/Africa 1,225 soft / 1,400 hard -
#   Asia/Oceania 700 soft / 800 hard (per-account, same for free and paid).
# We don't know which region a given account routes to, so pace to the most
# conservative region's soft limit with headroom, rather than guess a thread
# count and hope. This means CONCURRENCY (how many callers can be in flight)
# can be raised freely - actual req/s is capped here, not by thread count.
PROXYCHECK_RATE_PER_SEC = 500
_proxycheck_limiter = _RateLimiter(PROXYCHECK_RATE_PER_SEC)


def proxycheck_lookup(ip, api_key, timeout=DEFAULT_TIMEOUT):
    """Query proxycheck.io for an IP. Cheap/high-volume alternative to IPQS
    (1,000/day free). Returns a normalized dict (same shape as ipqs_lookup).
    Uses the v2 endpoint - proxycheck's v3 (announced Aug 2025) restructures
    the response into nested network/detections/operator sections; v2 stays
    supported until 2035, and v3's exact schema needs verifying against a live
    key before the parser is rewritten to it, so this isn't a blind migration."""
    _proxycheck_limiter.wait()
    url = ("https://proxycheck.io/v2/" + quote(ip, safe="")
           + "?key=" + quote(api_key, safe="") + "&vpn=1&asn=1&risk=1")
    data = http_get_json(url, timeout)
    if not isinstance(data, dict) or data.get("status") != "ok":
        return None
    rec = data.get(ip)
    if not isinstance(rec, dict):
        return None
    ptype = rec.get("type") or ""
    low = ptype.lower()
    try:
        risk = int(rec.get("risk")) if rec.get("risk") is not None else None
    except (TypeError, ValueError):
        risk = None
    return {
        "fraud_score": risk,                 # proxycheck 'risk' 0-100 ~ fraud
        "connection_type": ptype,            # Residential/Wireless/Business/...
        "proxy": rec.get("proxy") == "yes",
        "vpn": "vpn" in low,
        "tor": "tor" in low,
        "recent_abuse": False,
        "bot_status": False,
        "isp": rec.get("provider", "") or rec.get("organisation", ""),
        "country": rec.get("isocode", ""),
    }


def _ipinfo_parse(data):
    """Turn one IPinfo record into our score dict. Tolerant of BOTH schemas:
    the newer /lookup//batch shape (anonymous/as/mobile, with is_res_proxy,
    is_anycast, is_satellite - confirmed against IPinfo's own Batch Enrichment
    API docs) and the classic legacy shape (privacy/asn|company/carrier). Either
    way we pull the same proxy/vpn/tor/relay/hosting/mobile/anycast/satellite
    signals."""
    if not isinstance(data, dict):
        return {"_error": "IPinfo: no data"}
    # anonymous (new) vs privacy (classic)
    anon_o = data.get("anonymous") if isinstance(data.get("anonymous"), dict) \
        else (data.get("privacy") if isinstance(data.get("privacy"), dict)
              else {})
    # as (new) vs asn / company (classic)
    as_o = data.get("as") if isinstance(data.get("as"), dict) else (
        data.get("asn") if isinstance(data.get("asn"), dict) else (
            data.get("company") if isinstance(data.get("company"), dict)
            else {}))
    geo_o = data.get("geo") if isinstance(data.get("geo"), dict) else {}
    mob_o = data.get("mobile") if isinstance(data.get("mobile"), dict) else (
        data.get("carrier") if isinstance(data.get("carrier"), dict) else {})

    def _b(*keys):
        # First truthy value across new/classic key spellings.
        for k in keys:
            if anon_o.get(k):
                return True
        return False

    vpn = _b("is_vpn", "vpn")
    proxy = _b("is_proxy", "proxy")
    tor = _b("is_tor", "tor")
    relay = _b("is_relay", "relay")
    res_proxy = _b("is_res_proxy", "res_proxy")
    hosting = bool(data.get("is_hosting")) or _b("hosting")
    is_mobile = bool(data.get("is_mobile")) or bool(mob_o.get("carrier")
                                                    or mob_o.get("name"))
    # An anycast IP is never a genuine home connection - it's always CDN/global-
    # accelerator/infra address space, even on ranges not flagged 'hosting'.
    # A "residential" exit sitting on anycast space is close to a hard tell.
    is_anycast = bool(data.get("is_anycast"))
    # Satellite ISPs (Starlink etc.) are legitimate consumer connections, but
    # behave very differently - much higher/variable latency, coarse geo,
    # often CGNAT-shared - so they get their own Type rather than hiding inside
    # generic Residential/ISP.
    is_satellite = bool(data.get("is_satellite"))
    # 'name' is the confirmed new-schema field for a detected proxy/VPN/resi-
    # proxy service; keep the older guesses too in case a legacy record uses
    # them.
    service = str(anon_o.get("name") or anon_o.get("service")
                  or anon_o.get("res_proxy_service") or "").strip()
    carrier_name = str(mob_o.get("carrier") or mob_o.get("name") or "").strip()
    # When IPinfo last confirmed a positive detection - lets you weigh a flag
    # seen yesterday differently from one seen a year ago.
    last_seen = str(anon_o.get("last_seen") or "").strip()
    hostname = str(data.get("hostname") or "").strip()

    # Confirmed real values (IPinfo's own Batch Enrichment API examples):
    # isp, business, hosting, education, government. There is no 'residential'
    # value - a residential/ISP exit is inferred from org_type=='isp' plus no
    # anonymity flags.
    org_type = (as_o.get("type") or "").lower()
    anon = res_proxy or proxy or vpn or tor or relay
    if res_proxy or proxy:
        fraud = 90                      # a proxy exit -> burnt
    elif vpn or tor or relay:
        fraud = 85
    elif org_type == "government":
        # There is essentially no legitimate retail-shopper traffic from a
        # government/.mil-type network. A "residential" proxy exiting here is
        # almost certainly a compromised/hijacked host being used as an
        # unauthorized relay, not a real consumer. Previously fell through to
        # clean-Residential (fraud 5), which was simply wrong.
        fraud = 80
    elif org_type == "education":
        # Softer than government: a university/dorm connection CAN be a real
        # student's genuine home-like internet (some bandwidth-sharing SDKs
        # legitimately harvest exactly this kind of connection) - a student
        # buying a graphics card is a real shopper, not a fraud signal. Still
        # flagged, mildly, because it means the provider's "residential" pool
        # includes non-consumer-ISP address space, which is worth knowing -
        # just not treated as risky as an actual VPN/proxy/government exit.
        fraud = 35
    elif hosting or org_type == "hosting":
        fraud = 60                      # datacenter / hosting
    else:
        fraud = 5                       # clean residential / ISP / mobile
    if is_anycast:
        # Independent hard floor - anycast overrides a lower score from any
        # branch above, but never LOWERS a worse one (e.g. res_proxy + anycast
        # stays at least this bad).
        fraud = max(fraud, 95)
    if res_proxy:
        conn = "Residential proxy"
    elif is_mobile:
        conn = "Mobile"
    elif hosting or org_type == "hosting":
        conn = "Datacenter"
    elif org_type == "government":
        conn = "Government"
    elif org_type == "education":
        conn = "Education"
    elif is_satellite:
        conn = "Satellite"
    elif org_type == "isp":
        conn = "Residential/ISP"
    elif org_type == "business":
        conn = "Business"
    else:
        conn = "Proxy" if anon else "Residential"
    org = (as_o.get("name") or data.get("org") or "")
    extra = []
    if res_proxy:
        extra.append("residential proxy")
    if is_anycast:
        extra.append("anycast")
    if service:
        extra.append(service.lower())
    if carrier_name:
        extra.append(carrier_name.lower())
    if anon and last_seen:
        # Only meaningful attached to an actual positive detection - a clean
        # IP has no 'last seen doing something bad' to report.
        extra.append(f"seen {last_seen}")
    if org_type == "isp" and not is_mobile and not anon and not hostname:
        # Weak, non-scored anomaly: genuine WIRED residential ISPs almost
        # always have descriptive rDNS (pool-x.isp.net etc.), so a bare
        # ISP-typed IP with none is a mild oddity worth a soft tag. Excluded
        # for mobile: cellular CGNAT gateways commonly have no rDNS at all as
        # a normal thing, so the same absence there carries no signal.
        extra.append("no rdns")
    return {
        "fraud_score": fraud,
        "connection_type": conn,        # Mobile / Residential proxy / DC / ...
        "proxy": anon,
        "vpn": vpn,
        "tor": tor,
        "recent_abuse": res_proxy or proxy or is_anycast,
        "bot_status": False,
        "isp": org,
        "hostname": hostname,
        "country": geo_o.get("country_code") or geo_o.get("country", ""),
        "flag_extra": list(dict.fromkeys(extra)),   # deduped, order-preserved
    }


def ipinfo_lookup(ip, token, timeout=DEFAULT_TIMEOUT):
    """Single-IP lookup via api.ipinfo.io/lookup (Bearer auth). Kept for the
    fused engine and as the fallback when a batch entry is missing."""
    data, err = http_get_json_ex(
        "https://api.ipinfo.io/lookup/" + quote(ip, safe=""),
        timeout, extra_headers={"Authorization": "Bearer " + token})
    if err or not isinstance(data, dict):
        return {"_error": f"IPinfo: {err or 'no data'}"}
    return _ipinfo_parse(data)


IPINFO_BATCH_MAX = 1000     # IPinfo's documented per-call cap


def ipinfo_batch(ips, token, timeout=DEFAULT_TIMEOUT):
    """Look up many IPs in ONE POST to api.ipinfo.io/batch (up to 1000 per
    call). This is the fix for stage-2 socket exhaustion: instead of one direct
    connection per IP - which drowned the local machine on 10k+ runs - a whole
    chunk resolves over a single connection. Returns {ip: score_dict}; any IP
    the batch didn't answer is simply absent, so the caller can fall back.
    On a transport/HTTP error every IP maps to an {'_error': ...} dict."""
    ips = list(ips)
    if not ips:
        return {}
    url = "https://api.ipinfo.io/batch?token=" + quote(token, safe="")
    body = json.dumps(ips).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"User-Agent": USER_AGENT,
                     "Content-Type": "application/json"})
        opener = (urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=SSL_CTX)) if SSL_CTX
            else urllib.request.build_opener())
        # Batches are bigger than a single lookup - give them more headroom.
        with opener.open(req, timeout=max(timeout, 60)) as resp:
            raw = resp.read().decode("utf-8", "replace")
        obj = json.loads(raw)
    except urllib.error.HTTPError as e:
        return {ip: {"_error": f"IPinfo: HTTP {e.code}"} for ip in ips}
    except socket.timeout:
        return {ip: {"_error": "IPinfo: timeout"} for ip in ips}
    except Exception:
        return {ip: {"_error": "IPinfo: network"} for ip in ips}
    if not isinstance(obj, dict):
        return {ip: {"_error": "IPinfo: bad batch response"} for ip in ips}
    # Keys come back as the IP (bare-IP input). Be lenient: also match a value
    # that carries its own 'ip' field, in case the endpoint keys differently.
    out = {}
    for ip in ips:
        rec = obj.get(ip)
        if isinstance(rec, dict):
            out[ip] = _ipinfo_parse(rec)
    if len(out) < len(ips):
        for rec in obj.values():
            if isinstance(rec, dict) and rec.get("ip") in ips \
                    and rec["ip"] not in out:
                out[rec["ip"]] = _ipinfo_parse(rec)
    return out


IPINFO_BATCH_CONCURRENCY = 8   # chunks in flight at once (each POST holds up to
                              # 1000 IPs, so even a few thousand unique IPs is
                              # only a handful of chunks - no need for more)


def ipinfo_batch_all(ips, token, timeout=DEFAULT_TIMEOUT):
    """Resolve every IP via IPinfo's batch endpoint, chunked at
    IPINFO_BATCH_MAX and run CONCURRENTLY across chunks - a single-IPinfo-
    provider run used to walk its chunks one POST at a time, which serialized a
    50k-unique-IP run into 50 sequential round trips for no reason (chunks are
    independent). Falls back to a single lookup for any IP a chunk didn't
    answer. Returns {ip: score_dict} for every input IP."""
    ips = list(dict.fromkeys(ips))     # de-dup, preserve order
    if not ips:
        return {}
    chunks = [ips[i:i + IPINFO_BATCH_MAX]
              for i in range(0, len(ips), IPINFO_BATCH_MAX)]
    out = {}
    with ThreadPoolExecutor(
            max_workers=max(1, min(IPINFO_BATCH_CONCURRENCY, len(chunks)))
    ) as pool:
        futs = {pool.submit(ipinfo_batch, c, token, timeout): c
                for c in chunks}
        for fut, c in futs.items():
            try:
                got = fut.result()
            except Exception:
                got = {}
            for ip in c:
                out[ip] = got.get(ip) or ipinfo_lookup(ip, token, timeout)
    return out


# The aggregate runs EVERY configured provider concurrently and fuses their
# signals into one Trust score - so no single vendor's blind spots decide it.
AGGREGATE_PROVIDER = "All providers (fused)"

# Supported IP-reputation providers. The key for each lives in settings.json
# (entered on the Settings tab), never in code. The aggregate has a None lookup
# - score_ip handles it by running all the keyed providers below.
QUALITY_PROVIDERS = {
    AGGREGATE_PROVIDER: ("", None),
    "proxycheck.io": ("proxycheck_api_key", proxycheck_lookup),
    "IPinfo": ("ipinfo_token", ipinfo_lookup),
    "IPQualityScore": ("ipqs_api_key", ipqs_lookup),
}


def _merge_signals(dicts):
    """Fuse several detector results into one signal dict for the Trust score:
    booleans OR together (any provider flagging proxy/vpn/abuse wins), fraud is
    the most-pessimistic (max), flags are unioned, and the connection type
    prefers the most informative label (IPinfo's residential/mobile/ISP over a
    generic 'Proxy'), tagged '<type> proxy' when any provider flags a proxy."""
    merged, fraud, flags = {}, None, []
    for d in dicts:
        for k, v in (d or {}).items():
            if k == "fraud_score":
                if isinstance(v, (int, float)):
                    fraud = v if fraud is None else max(fraud, v)
            elif k == "flag_extra":
                flags += (v or [])
            elif k in ("proxy", "vpn", "tor", "recent_abuse", "bot_status"):
                merged[k] = bool(merged.get(k)) or bool(v)
            elif k == "blacklisted":
                if v is True:
                    merged[k] = True
                elif merged.get(k) is None:
                    merged[k] = v
            elif k == "connection_type":
                pass                    # handled below (pick the best label)
            elif v and not merged.get(k):
                merged[k] = v           # isp, country, _error - first non-empty
    if fraud is not None:
        merged["fraud_score"] = fraud
    merged["flag_extra"] = list(dict.fromkeys(flags))
    types = [d.get("connection_type") for d in dicts
             if (d or {}).get("connection_type")]
    ct = next((t for t in types if t.lower() != "proxy"),
              (types[0] if types else ""))
    if merged.get("proxy") and ct and "proxy" not in ct.lower():
        ct = ct + " proxy"
    merged["connection_type"] = ct
    return merged


def discover_exit_ip(proxy, timeout=DEFAULT_TIMEOUT, stop_event=None):
    """Route through a proxy to learn its public exit IP (and latency). This is
    the only step that touches your proxy credentials - they go to the proxy
    server only, never to any reputation API."""
    host, port = proxy["host"], proxy["port"]
    user, pw = proxy["user"], proxy["pw"]
    display = (f"{host}:{port}:{user}:****" if user and pw is not None
               else f"{host}:{port}")
    full = (f"{host}:{port}:{user}:{pw}" if user and pw is not None
            else (f"{host}:{port}:{user}" if user else f"{host}:{port}"))
    out = {"proxy": display, "full": full, "exit_ip": "", "ping": None,
           "status": "stopped"}
    if stop_event is not None and stop_event.is_set():
        return out
    r = do_request(build_proxy_url(host, port, user, pw), IPINFO_URL, timeout)
    if not r["ok"]:
        return {**out, "status": response_label(r)}
    ip = _parse_json_field(r["body"], "ip")
    if not ip:
        return {**out, "status": "no exit ip"}
    return {**out, "exit_ip": ip, "ping": r["ms"], "status": "OK"}


def _configured_lookups():
    """(name, lookup, key) for every keyed provider that currently has a key
    set - i.e. everything the aggregate should run. Excludes the aggregate
    entry itself (lookup is None)."""
    out = []
    for name, (key_setting, lookup) in QUALITY_PROVIDERS.items():
        if lookup is None:
            continue
        key = load_setting(key_setting, "").strip() if key_setting else ""
        if key or not key_setting:
            out.append((name, lookup, key))
    return out


class _ProviderBreaker:
    """Per-run failure tracker for the aggregate. After `threshold` failures a
    provider is disabled for the rest of the run, so a dead / keyless / rate-
    limited provider isn't retried on every IP. Thread-safe (scoring is
    concurrent)."""

    def __init__(self, threshold=4):
        self.threshold = threshold
        self._lock = threading.Lock()
        self._fail, self._ok, self.disabled = {}, {}, {}

    def active(self, name):
        return name not in self.disabled

    def record(self, name, ok, err=""):
        with self._lock:
            if ok:
                self._fail[name] = 0
                self._ok[name] = self._ok.get(name, 0) + 1
            else:
                self._fail[name] = self._fail.get(name, 0) + 1
                if name not in self.disabled \
                        and self._fail[name] >= self.threshold:
                    self.disabled[name] = err or "failed"

    def summary(self):
        out = []
        for name in set(self._ok) | set(self._fail) | set(self.disabled):
            if name in self.disabled:
                out.append(f"{name}: {self.disabled[name]} (stopped)")
            elif self._ok.get(name):
                out.append(f"{name}: ok")
            else:
                out.append(f"{name}: failing")
        return out


def score_ip(ip, provider, api_key, timeout=DEFAULT_TIMEOUT, breaker=None,
             precomputed=None):
    """Score one exit IP: free Spamhaus check + provider signal(s). Only the
    public IP is sent to a provider - never any credential. The aggregate runs
    EVERY configured provider concurrently and fuses them (skipping any the
    breaker has disabled, or any provider already resolved via `precomputed` -
    IPinfo's batch endpoint pre-fetches every unique IP up front for fused runs
    too, so it never needs a live per-IP call here); a single provider runs
    just that one."""
    if provider == AGGREGATE_PROVIDER:
        pre = precomputed or {}
        tasks = [("_spamhaus", lambda: spamhaus_lookup(ip))]
        for name, lookup, key in _configured_lookups():
            if name in pre:
                continue                # already resolved via batch
            if breaker and not breaker.active(name):
                continue
            tasks.append((name, lambda lk=lookup, k=key: lk(ip, k, timeout)))
        results = list(pre.values())
        for name, r in pre.items():
            if breaker:
                breaker.record(name, bool(r) and not (r or {}).get("_error"),
                               (r or {}).get("_error", ""))
        with ThreadPoolExecutor(max_workers=max(2, len(tasks))) as pool:
            futs = {pool.submit(fn): name for name, fn in tasks}
            for fut in futs:
                name = futs[fut]
                try:
                    r = fut.result() or {}
                except Exception as e:
                    r = {"_error": str(e)[:40]}
                if breaker and name != "_spamhaus":
                    breaker.record(name, bool(r) and not r.get("_error"),
                                   r.get("_error", ""))
                results.append(r)
        return _merge_signals(results)
    q = spamhaus_lookup(ip)
    key_setting, lookup = QUALITY_PROVIDERS.get(provider, ("", None))
    if lookup and (api_key or not key_setting):
        q.update(lookup(ip, api_key, timeout) or {})
    return q


# --- Pool overlap (white-label / shared-pool detection) ----------------------
# Different proxy brands often resell the SAME underlying pool. When two of your
# providers hand back the SAME exit IP, you are renting one IP twice - paying
# twice, and burning it twice as fast against a target that tracks IP history.
# We already resolve every exit IP in stage 1, so this costs nothing extra.
PROVIDER_HOSTS = (
    ("proxy-haus", "Proxy-Haus"),
    ("oxylabs", "Oxylabs"),
    ("rayobyte", "Rayobyte"),
    ("iproyal", "IPRoyal"),
    ("lum-superproxy", "Bright Data"),
    ("luminati", "Bright Data"),
    ("superproxy", "Bright Data"),
    ("smartproxy", "Smartproxy"),
    ("decodo", "Decodo"),
    ("netnut", "NetNut"),
    ("packetstream", "PacketStream"),
    ("geonode", "Geonode"),
    ("massive", "Massive"),
    ("soax", "SOAX"),
    ("nodemaven", "NodeMaven"),
    ("liveproxies", "Live Proxies"),
    ("live-proxies", "Live Proxies"),
    ("ntnt.vip", "ThuProxy (NetNut)"),
    ("fresi.hellworld", "F-Private"),      # more specific first
    ("hellworld", "Hell World"),
)


def proxy_full_key(line):
    """Canonical host:port:user:pass key for a proxy line (password included, so
    session-in-password proxies are told apart). None if unparseable."""
    p = parse_proxy_line(str(line))
    if not p:
        return None
    if p.get("user") and p.get("pw") is not None:
        return f"{p['host']}:{p['port']}:{p['user']}:{p['pw']}"
    return f"{p['host']}:{p['port']}"


# A label line - '# F-Oxylab', '// Oxylab', or '[Oxylab]' - names every proxy
# below it until the next label. Needed because resellers serve many different
# products from ONE hostname, so the host alone can't tell two SKUs apart.
_GROUP_LABEL_RE = re.compile(r"^\s*(?:#+|//)\s*(.+?)\s*$|^\s*\[\s*(.+?)\s*\]\s*$")


def group_label_of(line):
    """Return the group label a line declares, or None if it's not a label."""
    s = (line or "").strip()
    if not s or parse_proxy_line(s):        # a real proxy is never a label
        return None
    m = _GROUP_LABEL_RE.match(s)
    if not m:
        return None
    label = (m.group(1) or m.group(2) or "").strip()
    return label or None


def parse_labeled_proxies(text):
    """Split a proxy list into (parsed_proxies, {full_key: label}, bad_count).
    Label lines ('# Oxylab') tag everything beneath them so two SKUs bought from
    the same reseller host can still be compared against each other."""
    proxies, labels, bad = [], {}, 0
    current = None
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        lab = group_label_of(line)
        if lab is not None:
            current = lab
            continue
        parsed = parse_proxy_line(line)
        if not parsed:
            bad += 1
            continue
        proxies.append(parsed)
        if current:
            key = proxy_full_key(line)
            if key:
                labels.setdefault(key, current)
    return proxies, labels, bad


def provider_of_host(host):
    """Best-effort provider label for a proxy host, used to group exits by pool.
    Unknown hosts fall back to their registrable-looking domain so a provider we
    don't have a name for still groups with itself."""
    h = (host or "").strip().lower()
    for needle, label in PROVIDER_HOSTS:
        if needle in h:
            return label
    parts = [p for p in h.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return h or "unknown"


def compute_pool_overlap(discoveries, labels=None):
    """Group resolved exit IPs by provider and find the IPs served by MORE THAN
    ONE provider - the signature of two brands reselling the same pool.

    `labels` maps a proxy's full key to an explicit group name, which WINS over
    the hostname. That's what lets two SKUs from one reseller (same host,
    different product) be compared against each other.

    Returns a dict. `shared` is empty when there is nothing to report (only one
    provider in the list, or no collisions), which is the silent/normal case."""
    labels = labels or {}
    by_ip, per_provider = {}, {}
    for d in discoveries:
        ip = d.get("exit_ip")
        if not ip:
            continue
        prov = (labels.get(d.get("full") or "")
                or provider_of_host((d.get("proxy") or "").split(":")[0]))
        by_ip.setdefault(ip, set()).add(prov)
        per_provider.setdefault(prov, set()).add(ip)
    shared = {ip: sorted(ps) for ip, ps in by_ip.items() if len(ps) > 1}
    pairs = {}
    for ps in shared.values():
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                key = (ps[i], ps[j])
                pairs[key] = pairs.get(key, 0) + 1
    return {
        "shared": shared,
        "pairs": pairs,
        "per_provider": {p: len(ips) for p, ips in per_provider.items()},
        "providers": sorted(per_provider),
        "unique_ips": len(by_ip),
    }


def overlap_summary(ov):
    """One-line human summary of an overlap result, or '' when there's nothing
    to say (single provider, or no shared IPs)."""
    shared, uniq = ov.get("shared") or {}, ov.get("unique_ips") or 0
    if not shared or len(ov.get("providers") or []) < 2:
        return ""
    pct = (100.0 * len(shared) / uniq) if uniq else 0.0
    top = sorted(ov["pairs"].items(), key=lambda kv: -kv[1])[:3]
    detail = "; ".join(f"{a} + {b}: {n}" for (a, b), n in top)
    return (f"Pool overlap: {len(shared)} of {uniq} exit IPs ({pct:.1f}%) came "
            f"back from 2+ providers - {detail}")


def build_quality_row(disc, q, has_key):
    """Combine an exit-IP discovery with its reputation score into a table row."""
    display = disc["proxy"]
    full = disc.get("full", display)
    if disc["status"] != "OK":
        return {"proxy": display, "full": full, "exit_ip": "", "fraud": "",
                "type": "", "flags": "", "blacklist": "", "ping": None,
                "trust": None, "status": disc["status"]}
    q = dict(q)
    q["latency_ms"] = disc["ping"]
    flags = [name for name, on in (
        ("abuse", q.get("recent_abuse")), ("bot", q.get("bot_status")),
        ("vpn", q.get("vpn")), ("tor", q.get("tor"))) if on]
    # Provider-supplied detail (e.g. IPinfo's residential-proxy service name).
    flags += [f for f in (q.get("flag_extra") or []) if f and f not in flags]
    bl = q.get("blacklisted")
    kind = q.get("blacklist_kind") or ""
    fs = q.get("fraud_score")
    err = q.get("_error")
    return {
        "proxy": display,
        "full": full,
        "exit_ip": disc["exit_ip"],
        "fraud": "" if fs is None else str(fs),
        "type": (q.get("connection_type", "")
                 or (err if err else ("-" if has_key else "no key"))),
        "flags": ",".join(flags),
        # Show which sublist (XBL/SBL/PBL) when known, else generic 'listed'.
        "blacklist": (kind or "listed") if bl is True else (
            "clean" if bl is False else "-"),
        "ping": disc["ping"],
        "trust": _trust_score(q),
        "status": "OK",
    }


# --------------------------------------------------------------------------- #
# Profile persistence (JSON in the user's config dir)
# --------------------------------------------------------------------------- #
def _config_dir():
    """Per-user config folder, in each platform's normal place."""
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA") or home, "ProxyTester")
    if sys.platform == "darwin":
        path = os.path.join(home, "Library", "Application Support",
                            "ProxyTester")
    else:
        path = os.path.join(
            os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
            "ProxyTester")
    # Older builds put this straight in the home folder; keep using that if it's
    # already there so an existing install doesn't lose its saved settings.
    legacy = os.path.join(home, "ProxyTester")
    if os.path.isdir(legacy) and not os.path.isdir(path):
        return legacy
    return path


def _install_dir():
    """Folder the app runs from: next to the .exe when frozen, else the source."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _exports_dir():
    """An 'exports' folder inside the install dir; created on demand. Falls back
    to the config dir if the install dir isn't writable."""
    for base in (_install_dir(), _config_dir()):
        path = os.path.join(base, "exports")
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError:
            continue
    return _install_dir()


class ProfileStore:
    """Named credential/input profiles, saved to disk so they persist."""

    def __init__(self):
        self.path = os.path.join(_config_dir(), "profiles.json")
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _flush(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass

    def names(self):
        return sorted(self.data.keys())

    def get(self, name):
        return self.data.get(name)

    def save(self, name, state):
        self.data[name] = state
        self._flush()

    def delete(self, name):
        self.data.pop(name, None)
        self._flush()


def load_setting(key, default=""):
    """Read one app-wide setting (e.g. the IPQS API key) from settings.json."""
    try:
        with open(os.path.join(_config_dir(), "settings.json"),
                  "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(key, default) if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def save_setting(key, value):
    """Persist one app-wide setting to settings.json (best effort)."""
    path = os.path.join(_config_dir(), "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[key] = value
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


MAX_WORKERS_CAP = 500  # upper clamp. proxycheck.io load-balances one hostname
                       # across ~14 cluster nodes (200 req/s EACH => ~2,800/s
                       # aggregate), and IPinfo paid is unthrottled, so hundreds
                       # of concurrent workers are absorbed without targeting
                       # individual nodes. Threads are the real cost at this end.


def get_workers():
    """Concurrency for the full-GET / exit-IP path. Hard-coded at the cap for
    maximum throughput - the full path does TLS+GET+body, and 500 concurrent is
    the sweet spot before per-thread cost and provider-side limits bite. Not
    user-tunable: there's no setting that beats 'as fast as it safely goes'."""
    return MAX_WORKERS_CAP


# The connect-only liveness path (ProxyTab "Liveness (fast)" mode) does one
# CONNECT handshake per proxy - no TLS-to-target, no GET, no body - so it can
# run far wider than the full-GET cap. Capped conservatively: past ~1500 you're
# GIL/context-switch-bound and hit ephemeral-port/TIME_WAIT churn on Windows.
FAST_WORKERS_CAP = 1200
FAST_MIN_WORKERS = 200
FAST_MODE = "Liveness (fast)"
FULL_MODE = "Full (exit IP + geo)"
DEFAULT_FAST_TIMEOUT = 5      # seconds - a CONNECT is one RTT; 5s spares slow
                             # residential/mobile gateways without holding a
                             # dead proxy for the full 15s.


def get_fast_workers():
    """Worker count for the connect-only liveness path. Hard-coded at the cap -
    a CONNECT handshake is cheap enough to run this wide, and it's the whole
    point of the fast mode. Not user-tunable."""
    return FAST_WORKERS_CAP


def get_fast_timeout():
    """Connect timeout (seconds) for the liveness path. Hard-coded: 5s is long
    enough not to false-kill slow residential/mobile gateways, short enough that
    dead proxies don't hold a worker. Not user-tunable."""
    return DEFAULT_FAST_TIMEOUT


# Reputation-lookup concurrency (IP Quality stage 2), for whatever providers
# AREN'T resolved via a batch endpoint - IPinfo now pre-fetches via
# ipinfo_batch_all regardless of provider mode (fused or solo), so this pool
# mainly carries spamhaus + proxycheck.io + IPQS. It used to be capped at 100
# specifically to protect unbatched IPinfo from local socket exhaustion; now
# that IPinfo is batched, the real limit is proxycheck.io's documented
# per-second cap (700-1,400 req/s depending on region - see
# PROXYCHECK_RATE_PER_SEC), which is enforced by its own rate limiter
# regardless of how many threads call it. So concurrency here can be generous.
DEFAULT_SCORE_WORKERS = 400


def get_score_workers():
    """Concurrency for the IP-Quality REPUTATION-lookup stage (stage 2), for
    providers not already resolved via a batch endpoint. Not user-tunable -
    see DEFAULT_SCORE_WORKERS for why this number is safe."""
    return DEFAULT_SCORE_WORKERS


def split_creds(value):
    """Split a 'user:pass' string into (user, pass) on the FIRST colon, so a
    password containing colons stays intact. Returns ('', '') if empty."""
    value = (value or "").strip()
    if ":" in value:
        u, p = value.split(":", 1)
        return u.strip(), p.strip()
    return value, ""


def _cred_warning(value):
    """A short warning if a provider 'username:password' entry looks malformed
    (missing the colon, or a space in the username where an underscore likely
    belongs), else ''. Shown inline in Settings as you type."""
    v = (value or "").strip()
    if not v:
        return ""
    if ":" not in v:
        return "⚠ add a ':' between username and password"
    user = v.split(":", 1)[0]
    if " " in user:
        return "⚠ username has a space - did you mean '_'?"
    return ""


def load_provider_creds(key, legacy=None):
    """A provider's (user, pass). Prefers the combined 'user:pass' stored under
    `key`; falls back to legacy (user_key, pass_key) settings for migration."""
    combined = load_setting(key, "").strip()
    if combined:
        return split_creds(combined)
    if legacy:
        return (load_setting(legacy[0], "").strip(),
                load_setting(legacy[1], "").strip())
    return "", ""


def provider_creds_display(key, legacy=None):
    """The 'user:pass' string to prefill a Settings box (migrates legacy)."""
    u, p = load_provider_creds(key, legacy)
    return f"{u}:{p}" if (u or p) else ""


# --------------------------------------------------------------------------- #
# Provider rules
# --------------------------------------------------------------------------- #
# Each provider knows: its default host/port, and how to turn your account
# username + an ASN into a proxy auth username.  Pass sessid=None for a
# ROTATING proxy (new IP per request); pass a sessid for a sticky session
# (used internally when sampling during a test).
#
# To add a provider later: write a build_username(user, asn, sessid) function
# and add one entry to PROVIDERS. That's the only change needed.

def _oxylabs_username(user, asn, sessid=None, sesstime=None):
    # Oxylabs mobile. The account username needs a "customer-" prefix. The ASN
    # itself pins the (US) carrier, and Oxylabs ignores ASN if a country param
    # is also set, so we deliberately do NOT add cc-us. No sessid => rotating;
    # sessid (+ optional sesstime minutes) => sticky session.
    base = user if user.startswith("customer-") else f"customer-{user}"
    name = f"{base}-ASN-{asn}"
    if sessid:
        name += f"-sessid-{sessid}"
        if sesstime:
            name += f"-sesstime-{sesstime}"
    return name


def _proxyhaus_asn_username(user, asn, sessid=None, sesstime=None):
    # Proxy-Haus. The account username is the package name; the carrier is
    # pinned with -asn-<n>. sessid => sticky (-session-<tok>-ttl-<min>,
    # ttl defaults to 10 for a fresh sample).
    name = f"{user}-country-us-asn-{asn}"
    if sessid:
        name += f"-session-{sessid}-ttl-{sesstime or 10}"
    return name


PROVIDERS = {
    "Oxylabs": {"host": "pr.oxylabs.io", "port": "7777",
                "build": _oxylabs_username, "creds": "oxylabs_mobile",
                "max_min": 1440},
    "Proxy-Haus": {"host": "us-gw.proxy-haus.com", "port": "7777",
                   "build": _proxyhaus_asn_username, "creds": "proxyhaus",
                   "max_min": 120},
}

# Proxy-Haus only supports these carrier ASNs (US). When Proxy-Haus is the ASN
# Tester provider, the ASN list is restricted to exactly these.
PROXYHAUS_ASNS = [
    ("7018", "AT&T", "residential"),
    ("7922", "Comcast", "residential"),
    ("22773", "Cox", "residential"),
    ("21928", "T-Mobile", "mobile"),
    ("6167", "Verizon", "mobile"),
]


def build_username(provider, user, asn, sessid=None, sesstime=None):
    spec = PROVIDERS.get(provider) or next(iter(PROVIDERS.values()))
    return spec["build"](user, asn, sessid, sesstime)


def provider_hostport(provider):
    spec = PROVIDERS.get(provider)
    if spec:
        return spec["host"], spec["port"]
    return "", ""


# --------------------------------------------------------------------------- #
# Residential batch generation (client-side session-string construction).
# Nothing is fetched from an API: you make N distinct proxies by putting a
# unique random session token in each line (same token = same sticky IP).
# Credentials come from the Settings tab, never hard-coded.
# --------------------------------------------------------------------------- #
def _resi_sessid(n=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))


def _sessid_lower(n=8):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))


def _sessid_num(n=8):
    return "".join(random.choice(string.digits) for _ in range(n))


# Each builder shares one signature so the generator can call them uniformly:
#   (user, pw, state, city, lifetime_min, sessid, asn)
# lifetime_min is ALWAYS minutes (the generator's single shared unit); each
# builder renders it in the provider's own format. sessid=None => rotating (new
# IP per request); a sessid => sticky. asn is proxy-haus only.
def _build_oxylabs_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # pr.oxylabs.io: params live in the username; sticky via -sessid-/-sesstime-
    # (minutes, max 1440 = 24h).
    u = f"customer-{user}-cc-us"
    if state:
        u += f"-st-us_{state}"
    if city:
        u += f"-city-{city}"
    if sessid:
        u += f"-sessid-{sessid}"
        if lifetime:
            u += f"-sesstime-{lifetime}"
    return f"pr.oxylabs.io:7777:{u}:{pw}"


def _iproyal_lifetime(minutes):
    # IPRoyal encodes lifetime as '<=59m' or whole '<=168h'. Render minutes in
    # whichever fits: 59 or fewer stays minutes; more rounds to whole hours.
    if minutes <= 59:
        return f"{minutes}m"
    return f"{min(168, max(1, round(minutes / 60)))}h"


def _build_iproyal_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # geo.iproyal.com: params live in the password; '_streaming-1' always last.
    p = f"{pw}_country-us"
    if state:
        p += f"_state-{state}"
    if city:
        p += f"_city-{city}"
    if sessid:
        p += f"_session-{sessid}"
        if lifetime:
            p += f"_lifetime-{_iproyal_lifetime(lifetime)}"
    p += "_streaming-1"
    return f"geo.iproyal.com:12321:{user}:{p}"


def _build_brightdata_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # zproxy.lum-superproxy.com: params live in the username; sticky via
    # -session- (numeric token). No lifetime token - the IP holds inherently
    # (~30m max). The account username already carries the zone.
    u = f"{user}-dns-remote-country-US"
    if sessid:
        u += f"-session-{sessid}"
    return f"zproxy.lum-superproxy.com:32223:{u}:{pw}"


def _build_proxyhaus_resi(user, pw, state, city, lifetime, sessid, asn=None,
                          fresh=False):
    # us-gw.proxy-haus.com: params in the username; optional -asn-<n>, sticky via
    # -session-<tok>-ttl-<minutes> (ttl up to 120). `fresh` selects Proxy-Haus's
    # "Fresh" pool (freshly-added, less-used US IPs) via -pool-experimental1,
    # inserted right after the username - works with or without an ASN.
    u = user
    if fresh:
        u += "-pool-experimental1"
    u += "-country-us"
    if asn:
        u += f"-asn-{asn}"
    if sessid:
        u += f"-session-{sessid}-ttl-{lifetime or 10}"
    return f"us-gw.proxy-haus.com:7777:{u}:{pw}"


def _build_packetstream_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # proxy.packetstream.io: params live in the PASSWORD, underscore-delimited.
    # Country is CamelCase with no space ("UnitedStates"). Sticky adds
    # _session-<tok>; there is NO ttl/duration token - PacketStream pins the
    # sticky lifetime at its own maximum (~60 min) and it can't be lowered, so
    # `lifetime` is deliberately ignored here.
    p = f"{pw}_country-UnitedStates"
    if sessid:
        p += f"_session-{sessid}"
    return f"proxy.packetstream.io:31112:{user}:{p}"


def _build_hellworld_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # fresi.hellworld.io (Hell World's own "F-Private" pool): params live in the
    # USERNAME. Sticky adds -session-<tok>-time-<SECONDS> - note the unit: the
    # dashboard's "Session Duration (min)" of 10 emits time-600, so the
    # generator's minutes are converted here. Rotating is plain -country-us.
    u = f"{user}-country-us"
    if sessid:
        u += f"-session-{sessid}-time-{int(lifetime or 10) * 60}"
    return f"fresi.hellworld.io:10000:{u}:{pw}"


def _build_thuproxy_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # gw.ntnt.vip (ThuProxy, reselling NetNut): params live in the USERNAME.
    # Country is -cc-US (uppercase); sticky is -sid-<6 digits>. There is NO
    # duration token - a session holds for as long as you keep reusing the same
    # sid - so `lifetime` is deliberately ignored here.
    u = f"{user}-cc-US"
    if sessid:
        u += f"-sid-{sessid}"
    return f"gw.ntnt.vip:5959:{u}:{pw}"


def _build_rayobyte_resi(user, pw, state, city, lifetime, sessid, asn=None):
    # la.residential.rayobyte.com: params live in the PASSWORD. Rayobyte has no
    # rotating mode - it's ALWAYS a hardsession (sticky), so a token is always
    # emitted (varying it per line gives fresh IPs). Duration in minutes, max 60.
    sid = sessid or _sessid_lower(8)
    p = f"{pw}-country-US-hardsession-{sid}-duration-{lifetime or 60}"
    return f"la.residential.rayobyte.com:8000:{user}:{p}"


# Residential providers for the batch generator. `key` -> a combined
# 'user:pass' setting; `legacy` -> the old split keys, kept for migration.
# `max_min` is the hardcoded sticky-lifetime cap in MINUTES, ENFORCED (a request
# over it is refused, not silently clamped); None = provider has no lifetime
# token (Bright Data). `sessid` builds a session token in the provider's own
# style. `supports_asn` = proxy-haus.
# `max_min` is the hardcoded sticky cap in MINUTES. `min_max`/`hr_max` are the
# largest values each provider accepts in its minute-format vs whole-hour format
# (IPRoyal, e.g., only takes 1-59 in minutes but 1-168 in hours); `life_rule` is
# the human summary shown/enforced. Providers with max_min=None (Bright Data)
# have no lifetime token at all.
RESI_PROVIDERS = {
    "Oxylabs Residential": {
        "key": "oxylabs_resi",
        "legacy": ("oxylabs_resi_user", "oxylabs_resi_pass"),
        "build": _build_oxylabs_resi,
        "max_min": 1440, "min_max": 1440, "hr_max": 24,
        "life_rule": "1-1440m or 1-24h", "sessid": lambda: _sessid_num(10),
    },
    "IPRoyal": {
        "key": "iproyal",
        "legacy": ("iproyal_user", "iproyal_pass"),
        "build": _build_iproyal_resi,
        "max_min": 168 * 60, "min_max": 59, "hr_max": 168,
        "life_rule": "1-59m or 1-168h", "sessid": lambda: _resi_sessid(8),
    },
    "Bright Data": {
        "key": "brightdata",
        "legacy": None,
        "build": _build_brightdata_resi,
        "max_min": None, "sessid": lambda: _sessid_num(8),
    },
    "Proxy-Haus": {
        "key": "proxyhaus",
        "legacy": None,
        "build": _build_proxyhaus_resi,
        "max_min": 120, "min_max": 120, "hr_max": 2,
        "life_rule": "1-120m or 1-2h", "sessid": lambda: _sessid_lower(8),
        "supports_asn": True, "supports_fresh": True,
        # The Fresh pool allows a MUCH longer sticky session than the normal
        # pool (their generator caps Session TTL at 3600 min with Fresh on), so
        # the cap - and the rule text - swap when Fresh is ticked.
        "fresh_max_min": 3600, "fresh_min_max": 3600, "fresh_hr_max": 60,
        "fresh_life_rule": "1-3600m or 1-60h (Fresh)",
    },
    "Rayobyte": {
        "key": "rayobyte",
        "legacy": None,
        "build": _build_rayobyte_resi,
        "max_min": 60, "min_max": 60, "hr_max": 1,
        "life_rule": "1-60m (always sticky)", "sessid": lambda: _sessid_lower(8),
        # No rotating mode - always emit a hardsession, even in rotating runs.
        "always_session": True,
    },
    "PacketStream": {
        "key": "packetstream",
        "legacy": None,
        "build": _build_packetstream_resi,
        # PacketStream fixes the sticky lifetime at its own max (~60 min) and
        # offers no token to lower it - so, like Bright Data, no lifetime box.
        "max_min": None, "sessid": lambda: _resi_sessid(8),
        "life_note": "sticky lifetime fixed at PacketStream's max (~60m)",
    },
    # Hell World's own pool. Named for the product, not the vendor - that's what
    # it's called everywhere in their dashboard.
    "F-Private": {
        "key": "hellworld",
        "legacy": None,
        "build": _build_hellworld_resi,
        "max_min": 120, "min_max": 120, "hr_max": 2,
        "life_rule": "1-120m or 1-2h", "sessid": lambda: _sessid_lower(8),
    },
    "ThuProxy (NetNut)": {
        "key": "thuproxy",
        "legacy": None,
        "build": _build_thuproxy_resi,
        # No duration token exists - the sid IS the session, and it holds until
        # you use a different one. So, like Bright Data, no lifetime box.
        "max_min": None, "sessid": lambda: _sessid_num(6),
        "life_note": "no time token; the sid holds until you change it",
    },
}


def resi_life_caps(provider, fresh=False):
    """The sticky-lifetime limits in force for a provider right now, as
    (max_min, min_max, hr_max, rule_text). Proxy-Haus's Fresh pool allows a far
    longer session than its normal pool, so the caps swap when Fresh is on."""
    spec = RESI_PROVIDERS.get(provider, {})
    if fresh and spec.get("supports_fresh") and spec.get("fresh_max_min"):
        return (spec["fresh_max_min"], spec["fresh_min_max"],
                spec["fresh_hr_max"], spec.get("fresh_life_rule", ""))
    return (spec.get("max_min"), spec.get("min_max"), spec.get("hr_max"),
            spec.get("life_rule", ""))


def validate_resi_life(provider, raw, fresh=False):
    """Parse a per-provider sticky-lifetime entry and enforce that provider's
    real format rules. Returns (minutes, error). Rejects decimals, wrong units,
    and out-of-range values (so 0.5h, 90m on IPRoyal, or 169h never generate)."""
    spec = RESI_PROVIDERS.get(provider, {})
    if spec.get("max_min") is None:
        return None, None                 # no lifetime token (Bright Data)
    _mx, min_max, hr_max, rule = resi_life_caps(provider, fresh)
    s = (raw or "").strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d+)(m|min|mins|minutes|h|hr|hrs|hour|hours)?", s)
    if not m:
        return None, (f"{provider}: '{raw or '(blank)'}' isn't valid - enter a "
                      f"whole number of minutes or hours, e.g. 30m or 2h "
                      f"({rule}).")
    val = int(m.group(1))
    is_hr = (m.group(2) or "m").startswith("h")
    if val < 1:
        return None, f"{provider}: lifetime must be at least 1 ({rule})."
    if is_hr:
        if val > hr_max:
            return None, f"{provider}: max is {hr_max}h ({rule})."
        return val * 60, None
    if val > min_max:
        return None, (f"{provider}: {val}m is over the {min_max}m "
                      f"minute-format limit - use whole hours above that "
                      f"({rule}).")
    return val, None


def hidden_resi_providers():
    """Provider keys the user has switched OFF in Settings. Hiding is purely a
    display choice - the credentials stay saved, so flipping it back on needs no
    re-typing."""
    v = load_setting("hidden_providers", [])
    return set(v) if isinstance(v, (list, tuple, set)) else set()


def set_resi_provider_hidden(key, hidden):
    """Show/hide one provider in the batch generator, keeping its credentials."""
    cur = hidden_resi_providers()
    cur.discard(key) if not hidden else cur.add(key)
    save_setting("hidden_providers", sorted(cur))


def configured_resi_providers(include_hidden=False):
    """Providers that have both a username and password saved in settings, minus
    any the user has hidden in Settings (unless `include_hidden`)."""
    hidden = set() if include_hidden else hidden_resi_providers()
    out = []
    for name, spec in RESI_PROVIDERS.items():
        u, p = load_provider_creds(spec["key"], spec.get("legacy"))
        if u and p and spec["key"] not in hidden:
            out.append(name)
    return out


def _canon(name):
    return name.lower().replace(".", "").replace(" ", "_")


_US_STATE_NAMES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
]
_US_CITY_NAMES = [
    "Albuquerque", "Alpharetta", "Anaheim", "Arlington", "Ashburn", "Athens",
    "Atlanta", "Aurora", "Austin", "Bakersfield", "Baltimore", "Boston",
    "Buffalo", "Charlotte", "Chicago", "Cincinnati", "Cleveland",
    "Colorado Springs", "Columbus", "Dallas", "Denver", "Detroit", "El Paso",
    "Fort Worth", "Fresno", "Houston", "Indianapolis", "Jacksonville",
    "Kansas City", "Las Vegas", "Long Beach", "Los Angeles", "Louisville",
    "Memphis", "Mesa", "Miami", "Milwaukee", "Minneapolis", "Nashville",
    "New Orleans", "New York", "Newark", "Oakland", "Oklahoma City", "Omaha",
    "Orlando", "Philadelphia", "Phoenix", "Pittsburgh", "Portland", "Raleigh",
    "Richmond", "Sacramento", "Salt Lake City", "San Antonio", "San Diego",
    "San Francisco", "San Jose", "Seattle", "St Louis", "Tampa", "Tucson",
    "Tulsa", "Virginia Beach", "Washington",
]
US_STATES = [(_canon(n), n) for n in _US_STATE_NAMES]
US_CITIES = [(_canon(n), n) for n in sorted(_US_CITY_NAMES)]
REGION_OPTIONS = {"State": US_STATES, "City": US_CITIES}


def _fmt_minutes(m):
    """Human label for a minute count: '45m', '2h', '90m' -> '90m'."""
    if m % 60 == 0 and m >= 60:
        return f"{m // 60}h"
    return f"{m}m"


def resi_lifetime_error(provider, lifetime_min, fresh=False):
    """Return an error if `lifetime_min` (minutes) exceeds the provider's
    hardcoded sticky maximum, else None. Refused, never silently clamped."""
    spec = RESI_PROVIDERS.get(provider)
    if not spec or not lifetime_min:
        return None
    mx = resi_life_caps(provider, fresh)[0]
    if mx and lifetime_min > mx:
        return (f"{provider} sticky lifetime maxes out at {_fmt_minutes(mx)}. "
                f"You entered {_fmt_minutes(lifetime_min)} - lower it and "
                "try again.")
    return None


def generate_resi_batch(provider, region_type, regions, lifetime_min, count,
                        rotating=False, asns=None, fresh=False):
    """Build `count` residential proxy lines for one provider, spread round-robin
    across the selected `regions` (state/city) and, for proxy-haus, `asns`.
    lifetime_min is minutes. Each line gets a unique session token unless
    rotating. Returns (lines, error_or_None)."""
    spec = RESI_PROVIDERS.get(provider)
    if not spec:
        return [], f"Unknown provider: {provider}"
    user, pw = load_provider_creds(spec["key"], spec.get("legacy"))
    if not user or not pw:
        return [], f"Add {provider} username:password on the Settings tab first."
    if not rotating:
        err = resi_lifetime_error(provider, lifetime_min,
                                  fresh and spec.get("supports_fresh"))
        if err:
            return [], err
    make_sessid = spec.get("sessid", _resi_sessid)
    targets = regions if (region_type in ("State", "City") and regions) else [""]
    if spec.get("supports_asn") and asns:
        # ASN providers (proxy-haus): guarantee at least one proxy per selected
        # ASN, and split `count` as evenly as possible across them when count >
        # the number of ASNs. e.g. 5 ASNs / count 10 => 2 each; count 12 => three
        # ASNs get 3 and two get 2; count 1 => still one per ASN.
        n = len(asns)
        total = max(count, n)
        base, extra = divmod(total, n)
        asn_seq = []
        for idx, a in enumerate(asns):
            asn_seq.extend([a] * (base + (1 if idx < extra else 0)))
    else:
        asn_seq = [None] * count
    # `always_session` providers (Rayobyte) have no rotating mode, so they still
    # get a fresh session token even when the run is rotating.
    force_session = spec.get("always_session")
    lines = []
    for i, asn in enumerate(asn_seq):
        tgt = targets[i % len(targets)]
        state = tgt if region_type == "State" else ""
        city = tgt if region_type == "City" else ""
        sid = make_sessid() if (force_session or not rotating) else None
        extra = {"fresh": True} if (fresh and spec.get("supports_fresh")) else {}
        lines.append(spec["build"](user, pw, state, city, lifetime_min,
                                   sid, asn, **extra))
    return lines, None


def generate_resi_multi(providers, region_type, regions, lifetimes, count,
                        rotating=False, asns=None, fresh=False):
    """Generate `count` lines for EACH selected provider and concatenate them.
    `lifetimes` is a {provider: minutes} map so each provider can have its own
    sticky time. Any provider whose time exceeds its cap aborts the whole run
    with a naming error. Returns (lines, error_or_None)."""
    if not providers:
        return [], "Select at least one provider."
    all_lines = []
    for p in providers:
        lt = None if rotating else (lifetimes or {}).get(p)
        lines, err = generate_resi_batch(p, region_type, regions, lt,
                                         count, rotating, asns, fresh)
        if err:
            return [], err
        all_lines.extend(lines)
    return all_lines, None


# Hardcoded ASN catalog, classified by network type (researched via
# ipinfo/PeeringDB/CAIDA). Fields: (asn, name, category, strict).
#   category : "mobile" | "residential" | "business" | "datacenter"
#   strict   : True  = pure consumer eyeball network (no business/transit mix)
#              False = dual-use / business / datacenter (excluded by "Strict only")
CATEGORIES = ("mobile", "residential", "business", "datacenter")

ASN_CATALOG = [
    # --- Mobile (cellular CGNAT) ---
    ("21928", "T-Mobile US", "mobile", True),
    ("22140", "T-Mobile 2nd", "mobile", True),
    ("6167", "Verizon Wireless", "mobile", True),
    ("22394", "Verizon Wireless 2nd", "mobile", True),
    ("20057", "AT&T Mobility", "mobile", True),
    ("6614", "US Cellular -> T-Mobile", "mobile", True),
    ("10507", "Sprint PCS -> T-Mobile", "mobile", True),
    ("398378", "Dish / Boost Mobile", "mobile", True),
    # --- Residential (pure consumer eyeball) ---
    ("7922", "Comcast Xfinity", "residential", True),
    ("7015", "Comcast (legacy)", "residential", True),
    ("7016", "Comcast", "residential", True),
    ("33667", "Comcast regional", "residential", True),
    ("33651", "Comcast regional", "residential", True),
    ("33491", "Comcast regional", "residential", True),
    ("33490", "Comcast regional", "residential", True),
    ("33489", "Comcast regional", "residential", True),
    ("33287", "Comcast regional", "residential", True),
    ("20214", "Comcast regional", "residential", True),
    ("20115", "Charter Spectrum", "residential", True),
    ("11426", "Charter/TWC Carolinas", "residential", True),
    ("12271", "Charter/TWC NYC", "residential", True),
    ("20001", "Charter/TWC West", "residential", True),
    ("11351", "Charter/TWC Northeast", "residential", True),
    ("11427", "Charter/TWC Texas", "residential", True),
    ("10796", "Charter/TWC Midwest", "residential", True),
    ("33363", "Charter/Bright House", "residential", True),
    ("6128", "Optimum (Cablevision)", "residential", True),
    ("19108", "Optimum (Suddenlink)", "residential", True),
    ("22773", "Cox", "residential", True),
    ("5650", "Frontier", "residential", True),
    ("16591", "Google Fiber", "residential", True),
    # --- Residential but dual-use (also carries business) ---
    ("7018", "AT&T Internet", "residential", False),
    ("209", "CenturyLink / Lumen", "residential", False),
    ("7843", "Charter/TWC backbone", "residential", False),
    ("30036", "Mediacom", "residential", False),
    ("14593", "SpaceX Starlink", "residential", False),
    # --- Business / transit / enterprise ---
    ("701", "Verizon Business (UUNET)", "business", False),
    ("702", "Verizon Business (UUNET)", "business", False),
    ("2828", "XO (Verizon Business)", "business", False),
    ("3356", "Lumen / Level3 (transit)", "business", False),
    ("23504", "GTT (ex-Speakeasy)", "business", False),
    ("11486", "Verizon Business", "business", False),
    ("22561", "CenturyLink / Lumen", "business", False),
    # --- Datacenter / hosting ---
    ("27524", "haoxiangyun (hosting)", "datacenter", False),
    ("397143", "Neptune Networks (hosting)", "datacenter", False),
    ("40052", "Equinix", "datacenter", False),
]


def _classify_asn(name, desc, pdb_type=""):
    """Best-effort network category for an ASN from its name/description plus
    (optionally) PeeringDB's info_type. Returns one of CATEGORIES."""
    text = f"{name} {desc}".lower()
    if any(k in text for k in ("wireless", "mobil", "cellular", " pcs",
                               "cellco", "cmcc", "moviles", "telcel",
                               " lte", " 4g", " 5g")):
        return "mobile"
    pt = (pdb_type or "").lower()
    if "cable" in pt or "dsl" in pt or "isp" in pt:
        return "residential"
    if pt == "nsp" or "enterprise" in pt or "government" in pt or "educ" in pt:
        return "business"
    if "content" in pt or "network services" in pt or "route" in pt:
        return "datacenter"
    if any(k in text for k in ("hosting", "datacenter", "data center", "cloud",
                               "server", " vps", "colocation", " colo",
                               "dedicated")):
        return "datacenter"
    if any(k in text for k in ("broadband", "cable", "fiber", "fibre",
                               "telecom", "communications", "internet",
                               "networks", " isp")):
        return "residential"
    return "business"


def asn_lookup(asn, timeout=DEFAULT_TIMEOUT):
    """Resolve an ASN to (provider_name, category) using public registries
    (BGPView for the org name, PeeringDB for the network type, RIPEstat as a
    name fallback). No API key required. Returns (None, None) on failure."""
    asn = str(asn).strip().upper()
    if asn.startswith("AS"):
        asn = asn[2:]
    if not asn.isdigit():
        return None, None
    name = desc = ""
    data = http_get_json(f"https://api.bgpview.io/asn/{asn}", timeout=timeout)
    if data and data.get("status") == "ok":
        d = data.get("data") or {}
        name = (d.get("name") or "").strip()
        desc = (d.get("description_short") or "").strip()
    if not name and not desc:
        rs = http_get_json(
            "https://stat.ripe.net/data/as-overview/data.json"
            f"?resource=AS{asn}", timeout=timeout)
        if rs and isinstance(rs.get("data"), dict):
            name = (rs["data"].get("holder") or "").strip()
    if not name and not desc:
        return None, None
    pdb_type = ""
    pdb = http_get_json(f"https://www.peeringdb.com/api/net?asn={asn}",
                        timeout=timeout)
    if pdb and pdb.get("data"):
        pdb_type = (pdb["data"][0].get("info_type") or "").strip()
    label = desc or name
    return label, _classify_asn(name, desc, pdb_type)


def load_custom_asns():
    """User-added ASNs from settings.json: list of {asn, name, cat}."""
    v = load_setting("custom_asns", [])
    return v if isinstance(v, list) else []


def save_custom_asns(items):
    save_setting("custom_asns", items)


def all_asns():
    """The hardcoded catalog plus the user's custom ASNs. Custom entries are
    marked strict=True so the 'Strict only' toggle never hides them - and a
    custom entry OVERRIDES a catalog entry with the same ASN, so explicitly
    adding a catalog ASN (e.g. a dual-use ISP like AT&T 7018) pins it into
    view even when 'Strict only' is on. Returns (asn, name, cat, strict)."""
    custom = {}
    for c in load_custom_asns():
        asn = str(c.get("asn", "")).strip()
        if asn:
            cat = c.get("cat", "residential")
            custom[asn] = (asn, c.get("name") or f"AS{asn}",
                           cat if cat in CATEGORIES else "residential", True)
    out, seen = [], set()
    for a, name, cat, strict in ASN_CATALOG:
        out.append(custom.get(a, (a, name, cat, strict)))
        seen.add(a)
    for a, tup in custom.items():
        if a not in seen:
            out.append(tup)
            seen.add(a)
    return out


# --------------------------------------------------------------------------- #
# Tab 1: ASN Tester (Oxylabs mobile)
# --------------------------------------------------------------------------- #
def test_asn(host, port, username, password, asn, url, runs, timeout,
             stop_event=None, provider="Oxylabs"):
    """Run `runs` requests for a single ASN. Returns an aggregate result dict."""
    latencies = []
    successes = 0
    labels = []       # exact response label per failed run
    org = ""

    for _ in range(runs):
        if stop_event is not None and stop_event.is_set():
            break
        # Fresh sticky session per sample so each run lands on a fresh IP.
        user = build_username(provider, username, asn, _random_sessid())
        proxy_url = build_proxy_url(host, port, user, password)
        r = do_request(proxy_url, url, timeout)

        if r["ok"]:
            successes += 1
            latencies.append(r["ms"])
            found_org = _parse_json_field(r["body"], "org")
            if found_org:
                org = found_org
        else:
            labels.append(response_label(r))
        # Any test URL other than ipinfo returns no 'org' field, which used to
        # leave 'Landed on (org)' empty. Resolve it with ONE extra call through
        # the SAME sticky session, and only until this ASN has an answer - so it
        # costs at most one extra request per ASN, and none at all on the
        # default URL. A 4xx from the target still means the exit connected.
        code = r.get("code")
        reached = r["ok"] or (code and 400 <= code < 500 and code != 407)
        if not org and reached and "ipinfo.io" not in (url or "").lower():
            probe = do_request(proxy_url, IPINFO_URL, timeout)
            if probe["ok"]:
                org = _parse_json_field(probe["body"], "org") or org

    interrupted = stop_event is not None and stop_event.is_set()
    if successes > 0:
        status = "OK"
    elif interrupted and not labels:
        status = "stopped"
    elif labels:
        # Show the most common exact response across the runs.
        status = Counter(labels).most_common(1)[0][0]
    else:
        status = "no response"

    return {
        "asn": str(asn),
        "status": status,
        "median": statistics.median(latencies) if latencies else None,
        "min": min(latencies) if latencies else None,
        "max": max(latencies) if latencies else None,
        "success": successes,
        "runs": runs,
        "org": org,
    }


# --------------------------------------------------------------------------- #
# Tab 2: Proxy Tester (general reachability)
# --------------------------------------------------------------------------- #
def parse_proxy_line(line):
    """
    Parse 'host:port:user:pass' (or 'host:port') into a dict. Also accepts the
    comma-delimited 'host,port,user,pass' variant that some dashboards emit.
    Returns None if the line is not usable.
    """
    line = line.strip()
    if not line:
        return None
    # Pick the delimiter: comma only when the line is clearly comma-separated
    # (has commas and no colons), otherwise the usual colon format.
    if "," in line and ":" not in line:
        parts = line.split(",", 3)  # cap at 4 so ',' inside a password survives
    else:
        parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        user = pw = None
    elif len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        pw = parts[3] if len(parts) == 4 else ":".join(parts[3:])  # ':' in pass
    else:
        return None
    host = host.strip()
    port = port.strip()
    if not host or not port:
        return None
    return {"host": host, "port": port, "user": user, "pw": pw}


_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.I)


def apply_asn_to_username(user, asn):
    """Rewrite an Oxylabs-style username to target an ASN. Country and ASN are
    mutually exclusive on Oxylabs, so swap -cc-<country> for -ASN-<asn>; replace
    an existing -ASN-<n>; otherwise insert -ASN-<asn> before the session id (or
    at the end). Preserves sessid/sesstime."""
    if not user or not asn:
        return user
    if re.search(r"-cc-[a-z]{2}\b", user, re.I):
        return re.sub(r"-cc-[a-z]{2}\b", f"-ASN-{asn}", user, count=1, flags=re.I)
    if re.search(r"-ASN-\d+", user):
        return re.sub(r"-ASN-\d+", f"-ASN-{asn}", user, count=1)
    if "-sessid-" in user:
        return user.replace("-sessid-", f"-ASN-{asn}-sessid-", 1)
    return f"{user}-ASN-{asn}"


def convert_proxy_line(line, force_asn=None):
    """
    Normalize any provider proxy format into 'host:port:user:pass'.

    Accepts:
      - full URLs: http://customer-xxx-cc-us:PASS@pr.oxylabs.io:7777
      - python snippets: entry = 'http://user:pass@host:port'
      - user:pass@host:port (no scheme)
      - already host:port:user:pass (passthrough)
    Credentials are percent-decoded (so %7E -> ~). If force_asn is given, the
    username is rewritten to target that ASN (cc-<country> -> ASN-<n>). Returns
    None if unparseable.
    """
    line = line.strip().strip("'\",;")
    if not line:
        return None

    match = _URL_RE.search(line)
    target = match.group(0).strip("'\",;)") if match else line
    if "://" not in target and "@" in target:
        target = "http://" + target

    if "://" in target:
        try:
            parts = urlsplit(target)
            host, port = parts.hostname, parts.port
        except ValueError:
            return None
        if not host or not port:
            return None
        user = unquote(parts.username) if parts.username else None
        pw = unquote(parts.password) if parts.password is not None else None
        if user and force_asn:
            user = apply_asn_to_username(user, force_asn)
        if user and pw is not None:
            return f"{host}:{port}:{user}:{pw}"
        if user:
            return f"{host}:{port}:{user}"
        return f"{host}:{port}"

    parsed = parse_proxy_line(target)
    if parsed:
        user = parsed["user"]
        if user and force_asn:
            user = apply_asn_to_username(user, force_asn)
        if user and parsed["pw"] is not None:
            return f"{parsed['host']}:{parsed['port']}:{user}:{parsed['pw']}"
        return f"{parsed['host']}:{parsed['port']}"
    return None


def test_proxy(proxy, url, runs, timeout, stop_event=None):
    """Run `runs` reachability requests for a single proxy line."""
    host, port, user, pw = proxy["host"], proxy["port"], proxy["user"], proxy["pw"]
    if user and pw is not None:
        proxy_url = build_proxy_url(host, port, user, pw)
        display = f"{host}:{port}:{user}:****"
        full = f"{host}:{port}:{user}:{pw}"
    else:
        proxy_url = build_proxy_url(host, port)
        display = f"{host}:{port}"
        full = display

    latencies = []
    successes = 0
    attempts = 0
    last_code = None
    exit_ip = ""
    org = city = region = country = ""
    labels = []

    for _ in range(runs):
        if stop_event is not None and stop_event.is_set():
            break
        attempts += 1
        r = do_request(proxy_url, url, timeout)
        code = response_code(r)
        if code is not None:
            last_code = code
        if r["ok"]:
            successes += 1
            latencies.append(r["ms"])
            # When the test URL returns ipinfo-style JSON (the default), pull
            # the exit IP plus provider/ASN (org) and location for display.
            found_ip = _parse_json_field(r["body"], "ip")
            if found_ip:
                exit_ip = found_ip
            org = _parse_json_field(r["body"], "org") or org
            city = _parse_json_field(r["body"], "city") or city
            region = _parse_json_field(r["body"], "region") or region
            country = _parse_json_field(r["body"], "country") or country
        else:
            labels.append(response_label(r))
            # Fail-fast: a connection-level failure (timeout / refused / tunnel
            # failure) with no success yet means the proxy is dead - retrying
            # only burns another full per-request timeout while holding a
            # worker. Stop now instead of paying runs x timeout on dead proxies.
            # An HTTP response (even a 403) means the proxy reached the target,
            # so those keep testing every run.
            if r.get("error") == "conn" and successes == 0:
                break

    location = ", ".join(p for p in (city, region, country) if p)

    interrupted = stop_event is not None and stop_event.is_set()
    if successes > 0:
        status = "OK"
    elif interrupted and not labels:
        status = "stopped"
    elif labels:
        status = Counter(labels).most_common(1)[0][0]
    else:
        status = "no response"

    return {
        "proxy": display,
        "full": full,
        "status": status,
        "code": str(last_code) if last_code is not None else "-",
        "median": statistics.median(latencies) if latencies else None,
        "success": successes,
        "runs": attempts,
        "exit_ip": exit_ip,
        "org": org,
        "location": location,
        "reason": "",
    }


# Neutral CONNECT target for the liveness probe - never a retailer, so no
# bot-defence engages. The tunnel opening (or not) is the liveness signal.
LIVENESS_TARGET = ("ipinfo.io", 443)


def _fast_status(code, err):
    """A short status label for a connect-only probe outcome."""
    if code == 407:
        return "auth failed (407)"
    if code in (502, 504):
        return "upstream error"
    if code:
        return f"HTTP {code}"
    if err == "timeout":
        return "timeout"
    return "unreachable"


def test_proxy_fast(proxy, runs, timeout, stop_event=None):
    """Connect-only liveness + latency: open an HTTP CONNECT tunnel through the
    proxy to a neutral host:port and time the round-trip to '200 Connection
    established'. No TLS to the target, no HTTP request, no body read - far
    cheaper than a full GET, which is what makes huge lists fast. It proves the
    tunnel opens, NOT that egress works or what the exit IP is; use Full mode
    for the exit IP. Same result shape as test_proxy (exit_ip/org/location
    blank)."""
    host, port, user, pw = proxy["host"], proxy["port"], proxy["user"], proxy["pw"]
    if user and pw is not None:
        display = f"{host}:{port}:{user}:****"
        full = f"{host}:{port}:{user}:{pw}"
    else:
        display = f"{host}:{port}"
        full = display

    thost, tport = LIVENESS_TARGET
    latencies = []
    successes = attempts = 0
    last_code = None
    labels = []
    for _ in range(runs):
        if stop_event is not None and stop_event.is_set():
            break
        attempts += 1
        ms, code, err = proxy_connect_ping(proxy, thost, tport, timeout)
        if code is not None:
            last_code = code
        if ms is not None and code == 200:
            successes += 1
            latencies.append(ms)
        else:
            labels.append(_fast_status(code, err))
            # Fail-fast: a connection-level failure (no HTTP code at all) with
            # no success yet means the proxy is dead - don't pay another full
            # timeout. A 407/502 is an answer, so those still run every time.
            if code is None and successes == 0:
                break

    interrupted = stop_event is not None and stop_event.is_set()
    if successes > 0:
        status = "OK"
    elif interrupted and not labels:
        status = "stopped"
    elif labels:
        status = Counter(labels).most_common(1)[0][0]
    else:
        status = "no response"

    return {
        "proxy": display,
        "full": full,
        "status": status,
        "code": str(last_code) if last_code is not None else "-",
        "median": statistics.median(latencies) if latencies else None,
        "success": successes,
        "runs": attempts,
        "exit_ip": "",
        "org": "",
        "location": "",
        "reason": "",
    }


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class AsnTab(ttk.Frame):
    COLUMNS = ("asn", "type", "status", "median", "min", "max", "success",
               "org")
    HEADINGS = {
        "asn": "ASN", "type": "Type", "status": "Status", "median": "Median ms",
        "min": "Min ms", "max": "Max ms", "success": "Success (n/N)",
        "org": "Landed on (org)",
    }

    def __init__(self, master):
        super().__init__(master, padding=14)
        self.queue = queue.Queue()
        self.running = False
        self.stop_event = threading.Event()
        self.row_ids = {}
        self._build()

    def _build(self):
        form = ttk.Frame(self)
        form.pack(fill="x")

        _mu, _mp = load_provider_creds("oxylabs_mobile")
        self.host = tk.StringVar(value="pr.oxylabs.io")
        self.port = tk.StringVar(value="7777")
        self.username = tk.StringVar(value=_mu)
        self.password = tk.StringVar(value=_mp)
        self.url = tk.StringVar(value="https://ipinfo.io/json")
        self.runs = tk.StringVar(value="5")
        self.provider = tk.StringVar(value="Oxylabs")

        def field(row, label, var, width=28, show=None):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            e = ttk.Entry(form, textvariable=var, width=width, show=show)
            e.grid(row=row, column=1, sticky="w", pady=3, padx=(8, 24))
            return e

        ttk.Label(form, text="Provider").grid(row=0, column=0, sticky="w", pady=3)
        self.provider_cb = ttk.Combobox(
            form, textvariable=self.provider, values=list(PROVIDERS.keys()),
            width=18, state="readonly")
        self.provider_cb.grid(row=0, column=1, sticky="w", pady=3, padx=(8, 24))
        self.provider_cb.bind("<<ComboboxSelected>>", self.on_provider)

        field(1, "Host", self.host)
        field(2, "Port", self.port, width=10)
        field(3, "Username", self.username)
        pw_entry = field(4, "Password", self.password, show="•")
        reveal_on_focus(pw_entry)
        # Test URL + a retailer target picker (like the Proxy Tester tab): pick
        # a preset site and it drops the URL in, so you can test each ASN's IPs
        # straight against Walmart/Target/etc.
        ttk.Label(form, text="Test URL").grid(row=5, column=0, sticky="w",
                                              pady=3)
        url_row = ttk.Frame(form)
        url_row.grid(row=5, column=1, sticky="w", pady=3, padx=(8, 24))
        ttk.Entry(url_row, textvariable=self.url, width=30).pack(side="left")
        self.target_site = tk.StringVar(value="Custom")
        tcb = ttk.Combobox(url_row, textvariable=self.target_site, width=13,
                           state="readonly",
                           values=["Custom", "ipinfo.io/json"]
                           + [n for n, _ in RETAIL_SITES])
        tcb.pack(side="left", padx=(6, 0))
        tcb.bind("<<ComboboxSelected>>", self._on_target_site)
        field(6, "Runs per ASN", self.runs, width=6)

        asn_frame = ttk.Frame(form)
        asn_frame.grid(row=0, column=2, rowspan=7, sticky="nw", padx=(4, 0))
        ttk.Label(
            asn_frame,
            text="ASNs - filter, then Shift/Ctrl-click to select").pack(
            anchor="w")

        # Category filter toggles (Mobile/Residential on by default).
        self.filter_vars = {}
        frow = ttk.Frame(asn_frame)
        frow.pack(fill="x", pady=(2, 0))
        for cat, default in (("mobile", True), ("residential", True),
                             ("business", False), ("datacenter", False)):
            var = tk.BooleanVar(value=default)
            self.filter_vars[cat] = var
            ttk.Checkbutton(frow, text=cat.capitalize(), variable=var,
                            command=self._refilter_asns).pack(
                side="left", padx=(0, 8))

        frow2 = ttk.Frame(asn_frame)
        frow2.pack(fill="x", pady=(2, 4))
        self.strict_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frow2, text="Strict only", variable=self.strict_var,
                        command=self._refilter_asns).pack(side="left")
        ttk.Label(frow2, text="search (comma-sep)").pack(
            side="left", padx=(12, 4))
        self.search_var = tk.StringVar()
        ttk.Entry(frow2, textvariable=self.search_var, width=20).pack(
            side="left")
        self.search_var.trace_add("write", lambda *a: self._refilter_asns())

        lb_row = ttk.Frame(asn_frame)
        lb_row.pack(fill="both")
        self.asn_list = tk.Listbox(
            lb_row, selectmode="extended", height=9, width=50,
            exportselection=False, activestyle="none")
        self.asn_list.configure(
            bg=MANTLE, fg=TEXT, selectbackground=MAUVE, selectforeground=BASE,
            highlightthickness=1, highlightbackground=SURFACE2,
            highlightcolor=MAUVE, relief="flat", borderwidth=0,
            font=(UI_FONT, 10))
        lb_sb = ttk.Scrollbar(lb_row, orient="vertical",
                              command=self.asn_list.yview)
        self.asn_list.configure(yscrollcommand=lb_sb.set)
        self.asn_list.pack(side="left", fill="both")
        lb_sb.pack(side="left", fill="y")
        self._visible_asns = []
        self._refilter_asns()  # populate

        self.asn_list.bind("<Control-c>", self._copy_selected_asns)
        self.asn_list.bind("<Control-C>", self._copy_selected_asns)
        attach_copy_menu(self.asn_list, self._copy_selected_asns,
                         "Copy selected ASNs")

        lb_btns = ttk.Frame(asn_frame)
        lb_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(lb_btns, text="Select all",
                   command=lambda: self.asn_list.selection_set(0, "end")).pack(
            side="left")
        ttk.Button(lb_btns, text="Clear",
                   command=lambda: self.asn_list.selection_clear(0, "end")).pack(
            side="left", padx=6)
        ttk.Button(lb_btns, text="Copy",
                   command=self._copy_selected_asns).pack(side="left")

        ttk.Label(asn_frame,
                  text="+ custom ASNs (one per line or comma-separated)").pack(
            anchor="w", pady=(8, 0))
        self.asn_text = tk.Text(asn_frame, width=34, height=4)
        style_text(self.asn_text)
        self.asn_text.pack(fill="x")
        paste_appends_to_end(self.asn_text)

        # Look them up (provider + type) and pin them into the list above so
        # they persist and show even under 'Strict only'.
        addbar = ttk.Frame(asn_frame)
        addbar.pack(fill="x", pady=(4, 0))
        self.add_btn = ttk.Button(addbar, text="Look up & add to list",
                                  command=self.on_lookup_add)
        self.add_btn.pack(side="left")
        self.add_status = ttk.Label(addbar, text="", style="Muted.TLabel")
        self.add_status.pack(side="left", padx=(8, 0))

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 4))
        self.run_btn = ttk.Button(btns, text="Run", style="Accent.TButton",
                                  command=self.on_run)
        self.run_btn.pack(side="left")
        self.gen_btn = ttk.Button(btns, text="Generate from selected results",
                                  command=self.on_generate)
        self.gen_btn.pack(side="left", padx=8)
        self.export_btn = ttk.Button(btns, text="Export CSV",
                                     command=self.on_export)
        self.export_btn.pack(side="left", padx=8)
        self.status_lbl = ttk.Label(btns, text="Idle", style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        # Status/org stretch, are left-aligned, and have a minwidth so the
        # exact response and carrier org stay readable (can't be squeezed).
        layout = {
            "asn":     (80,  60,  False, "w"),
            "type":    (110, 80,  False, "center"),
            "status":  (200, 150, True,  "center"),
            "median":  (90,  70,  False, "center"),
            "min":     (90,  70,  False, "center"),
            "max":     (90,  70,  False, "center"),
            "success": (110, 90,  False, "center"),
            "org":     (220, 140, True,  "center"),
        }
        for col in self.COLUMNS:
            w, mw, st, anc = layout[col]
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=w, minwidth=mw, stretch=st, anchor=anc)
        tag_tree(self.tree)
        enable_drag_select(self.tree)
        self.tree.bind("<Control-c>", self._copy_rows)
        self.tree.bind("<Control-C>", self._copy_rows)
        self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(
            self.tree.get_children()), "break")[1])
        attach_copy_menu(self.tree, self._copy_rows, "Copy selected rows")
        self.tree.pack(fill="both", expand=True, pady=(8, 0))

        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _refilter_asns(self):
        """Rebuild the ASN list from the active category/strict/search filters.
        Proxy-Haus only serves a fixed carrier set, so when it's the provider the
        list is restricted to exactly those ASNs (the full catalog is Oxylabs')."""
        cats = {c for c, v in self.filter_vars.items() if v.get()}
        if not cats:                       # nothing checked -> show everything
            cats = set(CATEGORIES)
        strict_only = self.strict_var.get()
        # Search accepts several terms separated by commas or spaces; a row
        # matches if ANY term is found in its ASN number or provider name.
        terms = [t for t in re.split(r"[\s,]+",
                                     self.search_var.get().strip().lower()) if t]
        if getattr(self, "provider", None) and self.provider.get() == "Proxy-Haus":
            source = [(a, n, c, True) for a, n, c in PROXYHAUS_ASNS]
        else:
            source = all_asns()
        self.asn_list.delete(0, "end")
        self._visible_asns = []
        for asn, name, cat, strict in source:
            if cat not in cats:
                continue
            if strict_only and not strict:
                continue
            if terms and not any(t in asn or t in name.lower() for t in terms):
                continue
            label = f"{asn}  -  {name}  [{cat}]"
            if cat == "residential" and not strict:
                label += " +biz"
            self.asn_list.insert("end", label)
            self._visible_asns.append(asn)

    def _on_target_site(self, _event=None):
        """Set the Test URL from the retailer target picker."""
        choice = self.target_site.get()
        if choice == "Custom":
            return
        if choice == "ipinfo.io/json":
            self.url.set("https://ipinfo.io/json")
            return
        for name, host in RETAIL_SITES:
            if name == choice:
                self.url.set(f"https://{host}/")
                return

    def _copy_rows(self, _event=None):
        """Copy the selected result rows as tab-separated text (paste-ready for
        a spreadsheet)."""
        rows = ["\t".join(str(v) for v in self.tree.item(i, "values"))
                for i in self.tree.selection()]
        if rows:
            self.clipboard_clear()
            self.clipboard_append("\n".join(rows))
            self.update_idletasks()
            self.status_lbl.config(text=f"Copied {len(rows)} row(s)")
        return "break"

    def _copy_selected_asns(self, _event=None):
        """Copy just the ASN numbers (not the labels), one per line."""
        asns = [self._visible_asns[i] for i in self.asn_list.curselection()]
        if asns:
            self.clipboard_clear()
            self.clipboard_append("\n".join(asns))
            self.update_idletasks()
            self.status_lbl.config(text=f"Copied {len(asns)} ASN(s)")
        return "break"

    def _selected_asns(self):
        """Selected (visible) ASNs + any pasted ones, de-duplicated in order."""
        picked = [self._visible_asns[i] for i in self.asn_list.curselection()]
        pasted = [a.strip() for a in self.asn_text.get("1.0", "end").splitlines()
                  if a.strip()]
        seen, out = set(), []
        for asn in picked + pasted:
            if asn not in seen:
                seen.add(asn)
                out.append(asn)
        return out

    # --- look up & pin custom ASNs -------------------------------------- #
    def on_lookup_add(self):
        tokens, seen = [], set()
        for tok in re.split(r"[\s,]+", self.asn_text.get("1.0", "end").upper()):
            tok = tok[2:] if tok.startswith("AS") else tok
            if tok and tok not in seen:
                seen.add(tok)
                tokens.append(tok)
        if not tokens:
            self.add_status.config(text="Paste one or more ASNs above first.")
            return

        pinned = {str(c.get("asn")) for c in load_custom_asns()}
        catalog = {a: (name, cat) for a, name, cat, _ in ASN_CATALOG}
        total = len(tokens)
        invalid = [t for t in tokens if not t.isdigit()]
        # Duplicate = already pinned. A catalog ASN not yet pinned is pinned
        # now (no lookup needed) so it shows even under 'Strict only'.
        dup = [t for t in tokens if t.isdigit() and t in pinned]
        preadd = [{"asn": t, "name": catalog[t][0], "cat": catalog[t][1]}
                  for t in tokens
                  if t.isdigit() and t not in pinned and t in catalog]
        todo = [t for t in tokens
                if t.isdigit() and t not in pinned and t not in catalog]

        if not todo:
            self._finish_lookup_add(preadd, total, len(dup), len(invalid))
            return

        self.add_btn.config(state="disabled")
        self.add_status.config(text=f"Looking up {len(todo)} ASN(s)...")

        def work():
            found = list(preadd)
            for asn in todo:
                name, cat = asn_lookup(asn)
                if name:
                    found.append({"asn": asn, "name": name, "cat": cat})
            self.after(0, lambda: self._finish_lookup_add(
                found, total, len(dup), len(invalid)))

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _add_summary(total, added, dup, failed, invalid):
        parts = [f"{added}/{total} added"]
        if dup:
            parts.append(f"{dup} duplicate")
        if failed:
            parts.append(f"{failed} not found")
        if invalid:
            parts.append(f"{invalid} invalid")
        return ", ".join(parts)

    def _finish_lookup_add(self, found, total, dup, invalid):
        self.add_btn.config(state="normal")
        if found:
            items = load_custom_asns()
            items.extend(found)
            save_custom_asns(items)
            self._refilter_asns()
        failed = total - len(found) - dup - invalid
        self.add_status.config(
            text=self._add_summary(total, len(found), dup, failed, invalid))

    def load_mobile_creds(self):
        """Fill Username/Password from the current provider's saved creds
        (Oxylabs mobile / Proxy-Haus package). Called after Save so newly-entered
        creds sync into this tab without a restart."""
        creds_key = (PROVIDERS.get(self.provider.get()) or {}).get("creds")
        if not creds_key:
            return
        u, p = load_provider_creds(creds_key)
        if u:
            self.username.set(u)
        if p:
            self.password.set(p)

    # --- profile state ---
    def get_state(self):
        # Profiles store credentials/settings only - never the transient ASN
        # selection or the pasted box (those start empty each session).
        return {
            "host": self.host.get(), "port": self.port.get(),
            "username": self.username.get(), "password": self.password.get(),
            "url": self.url.get(), "runs": self.runs.get(),
            "provider": self.provider.get(),
        }

    def set_state(self, d):
        self.host.set(d.get("host", "pr.oxylabs.io"))
        self.port.set(d.get("port", "7777"))
        self.username.set(d.get("username", ""))
        self.password.set(d.get("password", ""))
        self.url.set(d.get("url", "https://ipinfo.io/json"))
        self.runs.set(d.get("runs", "5"))
        self.provider.set(d.get("provider", "Oxylabs"))

    def on_provider(self, _event=None):
        prov = self.provider.get()
        host, port = provider_hostport(prov)
        if host:
            self.host.set(host)
        if port:
            self.port.set(port)
        # Auto-fill this provider's saved username:password (Oxylabs mobile /
        # Proxy-Haus package) and restrict the ASN list to what it supports.
        creds_key = (PROVIDERS.get(prov) or {}).get("creds")
        if creds_key:
            u, p = load_provider_creds(creds_key)
            if u:
                self.username.set(u)
            if p:
                self.password.set(p)
        self._refilter_asns()

    def on_generate(self):
        # Build proxies from the ASNs selected in the RESULTS table.
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Generate proxies",
                "Select one or more rows in the results table first.\n\n"
                "Run a test, then highlight the ASNs you want proxies for "
                "(Shift-click a range, Ctrl-click to toggle).")
            return
        asns = [self.tree.item(iid, "values")[0] for iid in selection]

        host = self.host.get().strip()
        port = self.port.get().strip()
        username = self.username.get().strip()
        password = self.password.get()
        provider = self.provider.get()
        if not host or not port or not username:
            messagebox.showerror(
                "Generate proxies", "Host, Port and Username are required.")
            return

        opts = ask_generate_options(self, len(asns))
        if not opts:
            return
        mode, count, sesstime = opts  # mode: "static" | "rotating"

        # Enforce the provider's hardcoded sticky max (don't generate over it).
        mx = (PROVIDERS.get(provider) or {}).get("max_min")
        if mode == "static" and sesstime and mx and sesstime > mx:
            messagebox.showerror(
                "Generate proxies",
                f"{provider} sticky session maxes out at {mx} minutes. "
                f"You entered {sesstime} - lower the session time.")
            return

        lines = []
        # Sequential sessids (like the Oxylabs endpoint generator): a random
        # base, then +1 per proxy, so each static proxy is a distinct session.
        base = random.randint(1, 8_999_999_999)
        seq = 0
        for asn in asns:
            for _ in range(count):
                if mode == "static":
                    user = build_username(provider, username, asn,
                                          f"{base + seq:010d}", sesstime)
                    seq += 1
                else:
                    user = build_username(provider, username, asn)
                lines.append(f"{host}:{port}:{user}:{password}")
        title = (f"{mode.capitalize()} proxies - {provider} "
                 f"({len(asns)} ASN x {count} = {len(lines)})")
        show_output_popup(self, title, "\n".join(lines), shuffle=True)

    def on_run(self):
        if self.running:
            return
        host = self.host.get().strip()
        port = self.port.get().strip()
        username = self.username.get().strip()
        password = self.password.get()
        url = self.url.get().strip()
        asns = self._selected_asns()

        try:
            runs = max(1, int(self.runs.get().strip()))
        except ValueError:
            messagebox.showerror("ProxyTester", "Runs per ASN must be a number.")
            return
        if not host or not port:
            messagebox.showerror("ProxyTester", "Host and Port are required.")
            return
        if not username:
            messagebox.showerror("ProxyTester", "Username is required.")
            return
        if not asns:
            messagebox.showerror("ProxyTester", "Select or paste at least one ASN.")
            return

        self.tree.delete(*self.tree.get_children())
        self.row_ids.clear()
        # Map each ASN to its network type for the Type column.
        self._cat_map = {a: cat for a, name, cat, strict in all_asns()}
        for asn in asns:
            cat = self._cat_map.get(asn, "-")
            iid = self.tree.insert(
                "", "end",
                values=(asn, cat, "testing...", "-", "-", "-", "-", ""),
                tags=("muted",))
            self.row_ids[asn] = iid

        self.running = True
        self.stop_event.clear()
        self.run_btn.config(text="Stop", style="Stop.TButton",
                            command=self.on_stop)
        self.status_lbl.config(text=f"Testing {len(asns)} ASN(s)...")

        worker = threading.Thread(
            target=self._run_pool,
            args=(host, port, username, password, asns, url, runs,
                  self.provider.get()),
            daemon=True)
        worker.start()
        self.after(100, self._drain_queue)

    def on_stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.run_btn.config(state="disabled")
        self.status_lbl.config(text="Stopping...")

    def _run_pool(self, host, port, username, password, asns, url, runs, provider):
        try:
            with ThreadPoolExecutor(max_workers=get_workers()) as pool:
                futures = {
                    pool.submit(test_asn, host, port, username, password,
                                asn, url, runs, DEFAULT_TIMEOUT,
                                self.stop_event, provider): asn
                    for asn in asns
                }
                for fut, asn in futures.items():
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = {"asn": asn, "status": "unavailable",
                                  "median": None, "min": None, "max": None,
                                  "success": 0, "runs": runs, "org": str(e)}
                    self.queue.put(result)
        finally:
            self.queue.put({"_done": True})

    def _drain_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item.get("_done"):
                    self._finish()
                    return
                self._update_row(item)
        except queue.Empty:
            pass
        if self.running:
            self.after(100, self._drain_queue)

    def _update_row(self, r):
        iid = self.row_ids.get(r["asn"])
        cat = getattr(self, "_cat_map", {}).get(r["asn"], "-")
        values = (r["asn"], cat, r["status"], _fmt_ms(r["median"]),
                  _fmt_ms(r["min"]), _fmt_ms(r["max"]),
                  f"{r['success']}/{r['runs']}", r["org"])
        tag = status_tag(r["status"])
        if iid:
            self.tree.item(iid, values=values, tags=(tag,))
        else:
            self.tree.insert("", "end", values=values, tags=(tag,))

    def _finish(self):
        stopped = self.stop_event.is_set()
        self.running = False
        self.run_btn.config(text="Run", style="Accent.TButton",
                            command=self.on_run, state="normal")
        # Any row still 'testing...' never got a result (interrupted).
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if vals[2] == "testing...":
                self.tree.item(iid,
                               values=vals[:2] + ("stopped",) + vals[3:],
                               tags=("muted",))
        self._sort_rows()
        self.status_lbl.config(text="Stopped" if stopped else "Done")

    def _sort_rows(self):
        """OK rows first, ascending median; everything else after."""
        rows = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            try:
                median = float(vals[3])
            except (ValueError, TypeError):
                median = float("inf")
            ok_rank = 0 if vals[2] == "OK" else 1
            rows.append((ok_rank, median, iid))
        rows.sort(key=lambda t: (t[0], t[1]))
        for index, (_, _, iid) in enumerate(rows):
            self.tree.move(iid, "", index)

    def on_export(self):
        export_tree_csv(self.tree, self.COLUMNS,
                        [self.HEADINGS[c] for c in self.COLUMNS])


class ProxyTab(ttk.Frame):
    COLUMNS = ("proxy", "status", "code", "median", "success", "exit_ip",
               "org", "location")
    HEADINGS = {
        "proxy": "Proxy", "status": "Status", "code": "HTTP code",
        "median": "Median ms", "success": "Success (n/N)", "exit_ip": "Exit IP",
        "org": "Provider / ASN", "location": "Location",
    }

    def __init__(self, master):
        super().__init__(master, padding=14)
        self.queue = queue.Queue()
        self.running = False
        self.stop_event = threading.Event()
        self._sort_dir = {}       # column -> current sort direction
        self._row_full = {}       # tree item id -> full host:port:user:pass
        self._build()

    def _build(self):
        form = ttk.Frame(self)
        form.pack(fill="x")

        self.proxy_hdr = ttk.Label(
            form, text="Proxies (host:port:user:pass, one per line)")
        self.proxy_hdr.grid(row=0, column=0, sticky="w")
        self.proxy_text = tk.Text(form, width=50, height=8)
        style_text(self.proxy_text)
        self.proxy_text.grid(row=1, column=0, rowspan=4, sticky="nw", padx=(0, 24))
        self.proxy_text.bind("<<Modified>>", self._update_proxy_count)
        # Paste appends to the end on a fresh line, so a new list never merges
        # onto the last proxy.
        paste_appends_to_end(self.proxy_text,
                             lambda: self._update_proxy_count(force=True))

        self.url = tk.StringVar(value="https://ipinfo.io/json")
        self.runs = tk.StringVar(value="1")

        # Test mode. Liveness (fast) is connect-only - one CONNECT handshake per
        # proxy, no TLS/GET/body - so it blazes through huge lists but only
        # proves the tunnel opens. Full does the exit-IP GET (slower, richer).
        self.test_mode = tk.StringVar(value=FAST_MODE)
        ttk.Label(form, text="Test mode").grid(row=0, column=1, sticky="w")
        self.mode_cb = ttk.Combobox(
            form, textvariable=self.test_mode, state="readonly", width=22,
            values=[FAST_MODE, FULL_MODE])
        self.mode_cb.grid(row=0, column=2, sticky="w", pady=3)
        self.mode_cb.bind("<<ComboboxSelected>>", self._on_mode_change)

        ttk.Label(form, text="Test URL").grid(row=1, column=1, sticky="w")
        self.url_entry = ttk.Entry(form, textvariable=self.url, width=40)
        self.url_entry.grid(row=1, column=2, sticky="w", pady=3)
        ttk.Label(form, text="Runs per proxy").grid(row=2, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.runs, width=6).grid(
            row=2, column=2, sticky="w", pady=3)
        # Muted hint that explains what the current mode measures.
        self.mode_hint = ttk.Label(form, text="", style="Muted.TLabel")
        self.mode_hint.grid(row=3, column=1, columnspan=2, sticky="w")
        self._on_mode_change()

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 4))
        self.run_btn = ttk.Button(btns, text="Run", style="Accent.TButton",
                                  command=self.on_run)
        self.run_btn.pack(side="left")
        ttk.Button(btns, text="Generate batch",
                   command=lambda: open_generate_dialog(
                       self, self.proxy_text)).pack(side="left", padx=8)
        self.shuffle_btn = ttk.Button(btns, text="Shuffle list",
                                      command=self.on_shuffle)
        self.shuffle_btn.pack(side="left", padx=8)
        self.dedupe_btn = ttk.Button(btns, text="Dedupe",
                                     command=self.on_dedupe)
        self.dedupe_btn.pack(side="left", padx=(0, 8))
        self.cull_btn = ttk.Button(btns, text="Cull dead",
                                   command=self.on_cull_dead)
        self.cull_btn.pack(side="left", padx=(0, 8))
        # Speed filter: cull proxies whose median latency is over the threshold
        # (works on Run results and proxied Site-ping results alike).
        self.slow_btn = ttk.Button(btns, text="Cull slow >",
                                   command=self.on_cull_slow)
        self.slow_btn.pack(side="left", padx=(0, 2))
        self.slow_ms = tk.StringVar(value="1000")
        ttk.Entry(btns, textvariable=self.slow_ms, width=6).pack(side="left")
        ttk.Label(btns, text="ms", style="Muted.TLabel").pack(side="left",
                                                              padx=(2, 8))
        self.status_lbl = ttk.Label(btns, text="Idle", style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)

        # Site ping: latency to a retailer's edge - either direct (from this
        # machine) or through each pasted proxy via a CONNECT tunnel.
        ping_bar = ttk.Frame(self)
        ping_bar.pack(fill="x", pady=(0, 2))
        ttk.Label(ping_bar, text="Site ping:").pack(side="left")
        self.ping_site_var = tk.StringVar(value="Walmart")
        ttk.Combobox(
            ping_bar, textvariable=self.ping_site_var, state="readonly",
            width=22,
            values=["All presets"] + [n for n, _ in RETAIL_SITES]
            + ["Custom (Test URL)"]).pack(side="left", padx=8)
        self.ping_btn = ttk.Button(ping_bar, text="Ping site",
                                   command=self.on_ping_site)
        self.ping_btn.pack(side="left")
        # When on, ping the target through every proxy in the list (CONNECT
        # tunnel = the transport leg of a real HTTPS session, but no HTTP
        # request is sent, so PerimeterX/Akamai never see it). Off = direct
        # no-proxy baseline from this machine.
        self.ping_via_proxy = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            ping_bar, text="through proxies (PX-safe CONNECT)",
            variable=self.ping_via_proxy).pack(side="left", padx=(10, 0))

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        # (width, minwidth, stretch, anchor). Status stretches, is left-aligned,
        # and has a minwidth so the exact response (e.g. "502 exit node not
        # found") stays readable and can never be squeezed down to "5xx".
        layout = {
            "proxy":    (240, 140, True,  "w"),
            "status":   (150, 110, False, "center"),
            "code":     (75,  55,  False, "center"),
            "median":   (85,  65,  False, "center"),
            "success":  (95,  80,  False, "center"),
            "exit_ip":  (130, 100, False, "w"),
            "org":      (210, 130, True,  "w"),
            "location": (160, 110, True,  "w"),
        }
        for col in self.COLUMNS:
            w, mw, st, anc = layout[col]
            # Click any header to sort by that column (toggles asc/desc).
            self.tree.heading(col, text=self.HEADINGS[col],
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, minwidth=mw, stretch=st, anchor=anc)
        tag_tree(self.tree)
        enable_drag_select(self.tree)
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        # Ctrl+C copies the selected proxies (full host:port:user:pass), Ctrl+A
        # selects every row - matching the IP Quality tab.
        self.tree.bind("<Control-c>", self._copy_selected)
        self.tree.bind("<Control-C>", self._copy_selected)
        self.tree.bind("<Control-a>", self._select_all_rows)
        self.tree.bind("<Control-A>", self._select_all_rows)
        attach_copy_menu(self.tree, self._copy_selected,
                         "Copy selected proxies")

        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _select_all_rows(self, _event=None):
        rows = self.tree.get_children()
        if rows:
            self.tree.selection_set(rows)
        return "break"

    def _copy_selected(self, _event=None):
        """Copy the highlighted proxies to the clipboard as full
        host:port:user:pass - taken from the exact per-row proxy stored when the
        row was created (so the real password/session is preserved, not the
        masked display). Rows without a proxy (direct Site-ping) are skipped."""
        sel = self.tree.selection()
        if not sel:
            return "break"
        lines = [self._row_full[iid] for iid in sel
                 if self._row_full.get(iid)]
        if not lines:
            return "break"
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.update_idletasks()
        self.status_lbl.config(text=f"Copied {len(lines)} proxy(ies)")
        return "break"

    # --- profile state ---
    def get_state(self):
        return {
            "proxies": self.proxy_text.get("1.0", "end").rstrip("\n"),
            "url": self.url.get(), "runs": self.runs.get(),
        }

    def set_state(self, d):
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", d.get("proxies", ""))
        self.url.set(d.get("url", "https://ipinfo.io/json"))
        self.runs.set(d.get("runs", "1"))

    def _on_mode_change(self, _event=None):
        """Fast mode is connect-only, so the Test URL doesn't apply - grey it
        out and swap the hint text so it's clear what each mode measures."""
        fast = self.test_mode.get() == FAST_MODE
        try:
            self.url_entry.config(state="disabled" if fast else "normal")
        except Exception:
            pass
        self.mode_hint.config(
            text=("Connect-only: opens a CONNECT tunnel per proxy - fast, but "
                  "no exit IP (URL ignored)."
                  if fast else
                  "Full GET to the Test URL - slower; harvests exit IP, ASN "
                  "and location."))

    def on_run(self):
        if self.running:
            return
        fast = self.test_mode.get() == FAST_MODE
        url = self.url.get().strip()
        try:
            runs = max(1, int(self.runs.get().strip()))
        except ValueError:
            messagebox.showerror("ProxyTester", "Runs per proxy must be a number.")
            return
        # Fast (connect-only) mode ignores the Test URL - it CONNECTs to a
        # neutral target - so only require a URL for Full mode.
        if not fast and not url:
            messagebox.showerror("ProxyTester", "Test URL is required.")
            return

        proxies = []
        bad = 0
        for line in self.proxy_text.get("1.0", "end").splitlines():
            if not line.strip():
                continue
            parsed = parse_proxy_line(line)
            if parsed:
                proxies.append(parsed)
            else:
                bad += 1
        if not proxies:
            messagebox.showerror("ProxyTester", "Enter at least one valid proxy.")
            return
        if bad:
            self.status_lbl.config(text=f"Skipped {bad} unparseable line(s)")

        self.tree.delete(*self.tree.get_children())
        self._row_full = {}
        self.running = True
        self.stop_event.clear()
        self.run_btn.config(text="Stop", style="Stop.TButton",
                            command=self.on_stop)
        # Live progress counter (updated per result as they stream in).
        self._run_total = len(proxies)
        self._tested = self._live = 0
        self._count_cfg = ("Tested", "live", "dead")
        self._ping_mode = None
        self._run_started = time.perf_counter()
        self.status_lbl.config(text=f"Testing 0/{len(proxies)}...")

        worker = threading.Thread(
            target=self._run_pool, args=(proxies, url, runs, fast), daemon=True)
        worker.start()
        self.after(100, self._drain_queue)

    def on_stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.run_btn.config(state="disabled")
        self.status_lbl.config(text="Stopping...")

    def _run_pool(self, proxies, url, runs, fast=False):
        # Proxy testing is pure network I/O, so parallelism is the main speed
        # lever. The connect-only fast path is cheap enough to run far wider
        # (and with a short timeout) than the full-GET path.
        if fast:
            workers = get_fast_workers()
            fast_to = get_fast_timeout()
        else:
            workers = min(MAX_WORKERS_CAP,
                          max(get_workers(), min(len(proxies), 40)))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {}
                for p in proxies:
                    if fast:
                        fut = pool.submit(test_proxy_fast, p, runs, fast_to,
                                          self.stop_event)
                    else:
                        fut = pool.submit(test_proxy, p, url, runs,
                                          DEFAULT_TIMEOUT, self.stop_event)
                    futures[fut] = p
                for fut, p in futures.items():
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = {"proxy": f"{p['host']}:{p['port']}",
                                  "status": "unreachable", "code": "-",
                                  "median": None, "success": 0, "runs": runs,
                                  "exit_ip": "", "reason": str(e)}
                    self.queue.put(result)
        finally:
            self.queue.put({"_done": True})

    def _drain_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item.get("_done"):
                    self._finish()
                    return
                self._insert_row(item)
                # Live counter: count proxy-test results and proxy-ping results
                # (both stream one row per proxy); skip direct site-ping rows.
                cfg = getattr(self, "_count_cfg", None)
                if cfg and not item.get("_ping"):
                    self._tested += 1
                    if item.get("status") == "OK":
                        self._live += 1
                    total = getattr(self, "_run_total", 0) or self._tested
                    verb, live_word, dead_word = cfg
                    dead = self._tested - self._live
                    pct = int(self._tested * 100 / total) if total else 0
                    self.status_lbl.config(
                        text=f"{verb} {self._tested}/{total} ({pct}%) - "
                             f"{self._live} {live_word}, {dead} {dead_word}")
        except queue.Empty:
            pass
        if self.running:
            self.after(100, self._drain_queue)

    def _insert_row(self, r):
        if r.get("_ping"):
            rng = ("-" if r["min"] is None
                   else f"min {r['min']:.0f} / max {r['max']:.0f} ms")
            self.tree.insert("", "end", values=(
                f"PING  {r['name']} - {r['host']}", r["status"], "-",
                _fmt_ms(r["median"]), f"{r['success']}/{r['runs']}",
                "", rng, "direct (no proxy)",
            ), tags=(status_tag(r["status"]),))
            return
        if r.get("_pping"):
            # Carry the proxy's exit IP / provider / location from the prior
            # Run (matched by host:port:user) so a ping row keeps its geo. Fall
            # back to the ping target when there's no prior Run to draw from.
            ident = self._proxy_ident(r["proxy"])
            exit_ip, org, location = getattr(self, "_loc_map", {}).get(
                ident, ("", "", f"via proxy -> {r['name']} ({r['target']})"))
            item = self.tree.insert("", "end", values=(
                f"PING  {r['proxy']}", r["status"],
                str(r["code"]) if r["code"] is not None else "-",
                _fmt_ms(r["median"]), f"{r['success']}/{r['runs']}",
                exit_ip, org, location,
            ), tags=(status_tag(r["status"]),))
            self._row_full[item] = r.get("full", "")
            return
        item = self.tree.insert("", "end", values=(
            r["proxy"], r["status"], r["code"], _fmt_ms(r["median"]),
            f"{r['success']}/{r['runs']}", r["exit_ip"],
            r.get("org", ""), r.get("location", ""),
        ), tags=(status_tag(r["status"]),))
        self._row_full[item] = r.get("full", "")

    def _sort_by(self, col):
        """Sort the visible rows by a column (numeric when possible),
        toggling direction each click. Non-numeric / blank cells (e.g. a dead
        proxy's '-' latency) sort to the end on an ascending pass."""
        items = [(self.tree.set(i, col), i) for i in self.tree.get_children("")]

        def key(pair):
            v = pair[0]
            try:
                return (0, float(v))
            except ValueError:
                return (1, v.lower())

        rev = self._sort_dir.get(col, False)
        items.sort(key=key, reverse=rev)
        self._sort_dir[col] = not rev
        for idx, (_, i) in enumerate(items):
            self.tree.move(i, "", idx)

    def on_ping_site(self):
        if self.running:
            return
        choice = self.ping_site_var.get()
        presets = dict(RETAIL_SITES)
        if choice == "All presets":
            targets = list(RETAIL_SITES)
        elif choice in presets:
            targets = [(choice, presets[choice])]
        else:  # Custom (Test URL)
            url = self.url.get().strip()
            if not url:
                messagebox.showerror(
                    "ProxyTester",
                    "Enter a Test URL to ping, or pick a preset site.")
                return
            host, _ = _host_port_from_target(url)
            targets = [(host, url)]
        try:
            runs = max(1, int(self.runs.get().strip()))
        except ValueError:
            runs = 5

        via_proxy = self.ping_via_proxy.get()
        proxies = None
        if via_proxy:
            # Through-proxies pings ONE target from every proxy; a preset
            # sweep would be proxies x sites, so require a single site.
            if len(targets) != 1:
                messagebox.showerror(
                    "ProxyTester",
                    "Pick one site (not 'All presets') to ping through "
                    "proxies.")
                return
            proxies = [p for p in
                       (parse_proxy_line(ln) for ln
                        in self.proxy_text.get("1.0", "end").splitlines())
                       if p]
            if not proxies:
                messagebox.showerror(
                    "ProxyTester",
                    "Paste proxies above to ping the site through them.")
                return

        # Before wiping the table, harvest each proxy's exit IP / provider /
        # location from the just-finished Run so we can carry that geo context
        # onto the ping rows (the CONNECT ping itself resolves no geo).
        self._loc_map = {}
        if via_proxy:
            for iid in self.tree.get_children():
                vals = self.tree.item(iid, "values")
                if str(vals[0]).startswith("PING"):
                    continue
                ident = self._proxy_ident(vals[0])
                if ident:
                    self._loc_map[ident] = (vals[5], vals[6], vals[7])
        # A fresh ping starts with a clean table (results replace the Run).
        self.tree.delete(*self.tree.get_children())
        self._row_full = {}

        self.running = True
        self.stop_event.clear()
        self.run_btn.config(state="disabled")
        self.ping_btn.config(text="Stop", style="Stop.TButton",
                             command=self.on_stop)
        self._ping_mode = "proxy" if via_proxy else "direct"
        self._run_started = time.perf_counter()
        if via_proxy:
            self._run_total = len(proxies)
            self._tested = self._live = 0
            self._count_cfg = ("Pinged", "reachable", "failed")
            self.status_lbl.config(
                text=f"Pinging {targets[0][0]} through 0/{len(proxies)}...")
            threading.Thread(
                target=self._proxy_ping_worker,
                args=(proxies, targets[0], runs), daemon=True).start()
        else:
            self._count_cfg = None       # direct ping: no per-proxy counter
            self.status_lbl.config(text=f"Pinging {len(targets)} site(s)...")
            threading.Thread(target=self._ping_worker, args=(targets, runs),
                             daemon=True).start()
        self.after(100, self._drain_queue)

    def _ping_worker(self, targets, runs):
        try:
            for name, target in targets:
                if self.stop_event.is_set():
                    break
                r = ping_site(name, target, runs, DEFAULT_TIMEOUT,
                              self.stop_event)
                r["_ping"] = True
                self.queue.put(r)
        finally:
            self.queue.put({"_done": True})

    def _proxy_ping_worker(self, proxies, target, runs):
        name, url = target
        workers = min(MAX_WORKERS_CAP, max(get_workers(), min(len(proxies), 40)))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(ping_site_via_proxy, p, name, url, runs,
                                    DEFAULT_TIMEOUT, self.stop_event): p
                        for p in proxies}
                for fut in futs:
                    try:
                        self.queue.put(fut.result())
                    except Exception:
                        pass
        finally:
            self.queue.put({"_done": True})

    def _finish(self):
        stopped = self.stop_event.is_set()
        self.running = False
        self.run_btn.config(text="Run", style="Accent.TButton",
                            command=self.on_run, state="normal")
        self.ping_btn.config(text="Ping site", style="TButton",
                             command=self.on_ping_site, state="normal")
        base = "Stopped" if stopped else "Done"
        elapsed_s = (time.perf_counter()
                    - getattr(self, "_run_started", time.perf_counter()))
        elapsed = _fmt_elapsed(elapsed_s)
        if getattr(self, "_ping_mode", None) == "proxy":
            # Summarise the CONNECT-tunnel ping run from the live counters.
            ok, total = self._live, self._tested
            rate = f", {total / max(elapsed_s, 0.001):.0f}/s" if not stopped else ""
            self.status_lbl.config(
                text=f"{base} in {elapsed} - {total} pinged, {ok} reachable, "
                     f"{total - ok} failed{rate}")
        else:
            tested, alive = self._proxy_counts()
            dead = tested - alive
            rate = f", {tested / max(elapsed_s, 0.001):.0f}/s" if not stopped else ""
            self.status_lbl.config(
                text=f"{base} in {elapsed} - {tested} tested, {alive} live, "
                     f"{dead} dead{rate}")
        self._ping_mode = None

    def _proxy_counts(self):
        """(tested, live) over proxy-test rows only (Site-ping rows excluded)."""
        tested = alive = 0
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if str(vals[0]).startswith("PING"):
                continue
            tested += 1
            if vals[1] == "OK":
                alive += 1
        return tested, alive

    @staticmethod
    def _proxy_ident(s):
        """Identity (host, port, user) of a proxy line or masked display, so a
        result row can be matched back to its original input line."""
        p = parse_proxy_line(str(s))
        if not p:
            return None
        return (p["host"], str(p["port"]), p.get("user") or "")

    def _update_proxy_count(self, _e=None, force=False):
        """Live count of non-empty proxy lines, shown in the box's header."""
        if not force and not self.proxy_text.edit_modified():
            return
        n = sum(1 for ln in self.proxy_text.get("1.0", "end").splitlines()
                if ln.strip())
        self.proxy_hdr.config(
            text=f"Proxies (host:port:user:pass, one per line) - {n} in list")
        self.proxy_text.edit_modified(False)

    @staticmethod
    def _full_key(line):
        """Canonical host:port:user:pass key for a proxy line - includes the
        password, so proxies that differ only by a session token IN the password
        (IPRoyal, Rayobyte) are told apart. None if unparseable."""
        p = parse_proxy_line(str(line))
        if not p:
            return None
        if p.get("user") and p.get("pw") is not None:
            return f"{p['host']}:{p['port']}:{p['user']}:{p['pw']}"
        return f"{p['host']}:{p['port']}"

    def _cull(self, want_removed, label):
        """Shared cull: `want_removed(vals)` decides if a result row's proxy
        should be dropped. Removes those rows AND the exact matching input lines
        (matched by full key, so session-in-password proxies cull correctly).
        Rows without a real proxy (direct Site-ping) are ignored."""
        remove_keys, remove_iids = set(), []
        candidates = 0
        for iid in self.tree.get_children():
            full = self._row_full.get(iid)
            if not full:
                continue                       # direct-ping / non-proxy row
            candidates += 1
            vals = self.tree.item(iid, "values")
            if want_removed(vals):
                k = self._full_key(full)
                if k:
                    remove_keys.add(k)
                remove_iids.append(iid)
        if not candidates:
            self.status_lbl.config(text="Run or Ping proxies first")
            return
        if not remove_iids:
            self.status_lbl.config(text=f"No {label} proxies to cull")
            return
        for iid in remove_iids:
            self.tree.delete(iid)
            self._row_full.pop(iid, None)
        kept = [ln for ln in self.proxy_text.get("1.0", "end").splitlines()
                if ln.strip() and self._full_key(ln) not in remove_keys]
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", "\n".join(kept))
        self._update_proxy_count(force=True)
        self.status_lbl.config(
            text=f"Culled {len(remove_iids)} {label}; kept {len(kept)}")

    def on_cull_dead(self):
        """Drop dead (non-OK) proxies - from Run results OR proxied Site-ping
        results - and their input lines."""
        self._cull(lambda vals: vals[1] != "OK", "dead")

    def on_cull_slow(self):
        """Speed filter (REVERSIBLE): rebuild the proxy list from the intact
        results table, keeping only proxies whose median latency is <= the ms
        threshold. Because it re-derives from the full results each time (never
        deleting result rows), raising the threshold brings previously-excluded
        proxies back. Proxies with no median (dead) are kept for Cull dead."""
        try:
            thr = max(1, int(self.slow_ms.get().strip()))
        except (TypeError, ValueError):
            self.status_lbl.config(text="Enter a valid ms threshold")
            return
        kept, seen, excluded, candidates = [], set(), 0, 0
        for iid in self.tree.get_children():
            full = self._row_full.get(iid)
            if not full:
                continue                       # direct-ping / non-proxy row
            candidates += 1
            vals = self.tree.item(iid, "values")
            try:
                ms = float(vals[3])
            except (TypeError, ValueError):
                ms = None                      # dead row - keep (Cull dead's job)
            if ms is not None and ms > thr:
                excluded += 1
                continue
            key = self._full_key(full)
            if key in seen:
                continue
            seen.add(key)
            kept.append(full)
        if not candidates:
            self.status_lbl.config(text="Run or Ping proxies first")
            return
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", "\n".join(kept))
        self._update_proxy_count(force=True)
        self.status_lbl.config(
            text=f"Speed filter <={thr}ms: kept {len(kept)}, {excluded} slower "
                 "excluded")

    def on_dedupe(self):
        """Drop duplicate proxy lines, keeping the first occurrence and the
        original order. Matches on the full host:port:user:pass (password
        included), so proxies that differ only by a session token are kept -
        they're distinct sessions, not duplicates. Unparseable lines are kept
        as-is."""
        seen, kept, removed = set(), [], 0
        for ln in self.proxy_text.get("1.0", "end").splitlines():
            if not ln.strip():
                continue
            key = self._full_key(ln)
            if key is None:            # can't parse it - never silently drop it
                kept.append(ln)
                continue
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(ln)
        if not removed:
            self.status_lbl.config(text="No duplicates found")
            return
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", "\n".join(kept) + "\n")
        self.proxy_text.mark_set("insert", "end-1c")
        self.status_lbl.config(
            text=f"Removed {removed} duplicate(s) - {len(kept)} left")

    def on_shuffle(self):
        """Randomly reorder the pasted proxy lines in place."""
        lines = [ln for ln in self.proxy_text.get("1.0", "end").splitlines()
                 if ln.strip()]
        if len(lines) < 2:
            self.status_lbl.config(text="Nothing to shuffle")
            return
        random.shuffle(lines)
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", "\n".join(lines))
        self.status_lbl.config(text=f"Shuffled {len(lines)} proxy(ies)")


def center_over_parent(top, parent, w=None, h=None):
    """Position a popup centered over the main app window (not top-left of a
    huge monitor), clamped to the screen so nothing (e.g. buttons) is cut off."""
    top.update_idletasks()
    root = parent.winfo_toplevel()
    w = w or top.winfo_reqwidth()
    h = h or top.winfo_reqheight()
    sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
    w = min(w, sw - 40)
    h = min(h, sh - 80)
    px, py = root.winfo_rootx(), root.winfo_rooty()
    pw, ph = root.winfo_width(), root.winfo_height()
    x = max(0, min(px + (pw - w) // 2, sw - w))
    y = max(0, min(py + (ph - h) // 2, sh - h))
    top.geometry(f"{w}x{h}+{x}+{y}")


def make_modal(top):
    """Grab input for a modal dialog, but drop the grab while the window is
    minimized and re-take it when restored.

    A plain grab_set() left on an iconified (minimized) toplevel captures ALL of
    the app's input for a window that can't be clicked, which freezes the whole
    app - reported after minimizing the main window while a dialog was open. The
    Map/Unmap handlers keep the grab tied to an actually-visible window.
    """
    def _regrab():
        try:
            if top.winfo_exists() and top.winfo_viewable():
                top.grab_set()
        except Exception:
            pass

    def _on_map(e):
        if e.widget is top:
            top.after(60, _regrab)      # after the WM finishes restoring

    def _on_unmap(e):
        if e.widget is top:
            try:
                top.grab_release()
            except Exception:
                pass

    top.bind("<Map>", _on_map, add="+")
    top.bind("<Unmap>", _on_unmap, add="+")
    _regrab()


def fit_to_content(top):
    """Grow a dialog so its content - including rows revealed AFTER it opened
    (e.g. the Proxy-Haus block) - actually fits. Never shrinks, so a size the
    user chose is respected; clamped to the screen and nudged up if the bottom
    (where the action buttons live) would fall off."""
    top.update_idletasks()
    sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
    w = min(max(top.winfo_reqwidth(), top.winfo_width()), sw - 40)
    h = min(max(top.winfo_reqheight(), top.winfo_height()), sh - 80)
    x, y = top.winfo_x(), top.winfo_y()
    x = max(0, min(x, sw - w))
    y = max(0, min(y, sh - h))
    top.geometry(f"{w}x{h}+{x}+{y}")


_GEOM_RE = re.compile(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")


def restore_geometry(top, parent, key):
    """Reopen a dialog at the size/position the user left it last time, but only
    if that still lands on THIS screen - otherwise centre it over the app."""
    top.update_idletasks()
    m = _GEOM_RE.fullmatch(str(load_setting(f"win_geom_{key}", "")).strip())
    if m:
        w, h, x, y = (int(v) for v in m.groups())
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        if (200 <= w <= sw and 150 <= h <= sh
                and -20 <= x <= sw - 100 and -20 <= y <= sh - 100):
            top.geometry(f"{w}x{h}+{x}+{y}")
            return
    center_over_parent(top, parent)


def persist_geometry(top, key):
    """Remember where/how big the user left a dialog."""
    try:
        save_setting(f"win_geom_{key}", top.geometry())
    except Exception:
        pass


def ask_generate_options(parent, asn_count):
    """Modal dialog: choose static/rotating, proxies-per-ASN, and (for static)
    sticky minutes. Returns (mode, count, sesstime) or None if cancelled.
    sesstime is an int or None."""
    top = tk.Toplevel(parent)
    top.title("Generate proxies")
    top.configure(bg=BASE)
    top.transient(parent.winfo_toplevel())
    top.resizable(False, False)

    mode = tk.StringVar(value="rotating")
    count = tk.StringVar(value="1")
    sesstime = tk.StringVar(value="")
    result = {}

    ttk.Label(top, text=f"Generating for {asn_count} selected ASN(s)",
              style="Muted.TLabel").pack(anchor="w", padx=16, pady=(14, 8))

    ttk.Label(top, text="Session type").pack(anchor="w", padx=16)
    ttk.Radiobutton(top, text="Rotating  -  new IP every request",
                    variable=mode, value="rotating",
                    command=lambda: _sync_sticky()).pack(anchor="w", padx=24)
    ttk.Radiobutton(top, text="Static  -  sticky IP per proxy",
                    variable=mode, value="static",
                    command=lambda: _sync_sticky()).pack(anchor="w", padx=24)

    row = ttk.Frame(top)
    row.pack(anchor="w", padx=16, pady=(10, 2))
    ttk.Label(row, text="Proxies per ASN").pack(side="left")
    ttk.Entry(row, textvariable=count, width=6).pack(side="left", padx=8)

    # Sticky-minutes row: shown only when Static is selected.
    row2 = ttk.Frame(top)
    ttk.Label(row2, text="Sticky minutes (max 1440, blank = 60)").pack(
        side="left")
    ttk.Entry(row2, textvariable=sesstime, width=6).pack(side="left", padx=8)

    def _sync_sticky():
        if mode.get() == "static":
            row2.pack(anchor="w", padx=16, pady=(2, 4))
        else:
            row2.pack_forget()
        top.update_idletasks()
        center_over_parent(top, parent)

    _sync_sticky()

    def ok():
        try:
            n = max(1, int(count.get().strip()))
        except ValueError:
            messagebox.showerror("Generate proxies",
                                 "Proxies per ASN must be a number.")
            return
        st = sesstime.get().strip()
        if st:
            try:
                st = max(1, int(st))
            except ValueError:
                messagebox.showerror("Generate proxies",
                                     "Sticky minutes must be a number.")
                return
        elif mode.get() == "static":
            st = 60          # blank on Static defaults to a 60-minute session
        else:
            st = None        # rotating ignores sesstime anyway
        result["mode"] = mode.get()
        result["count"] = n
        result["sesstime"] = st
        top.destroy()

    btns = ttk.Frame(top)
    btns.pack(fill="x", padx=16, pady=14)
    ttk.Button(btns, text="Generate", style="Accent.TButton",
               command=ok).pack(side="left")
    ttk.Button(btns, text="Cancel", command=top.destroy).pack(side="left", padx=8)

    center_over_parent(top, parent)
    make_modal(top)
    top.wait_window()
    if result:
        return result["mode"], result["count"], result["sesstime"]
    return None


def show_output_popup(parent, title, text, shuffle=False):
    """Modal-ish popup with a scrollable, copyable text box."""
    top = tk.Toplevel(parent)
    top.title(title)
    top.configure(bg=BASE)
    top.transient(parent.winfo_toplevel())

    ttk.Label(top, text=title, style="Header.TLabel").pack(
        anchor="w", padx=14, pady=(12, 6))

    # Pin the buttons to the bottom FIRST so they can never be pushed off-screen
    # by a long list; the text box then fills the space above them.
    btns = ttk.Frame(top)
    btns.pack(side="bottom", fill="x", padx=14, pady=12)

    box = tk.Text(top, wrap="none", height=16)
    style_text(box)
    box.pack(side="top", fill="both", expand=True, padx=14)
    box.insert("1.0", text)

    def copy():
        top.clipboard_clear()
        top.clipboard_append(box.get("1.0", "end").strip())
        top.update_idletasks()
        copy_btn.config(text="Copied!")

    copy_btn = ttk.Button(btns, text="Copy all", style="Accent.TButton",
                          command=copy)
    copy_btn.pack(side="left")

    if shuffle:
        def do_shuffle():
            lines = [ln for ln in box.get("1.0", "end").splitlines() if ln.strip()]
            random.shuffle(lines)
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(lines))
            copy_btn.config(text="Copy all")
        ttk.Button(btns, text="Shuffle", command=do_shuffle).pack(
            side="left", padx=8)

    ttk.Button(btns, text="Close", command=top.destroy).pack(side="left", padx=8)
    top.resizable(True, True)
    center_over_parent(top, parent, 720, 520)
    box.focus_set()


def _reveal_in_folder(path):
    """Open the containing folder, selecting the file where the OS supports it."""
    folder = os.path.dirname(path) or "."
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception:
        try:
            os.startfile(folder)     # Windows fallback
        except Exception:
            pass


def export_tree_csv(tree, columns, headings, full_map=None, full_col=0,
                    items=None):
    """Write tree rows to CSV. `items` limits the export to specific row ids
    (e.g. the current selection); None exports every visible row. If full_map
    (item id -> full 'host:port:user:pass') is given, its value replaces the
    masked proxy cell at full_col so exports carry usable credentials."""
    rows = list(items) if items is not None else list(tree.get_children())
    if not rows:
        messagebox.showinfo("Export CSV", "No results to export yet.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        title="Export results to CSV",
        initialdir=_exports_dir(),
        initialfile="proxytester_results.csv")
    if not path:
        return
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headings)
            for iid in rows:
                vals = list(tree.item(iid, "values"))
                if full_map and full_map.get(iid) and 0 <= full_col < len(vals):
                    vals[full_col] = full_map[iid]     # unmasked proxy
                writer.writerow(vals)
    except OSError as e:
        messagebox.showerror("Export CSV", f"Could not write file:\n{e}")
        return
    _reveal_in_folder(path)          # pop the folder open with the file selected


class ConverterTab(ttk.Frame):
    """Convert any provider proxy format into copy-ready host:port:user:pass."""

    def __init__(self, master):
        super().__init__(master, padding=14)
        self._build()

    def _build(self):
        ttk.Label(
            self,
            text="Paste proxy URLs / python snippets / any format (one per line)",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="host:port:user:pass").grid(
            row=0, column=2, sticky="w")

        self.src = tk.Text(self, width=52, height=18)
        style_text(self.src)
        self.src.grid(row=1, column=0, sticky="nsew")
        paste_appends_to_end(self.src)

        mid = ttk.Frame(self)
        mid.grid(row=1, column=1, sticky="ns", padx=14)
        ttk.Button(mid, text="Convert  →", style="Accent.TButton",
                   command=self.on_convert).pack(pady=(40, 8))
        ttk.Button(mid, text="Copy", command=self.on_copy).pack(pady=8)
        ttk.Button(mid, text="Clear", command=self.on_clear).pack(pady=8)
        ttk.Label(mid, text="Force ASN", style="Muted.TLabel").pack(pady=(20, 0))
        self.asn_var = tk.StringVar()
        ttk.Entry(mid, textvariable=self.asn_var, width=10).pack(pady=(2, 0))
        ttk.Label(mid, text="(swaps cc-> ASN)", style="Muted.TLabel").pack()

        self.out = tk.Text(self, width=52, height=18)
        style_text(self.out)
        self.out.grid(row=1, column=2, sticky="nsew")

        self.status_lbl = ttk.Label(self, text="", style="Muted.TLabel")
        self.status_lbl.grid(row=2, column=0, columnspan=3, sticky="w",
                             pady=(8, 0))

        self.columnconfigure(0, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(1, weight=1)

    def on_convert(self):
        lines = self.src.get("1.0", "end").splitlines()
        force_asn = self.asn_var.get().strip() or None
        out, ok, bad = [], 0, 0
        for line in lines:
            if not line.strip():
                continue
            result = convert_proxy_line(line, force_asn=force_asn)
            if result:
                out.append(result)
                ok += 1
            else:
                bad += 1
        self.out.delete("1.0", "end")
        self.out.insert("1.0", "\n".join(out))
        msg = f"Converted {ok} proxy(ies)."
        if force_asn:
            msg += f" ASN set to {force_asn}."
        if bad:
            msg += f" Skipped {bad} unparseable line(s)."
        self.status_lbl.config(text=msg)

    def on_copy(self):
        text = self.out.get("1.0", "end").strip()
        if not text:
            self.status_lbl.config(text="Nothing to copy - convert first.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self.status_lbl.config(text="Copied to clipboard.")

    def on_clear(self):
        self.src.delete("1.0", "end")
        self.out.delete("1.0", "end")
        self.status_lbl.config(text="")


def open_generate_dialog(parent, text_widget):
    """Batch generator: build proxy lines for one or more residential providers
    at once and drop them into `text_widget`. Each checked provider gets its OWN
    sticky lifetime (with its max called out); shared settings are count and
    location. Proxy-Haus adds a click-to-pick ASN menu."""
    configured = configured_resi_providers()
    if not configured:
        # Distinguish "no credentials yet" from "you hid them all".
        hidden_n = len(configured_resi_providers(include_hidden=True))
        msg = ("Add a provider's username:password on the Settings tab first "
               "(Oxylabs Residential, IPRoyal, Bright Data, Proxy-Haus, "
               "Rayobyte, or PacketStream).")
        if hidden_n:
            msg = (f"All {hidden_n} configured provider(s) are hidden from the "
                   "generator. Re-tick 'in generator' next to a provider on "
                   "the Settings tab - your credentials are still saved.")
        messagebox.showinfo("Generate batch", msg)
        return
    top = tk.Toplevel(parent)
    top.title("Generate residential batch")
    top.configure(bg=BASE)
    top.transient(parent.winfo_toplevel())
    top.resizable(True, True)      # never trap the Generate/Cancel buttons
    GEOM_KEY = "generate_batch"

    def _close():
        """Remember the window AND every selection, so reopening the dialog
        looks exactly like it did when you left it."""
        persist_geometry(top, GEOM_KEY)
        try:
            save_setting("generate_batch_state", {
                "providers": [n for n, v in provider_vars.items() if v.get()],
                "lifetimes": {n: v.get() for n, v in life_vars.items()},
                "count": count.get(),
                "rotating": bool(rotating.get()),
                "append": bool(append.get()),
                "asns": [a for a, v in asn_vars.items() if v.get()],
                "fresh": bool(fresh.get()),
                "region_type": region_type.get(),
                "regions": [c for c, v in region_vars.items() if v.get()],
            })
        except Exception:
            pass          # never block closing the dialog over a saved setting
        top.destroy()

    # Every control is restored exactly as it was left last time (saved on
    # Generate, Cancel or close). First ever run starts with nothing selected.
    saved = load_setting("generate_batch_state", {})
    if not isinstance(saved, dict):
        saved = {}
    saved_provs = set(saved.get("providers") or [])
    saved_life = saved.get("lifetimes") or {}
    saved_asns = set(saved.get("asns") or [])
    provider_vars = {name: tk.BooleanVar(value=name in saved_provs)
                     for name in configured}
    life_vars = {}            # provider -> StringVar (only providers with a cap)
    rtype0 = saved.get("region_type")
    region_type = tk.StringVar(
        value=rtype0 if rtype0 in ("Country", "State", "City") else "Country")
    count = tk.StringVar(value=str(saved.get("count") or "500"))
    rotating = tk.BooleanVar(value=bool(saved.get("rotating")))
    append = tk.BooleanVar(value=bool(saved.get("append")))
    region_vars = {}          # canonical -> BooleanVar (rebuilt per region type)
    asn_vars = {a: tk.BooleanVar(value=a in saved_asns)
                for a, _, _ in PROXYHAUS_ASNS}
    fresh = tk.BooleanVar(value=bool(saved.get("fresh")))

    frm = ttk.Frame(top, padding=(16, 14))
    frm.pack(fill="both", expand=True)
    row = 0

    ttk.Label(frm, text="Providers (check to include; set each one's sticky "
                        "lifetime)").grid(row=row, column=0, columnspan=2,
                                          sticky="w", pady=(0, 4))
    row += 1
    prov_box = ttk.Frame(frm)
    prov_box.grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    prov_life_frames = {}
    # Providers fill COLUMNS of at most PROV_ROWS each, so adding a provider
    # widens the dialog instead of making it ever taller.
    PROV_ROWS = 5
    prov_cb_widgets = {}
    rule_lbls = {}            # provider -> the grey "(1-120m or 1-2h)" label
    for i, name in enumerate(configured):
        spec = RESI_PROVIDERS[name]
        grow, gcol = i % PROV_ROWS, i // PROV_ROWS
        # One cell per provider holds its checkbox AND its lifetime box, so the
        # pair hides together (Rayobyte during a rotating run) and columns stay
        # aligned regardless of how wide a provider's lifetime hint is.
        cell = ttk.Frame(prov_box)
        cell.grid(row=grow, column=gcol, sticky="w", pady=2, padx=(0, 18))
        cb = ttk.Checkbutton(cell, text=name, variable=provider_vars[name],
                             command=lambda: refresh_ui())
        cb.pack(side="left", padx=(0, 8))
        prov_cb_widgets[name] = cell     # hide/show the whole cell
        lf = ttk.Frame(cell)
        lf.pack(side="left")
        prov_life_frames[name] = lf
        mx = spec.get("max_min")
        if mx:
            lv = tk.StringVar(value=str(saved_life.get(name) or "30m"))
            life_vars[name] = lv
            ttk.Label(lf, text="sticky").pack(side="left")
            ttk.Entry(lf, textvariable=lv, width=8).pack(side="left", padx=(4, 4))
            # Kept so the rule text can change live (Proxy-Haus + Fresh).
            rule_lbls[name] = ttk.Label(lf, text=f"({spec.get('life_rule', '')})",
                                        style="Muted.TLabel")
            rule_lbls[name].pack(side="left")
        else:
            # No TTL token at all (Bright Data, PacketStream) - say why.
            note = spec.get("life_note",
                            "no lifetime token; sticky IP holds ~30m")
            ttk.Label(lf, text=f"({note})",
                      style="Muted.TLabel").pack(side="left")

    def set_all_to(target_min):
        # Each provider gets the value closest to `target_min` that it allows -
        # i.e. min(target, its cap), so a 3h target lands Proxy-Haus on 2h and
        # Rayobyte on 1h while Oxylabs/IPRoyal take the full 3h.
        for pname, lv in life_vars.items():
            cap = resi_life_caps(pname, fresh.get())[0]
            lv.set(_fmt_minutes(min(target_min, cap)))

    mrow = ttk.Frame(frm)
    mrow.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
    row += 1
    ttk.Button(mrow, text="Set all to max",
               command=lambda: set_all_to(10 ** 9)).pack(side="left")
    ttk.Button(mrow, text="1hr",
               command=lambda: set_all_to(60)).pack(side="left", padx=(6, 0))
    ttk.Button(mrow, text="3hr",
               command=lambda: set_all_to(180)).pack(side="left", padx=(6, 0))
    ttk.Label(mrow, text="(closest each provider allows)",
              style="Muted.TLabel").pack(side="left", padx=(8, 0))

    # Label + dropdown packed in ONE cell - gridding them into separate columns
    # let the dropdown drift to the far right when column 0 stretched.
    creg = ttk.Frame(frm)
    creg.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 2))
    row += 1
    ttk.Label(creg, text="Country: United States (fixed)",
              style="Muted.TLabel").pack(side="left", padx=(0, 16))
    ttk.Label(creg, text="Region type").pack(side="left")
    ttk.Combobox(creg, textvariable=region_type, width=12, state="readonly",
                 values=["Country", "State", "City"]).pack(side="left",
                                                           padx=(8, 0))

    # Scrollable checkbox list of regions - repopulated when region type changes.
    list_lbl = ttk.Label(frm, text="Regions (check one or more)")
    list_lbl.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 2))
    row += 1
    holder = ttk.Frame(frm)
    holder.grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    canvas = tk.Canvas(holder, bg=SURFACE, highlightthickness=1,
                       highlightbackground=SURFACE2, width=300, height=150)
    vsb = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    canvas.bind("<MouseWheel>",
                lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    def rebuild_regions(*_):
        region_vars.clear()
        for w in inner.winfo_children():
            w.destroy()
        opts = REGION_OPTIONS.get(region_type.get())
        if not opts:
            # Country-wide needs no picker - hide the label AND the box so the
            # dialog doesn't carry ~180px of dead space, which was pushing the
            # Generate/Cancel buttons off the bottom.
            list_lbl.grid_remove()
            holder.grid_remove()
            return
        list_lbl.grid()
        holder.grid()
        for canon, disp in opts:
            v = tk.BooleanVar(value=False)
            region_vars[canon] = v
            ttk.Checkbutton(inner, text=disp, variable=v).pack(
                anchor="w", padx=6)
        canvas.yview_moveto(0)
        fit_to_content(top)

    region_type.trace_add("write", rebuild_regions)
    rebuild_regions()
    # rebuild_regions() has just created the vars for the restored region type,
    # so the saved ticks can be re-applied now.
    for _canon in (saved.get("regions") or []):
        if _canon in region_vars:
            region_vars[_canon].set(True)

    cnt = ttk.Frame(frm)
    cnt.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
    row += 1
    ttk.Label(cnt, text="Count (per provider)").pack(side="left")
    ttk.Entry(cnt, textvariable=count, width=8).pack(side="left", padx=(6, 0))

    # Proxy-Haus ASN picker: inline checkboxes - always-visible, always-on
    # multi-select (no popup/menu that could drop the selection). Pick any
    # number; shown only while Proxy-Haus is checked.
    # Everything Proxy-Haus-only lives in ONE block, shown only while Proxy-Haus
    # is checked: the Fresh toggle (its own pool, with a longer sticky cap) and
    # the carrier ASNs, wrapped 3-per-row so the last one never clips off.
    asn_row = ttk.Frame(frm)
    asn_row.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
    row += 1
    head = ttk.Frame(asn_row)
    head.pack(anchor="w")
    ttk.Label(head, text="Proxy-Haus:").pack(side="left", padx=(0, 8))
    ttk.Checkbutton(head, text="Fresh", variable=fresh,
                    command=lambda: _fresh_changed()).pack(side="left")
    grid_f = ttk.Frame(asn_row)
    grid_f.pack(anchor="w", pady=(2, 0))
    ttk.Label(grid_f, text="ASNs:").grid(row=0, column=0, sticky="w",
                                         padx=(0, 8))
    for i, (a, aname, cat) in enumerate(PROXYHAUS_ASNS):
        ttk.Checkbutton(grid_f, text=f"{aname} {a}",
                        variable=asn_vars[a]).grid(
            row=i // 3, column=1 + (i % 3), sticky="w", padx=(0, 10), pady=1)

    def _fresh_changed():
        """Fresh swaps Proxy-Haus onto a pool with a much longer sticky cap, so
        the grey rule text has to follow the toggle."""
        lbl = rule_lbls.get("Proxy-Haus")
        if lbl is not None:
            lbl.config(text=f"({resi_life_caps('Proxy-Haus', fresh.get())[3]})")

    rot_cb = ttk.Checkbutton(
        frm, text="Rotating (new IP per request, no sticky session)",
        variable=rotating, command=lambda: refresh_ui())
    rot_cb.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
    row += 1
    ttk.Checkbutton(frm, text="Append to existing list (instead of replacing)",
                    variable=append).grid(row=row, column=0, columnspan=2,
                                          sticky="w")
    row += 1

    def refresh_ui(*_):
        """Hide providers that don't support the current mode (Rayobyte has no
        rotating), show a provider's lifetime box only while it's checked, and
        show the ASN picker only while Proxy-Haus is checked."""
        rot = rotating.get()
        for pname, lf in prov_life_frames.items():
            # A provider that is always-sticky can't do a rotating run.
            unsupported = rot and RESI_PROVIDERS[pname].get("always_session")
            if unsupported:
                prov_cb_widgets[pname].grid_remove()
                lf.pack_forget()
                continue
            prov_cb_widgets[pname].grid()
            # lf is packed inside the provider's cell, not gridded.
            if provider_vars[pname].get():
                lf.pack(side="left")
            else:
                lf.pack_forget()
        ph = provider_vars.get("Proxy-Haus")
        if ph and ph.get():
            asn_row.grid()
        else:
            asn_row.grid_remove()
        _fresh_changed()
        # Rows just appeared/vanished - resize so the buttons stay reachable.
        fit_to_content(top)

    refresh_ui()

    def gen():
        # In rotating mode, drop always-sticky providers (Rayobyte) - they're
        # hidden in the UI too, so this just mirrors that.
        providers = [n for n, v in provider_vars.items() if v.get()
                     and not (rotating.get()
                              and RESI_PROVIDERS[n].get("always_session"))]
        if not providers:
            messagebox.showerror("Generate batch", "Check at least one provider.")
            return
        try:
            n = max(1, int(count.get().strip()))
        except ValueError:
            messagebox.showerror("Generate batch", "Count must be a number.")
            return
        rtype = region_type.get()
        regions = [c for c, v in region_vars.items() if v.get()]
        if rtype in ("State", "City") and not regions:
            messagebox.showerror(
                "Generate batch",
                f"Check at least one {rtype.lower()}, or set Region type to "
                "Country.")
            return
        # Validate each provider's sticky lifetime against its real format rules
        # BEFORE generating - reject and name the first bad one (unless rotating,
        # where lifetime is irrelevant).
        lifetimes = {}
        if not rotating.get():
            for name in providers:
                if name not in life_vars:
                    continue
                mins, lerr = validate_resi_life(
                    name, life_vars[name].get(),
                    fresh.get() and RESI_PROVIDERS[name].get("supports_fresh"))
                if lerr:
                    messagebox.showerror("Generate batch", lerr)
                    return
                lifetimes[name] = mins
        asns = [a for a, v in asn_vars.items() if v.get()]
        lines, err = generate_resi_multi(providers, rtype, regions, lifetimes, n,
                                         rotating.get(), asns, fresh.get())
        if err:
            messagebox.showerror("Generate batch", err)
            return
        text = "\n".join(lines)
        if append.get():
            cur = text_widget.get("1.0", "end").rstrip("\n")
            text = (cur + "\n" + text) if cur else text
        # Trailing newline leaves the caret on a fresh blank line so you can
        # paste more proxies straight below without them running onto the last.
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", text + "\n")
        text_widget.mark_set("insert", "end-1c")
        text_widget.see("end")
        _close()

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
    ttk.Button(btns, text="Generate", style="Accent.TButton",
               command=gen).pack(side="left")
    ttk.Button(btns, text="Cancel", command=_close).pack(side="left", padx=8)
    # Reopen where it was last left, then make sure the content actually fits -
    # the Proxy-Haus block appears only after you tick it, and its extra height
    # used to push Generate/Cancel off the bottom.
    restore_geometry(top, parent, GEOM_KEY)
    fit_to_content(top)
    top.protocol("WM_DELETE_WINDOW", _close)
    make_modal(top)


DEFAULT_MIN_TRUST = 92   # default display floor - the healthy majority shows
                        # after a run; clear/lower the box to see the rest.

# Trust-range buckets for the Trust header filter (label, predicate on trust).
TRUST_BUCKETS = [
    ("90-100", lambda t: isinstance(t, int) and 90 <= t <= 100),
    ("75-89", lambda t: isinstance(t, int) and 75 <= t <= 89),
    ("50-74", lambda t: isinstance(t, int) and 50 <= t <= 74),
    ("25-49", lambda t: isinstance(t, int) and 25 <= t <= 49),
    ("1-24", lambda t: isinstance(t, int) and 1 <= t <= 24),
    ("0 (burnt)", lambda t: t == 0),
    ("no score", lambda t: not isinstance(t, int)),
]


class QualityTab(ttk.Frame):
    """Score each proxy's exit-IP reputation (IPQualityScore + Spamhaus) into a
    single Trust score, so you can rank a list and keep the cleanest IPs."""

    COLUMNS = ("proxy", "exit_ip", "fraud", "type", "flags",
               "blacklist", "ping", "trust")
    HEADINGS = {
        "proxy": "Proxy", "exit_ip": "Exit IP / status", "fraud": "Fraud",
        "type": "Type", "flags": "Flags", "blacklist": "Blacklist",
        "ping": "Ping ms", "trust": "Trust",
    }

    def __init__(self, master):
        super().__init__(master, padding=14)
        self.queue = queue.Queue()
        self.running = False
        self.stop_event = threading.Event()
        self._rows = []
        self._item_full = {}      # tree item id -> full host:port:user:pass
        self._sort_dir = {}       # column -> current sort direction
        self._summary = ""        # persistent run summary (survives filtering)
        self._trust_buckets = set()  # active Trust-range filter (empty = all)
        self._type_filter = set()    # active Type filter (empty = all)
        self._build()

    def _build(self):
        form = ttk.Frame(self)
        form.pack(fill="x")
        self.proxy_hdr = ttk.Label(
            form, text="Proxies (host:port:user:pass, one per line)")
        # Spans the row: as a plain column-0 cell, this (long) header set the
        # column width and indented everything to the right of the box.
        self.proxy_hdr.grid(row=0, column=0, columnspan=4, sticky="w")
        self.proxy_text = tk.Text(form, width=50, height=8)
        style_text(self.proxy_text)
        self.proxy_text.grid(row=1, column=0, rowspan=4, sticky="nw",
                             padx=(0, 24))
        paste_appends_to_end(self.proxy_text,
                             lambda: self._update_proxy_count(force=True))
        self.proxy_text.bind("<<Modified>>", self._update_proxy_count)

        # Default to proxycheck.io - highest request rate (200/s per node) and
        # cheap/high-volume, so it's the primary screen; IPinfo is second. Fall
        # back to it if the saved provider no longer exists.
        _saved_prov = load_setting("quality_provider", "proxycheck.io")
        if _saved_prov not in QUALITY_PROVIDERS:
            _saved_prov = "proxycheck.io"
        self.provider = tk.StringVar(value=_saved_prov)
        ttk.Label(form, text="Reputation provider").grid(
            row=1, column=1, sticky="w")
        ttk.Combobox(form, textvariable=self.provider,
                     values=list(QUALITY_PROVIDERS.keys()), width=22,
                     state="readonly").grid(row=1, column=2, sticky="w", pady=3)
        self._prov_help = ttk.Label(
            form,
            text="'All providers (fused)' runs every keyed provider (IPinfo + "
                 "any others) concurrently and merges them - most pessimistic "
                 "signal wins. API keys live in Settings. Unique exit IPs are "
                 "scored once (deduped).",
            style="Muted.TLabel", justify="left")
        self._prov_help.grid(row=2, column=1, columnspan=2, sticky="w")
        # Reflow this help text to the window width instead of letting it run
        # off the right edge when the window is narrow.
        self.bind("<Configure>", lambda e: self._prov_help.config(
            wraplength=max(280, e.width - 40)), add="+")

        # Speed gate (two-stage funnel): filter on the NEUTRAL exit-IP-discovery
        # latency (proxy -> ipinfo.io/json, which we measure anyway) - so slow
        # proxies never reach the paid reputation API, and NO retailer is
        # contacted during scanning. The retailer test is your deliberate final
        # step on the vetted list (Proxy Tester tab), not the bulk scan.
        self.gate_on = tk.BooleanVar(value=False)
        gate_row = ttk.Frame(form)
        gate_row.grid(row=3, column=1, columnspan=2, sticky="w", pady=(10, 0))
        # Toggling the gate (or editing the ms) re-filters the ALREADY-scored
        # rows on-screen too - so you can apply a speed cut to a finished run
        # without re-scoring thousands of proxies.
        ttk.Checkbutton(
            gate_row, text="Speed gate: only score proxies that resolve under",
            variable=self.gate_on,
            command=self._render_rows).pack(side="left")
        self.gate_ms = tk.StringVar(value="1000")
        gate_entry = ttk.Entry(gate_row, textvariable=self.gate_ms, width=6)
        gate_entry.pack(side="left", padx=4)
        gate_entry.bind("<Return>", lambda e: self._render_rows())
        gate_entry.bind("<FocusOut>", lambda e: self._render_rows())
        ttk.Label(gate_row, text="ms (to ipinfo.io/json - no retailer "
                                 "contact)").pack(side="left")

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 4))
        self.run_btn = ttk.Button(btns, text="Score", style="Accent.TButton",
                                  command=self.on_run)
        self.run_btn.pack(side="left")
        ttk.Button(btns, text="Generate batch",
                   command=lambda: open_generate_dialog(
                       self, self.proxy_text)).pack(side="left", padx=8)
        # Exports the highlighted rows, or all currently-shown rows if none are.
        ttk.Button(btns, text="Export shown/selected",
                   command=self.on_export).pack(side="left", padx=(0, 8))
        # Collapse to one row (best Trust) per distinct exit IP.
        self._unique_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(btns, text="Unique exit IPs only",
                        variable=self._unique_only,
                        command=self._render_rows).pack(side="left", padx=(4, 0))
        # Default view is the healthy majority - only Trust >= this shows after
        # a run. Clear the box (or lower it) to reveal the poorer proxies;
        # nothing is discarded, this only changes what's displayed.
        ttk.Label(btns, text="Min trust").pack(side="left", padx=(10, 4))
        self.min_trust = tk.StringVar(value=str(DEFAULT_MIN_TRUST))
        min_trust_entry = ttk.Entry(btns, textvariable=self.min_trust, width=4)
        min_trust_entry.pack(side="left")
        min_trust_entry.bind("<Return>", lambda e: self._render_rows())
        min_trust_entry.bind("<FocusOut>", lambda e: self._render_rows())
        ttk.Label(btns, text="Filter Type / Trust from headers ▾",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))
        self.sel_lbl = ttk.Label(btns, text="", style="Muted.TLabel")
        self.sel_lbl.pack(side="right")

        # Run summary / progress on its own full-width row so it can never be
        # clipped off-screen; wraplength tracks the window so it reflows to fit.
        status_row = ttk.Frame(self)
        status_row.pack(fill="x", pady=(0, 2))
        self.status_lbl = ttk.Label(status_row, text="Idle", style="Muted.TLabel",
                                    anchor="w", justify="left")
        self.status_lbl.pack(fill="x", expand=True)
        status_row.bind(
            "<Configure>",
            lambda e: self.status_lbl.config(wraplength=max(200, e.width - 8)))

        # Pool-overlap banner: hidden entirely unless two providers in the list
        # actually returned the same exit IP. Silence = no overlap found.
        self._overlap = None
        self.overlap_row = ttk.Frame(self)
        self.overlap_lbl = ttk.Label(self.overlap_row, text="",
                                     style="Warn.TLabel", anchor="w",
                                     justify="left")
        self.overlap_lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(self.overlap_row, text="Details",
                   command=self._show_overlap).pack(side="right", padx=(8, 0))
        self.overlap_row.bind(
            "<Configure>",
            lambda e: self.overlap_lbl.config(wraplength=max(200, e.width - 90)))

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        layout = {
            "proxy":     (260, 150, True,  "w"),
            "exit_ip":   (150, 100, True,  "center"),
            "fraud":     (70,  50,  False, "center"),
            "type":      (130, 90,  True,  "center"),
            "flags":     (150, 90,  True,  "center"),
            "blacklist": (90,  70,  False, "center"),
            "ping":      (80,  60,  False, "center"),
            "trust":     (80,  60,  False, "center"),
        }
        # Type and Trust headers open multi-select filter dropdowns (▾); the
        # other headers sort on click.
        header_filters = {"type": self._open_type_filter,
                          "trust": self._open_trust_filter}
        for col in self.COLUMNS:
            w, mw, st, anc = layout[col]
            if col in header_filters:
                self.tree.heading(col, text=self.HEADINGS[col] + " ▾",
                                  command=header_filters[col])
            else:
                self.tree.heading(col, text=self.HEADINGS[col],
                                  command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, minwidth=mw, stretch=st, anchor=anc)
        tag_tree(self.tree)
        enable_drag_select(self.tree)
        self.tree.bind("<<TreeviewSelect>>", self._update_sel_count)
        self.tree.bind("<Control-c>", lambda e: (self.on_copy_selected(), "break"))
        self.tree.bind("<Control-C>", lambda e: (self.on_copy_selected(), "break"))
        self.tree.bind("<Control-a>", lambda e: (self._select_all_rows(), "break"))
        self.tree.bind("<Control-A>", lambda e: (self._select_all_rows(), "break"))
        attach_copy_menu(self.tree, self.on_copy_selected,
                         "Copy selected proxies")
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _update_proxy_count(self, _e=None, force=False):
        """Live count of non-empty proxy lines, shown in the box's header."""
        if not force and not self.proxy_text.edit_modified():
            return
        # '# Label' group headers are not proxies, so don't count them.
        n = sum(1 for ln in self.proxy_text.get("1.0", "end").splitlines()
                if ln.strip() and group_label_of(ln) is None)
        self.proxy_hdr.config(
            text=f"Proxies (host:port:user:pass, one per line; "
                 f"'# Label' groups a block) - {n} in list")
        self.proxy_text.edit_modified(False)

    # --- profile state (proxies only; the API key lives in settings.json) ---
    def get_state(self):
        return {"proxies": self.proxy_text.get("1.0", "end").rstrip("\n")}

    def set_state(self, d):
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", d.get("proxies", ""))

    def on_run(self):
        if self.running:
            return
        provider = self.provider.get()
        save_setting("quality_provider", provider)
        key_setting = QUALITY_PROVIDERS.get(provider, ("", None))[0]
        api_key = load_setting(key_setting, "").strip() if key_setting else ""
        # '# Label' lines group the proxies beneath them, so two SKUs from the
        # same reseller host can still be told apart for overlap detection.
        proxies, self._labels, bad = parse_labeled_proxies(
            self.proxy_text.get("1.0", "end"))
        if not proxies:
            messagebox.showerror("ProxyTester", "Enter at least one valid proxy.")
            return

        gate_ms = None
        if self.gate_on.get():
            try:
                gate_ms = max(1, int(self.gate_ms.get().strip()))
            except (TypeError, ValueError):
                gate_ms = 1000

        self.tree.delete(*self.tree.get_children())
        self._rows = []
        self.running = True
        self.stop_event.clear()
        self._run_started = time.perf_counter()
        self._run_total = len(proxies)
        self.run_btn.config(text="Stop", style="Stop.TButton",
                            command=self.on_stop)
        # The aggregate lists whichever keyed providers are active; a single
        # keyed provider falls back to Spamhaus-only if its key is unset.
        if provider == AGGREGATE_PROVIDER:
            active = [n for n, _, _ in _configured_lookups()]
            engine = ("fused: " + ", ".join(active) if active
                      else "Spamhaus only (add a key in Settings)")
        else:
            engine = (provider if (api_key or not key_setting)
                      else "no key (Spamhaus + latency)")
        self.status_lbl.config(
            text=f"Resolving exit IPs for {len(proxies)} proxy(ies) "
                 f"[{engine}]...")
        worker = threading.Thread(
            target=self._run_pool,
            args=(proxies, provider, api_key, gate_ms), daemon=True)
        worker.start()
        self.after(100, self._drain_queue)

    def on_stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.run_btn.config(state="disabled")
        self.status_lbl.config(text="Stopping...")

    def _slow_row(self, d, gate_ms):
        """A row for a proxy that resolved but was too slow for the speed gate -
        shown, but never sent to the paid API. Uses its neutral resolve latency."""
        ms = d.get("ping")
        status = (f"slow {ms:.0f}ms > {gate_ms}ms" if ms is not None else "slow")
        return {"proxy": d["proxy"], "full": d.get("full", d["proxy"]),
                "exit_ip": d.get("exit_ip", ""), "fraud": "", "type": "",
                # Say WHY the score columns are empty - a blank row otherwise
                # looks like a proxy that scored nothing, not one never asked
                # about.
                "flags": "not scored (speed gate)",
                "blacklist": "-", "ping": ms, "trust": None,
                "status": status}

    def _run_pool(self, proxies, provider, api_key, gate_ms=None):
        """Two-stage funnel. Stage 1: resolve each proxy's exit IP (this hits
        the NEUTRAL ipinfo.io/json, never a retailer, and gives a free latency).
        Speed gate (optional): a proxy that resolved slower than the threshold is
        shown but NOT scored. Stage 2: score each UNIQUE surviving exit IP once
        (dedupe). The retailer test is a separate deliberate final step."""
        workers = get_workers()
        resolved = unique_n = gated_out = 0
        provider_err, err_ct = "", 0
        prov_status = []
        overlap = None
        try:
            # --- Stage 1a: connect-only pre-filter (cheap, very wide) ---
            # A dead proxy costs the FULL do_request timeout (TLS+GET+body) if
            # it goes straight into stage 1b, held by one of only `workers`
            # (500) full-path slots. A CONNECT-only probe answers "is this
            # proxy even reachable" in one RTT at ~1,200-wide concurrency and a
            # short timeout, so the dead majority of a huge list never touches
            # the expensive path at all. Same target host as stage 1b's GET
            # (ipinfo.io:443), so a pass here means the real request can follow.
            discoveries = []
            alive = []
            thost, tport = LIVENESS_TARGET
            with ThreadPoolExecutor(max_workers=get_fast_workers()) as pool:
                futs = {pool.submit(proxy_connect_ping, p, thost, tport,
                                    get_fast_timeout()): p for p in proxies}
                done = 0
                for fut, p in futs.items():
                    display = (f"{p['host']}:{p['port']}:{p['user']}:****"
                              if p.get("user") and p.get("pw") is not None
                              else f"{p['host']}:{p['port']}")
                    full = (f"{p['host']}:{p['port']}:{p['user']}:{p['pw']}"
                           if p.get("user") and p.get("pw") is not None
                           else display)
                    try:
                        ms, code, err = fut.result()
                    except Exception as e:
                        ms, code, err = None, None, str(e)[:60]
                    if code == 200:
                        alive.append(p)
                    else:
                        discoveries.append({
                            "proxy": display, "full": full, "exit_ip": "",
                            "ping": None, "status": _fast_status(code, err)})
                    done += 1
                    if done % 200 == 0:
                        self.queue.put({"_status":
                                        f"Pre-filtering {done}/{len(proxies)} "
                                        f"({len(alive)} reachable so far)..."})
            self.queue.put({"_status":
                            f"Pre-filter kept {len(alive)}/{len(proxies)} "
                            "reachable proxies - resolving exit IPs..."})

            # --- Stage 1b: resolve exit IPs on the SURVIVORS only ---
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(discover_exit_ip, p, DEFAULT_TIMEOUT,
                                    self.stop_event): p for p in alive}
                done = 0
                for fut in futs:
                    try:
                        d = fut.result()
                    except Exception as e:
                        p = futs[fut]
                        d = {"proxy": f"{p['host']}:{p['port']}", "exit_ip": "",
                             "ping": None, "status": str(e)[:60],
                             "full": f"{p['host']}:{p['port']}"}
                    discoveries.append(d)
                    done += 1
                    if done % 25 == 0:
                        self.queue.put({"_status":
                                        f"Resolved {done}/{len(alive)} "
                                        "exit IPs..."})

            # --- Speed gate: mark OK-but-slow proxies (kept out of scoring) ---
            if gate_ms is not None:
                for d in discoveries:
                    d["_slow"] = (d.get("status") == "OK"
                                  and (d.get("ping") is None
                                       or d["ping"] > gate_ms))
                gated_out = sum(1 for d in discoveries if d.get("_slow"))

            unique = sorted({d["exit_ip"] for d in discoveries
                             if d["exit_ip"] and not d.get("_slow")})
            unique_n = len(unique)
            resolved = sum(1 for d in discoveries if d["exit_ip"])
            gate_note = (f"; {gated_out} slow-skipped" if gated_out else "")
            self.queue.put({"_status": f"Scoring {unique_n} unique IP(s) from "
                                       f"{resolved} live proxies "
                                       f"({resolved - unique_n} deduped)"
                                       f"{gate_note}..."})
            breaker = (_ProviderBreaker()
                       if provider == AGGREGATE_PROVIDER else None)
            scores = {}
            # IPinfo has a bulk endpoint (up to 1000 IPs per POST, run several
            # chunks concurrently) - a whole run resolves in a handful of
            # requests instead of one direct connection per IP, which is what
            # exhausted local sockets on big runs. This now applies whenever
            # IPinfo has a key and batch isn't disabled in Settings - INCLUDING
            # fused mode, which previously called IPinfo per-IP inside the same
            # pool as every other provider and never batched at all.
            ipinfo_key = load_setting("ipinfo_token", "").strip()
            use_batch = (bool(ipinfo_key)
                         and load_setting("ipinfo_batch", True)
                         and not self.stop_event.is_set())
            ipinfo_precomputed = {}
            if use_batch and provider in ("IPinfo", AGGREGATE_PROVIDER):
                self.queue.put({"_status": f"Batch-resolving IPinfo for "
                                f"{unique_n} unique IP(s)..."})
                ipinfo_precomputed = ipinfo_batch_all(unique, ipinfo_key,
                                                      DEFAULT_TIMEOUT)
            if provider == "IPinfo" and use_batch:
                scores = dict(ipinfo_precomputed)
            elif not self.stop_event.is_set():
                # Stage 2's general pool: spamhaus + whatever providers aren't
                # already resolved via batch. Concurrency is generous here
                # because proxycheck.io self-paces to its own documented
                # per-second limit via _proxycheck_limiter, and IPinfo (the
                # provider that used to need protecting) is pre-fetched above.
                score_workers = min(get_score_workers(), max(1, unique_n))
                with ThreadPoolExecutor(max_workers=score_workers) as pool:
                    if provider == AGGREGATE_PROVIDER:
                        futs = {pool.submit(
                            score_ip, ip, provider, api_key, DEFAULT_TIMEOUT,
                            breaker,
                            ({"IPinfo": ipinfo_precomputed[ip]}
                             if ip in ipinfo_precomputed else None)): ip
                            for ip in unique}
                    else:
                        futs = {pool.submit(score_ip, ip, provider, api_key,
                                            DEFAULT_TIMEOUT, breaker): ip
                                for ip in unique}
                    done = 0
                    for fut in futs:
                        ip = futs[fut]
                        try:
                            scores[ip] = fut.result()
                        except Exception:
                            scores[ip] = {"blacklisted": None}
                        done += 1
                        if done % 50 == 0:
                            self.queue.put({"_status": f"Scored {done}/"
                                            f"{unique_n} unique IP(s)..."})

            for q in scores.values():
                if q.get("_error"):
                    err_ct += 1
                    provider_err = q["_error"]
            # Per-provider status for the aggregate: which ran ok, which the
            # breaker stopped, and which were skipped for a missing key.
            prov_status = breaker.summary() if breaker else []
            if provider == AGGREGATE_PROVIDER:
                for name, (ks, lk) in QUALITY_PROVIDERS.items():
                    if lk is None or not ks:
                        continue
                    if not load_setting(ks, "").strip():
                        prov_status.append(f"{name}: skipped (no key)")
            # Same-pool detection: costs nothing (we already have every exit
            # IP), and only ever surfaces when two providers collide.
            overlap = compute_pool_overlap(discoveries,
                                           getattr(self, "_labels", None))
            shared_map = overlap["shared"]
            has_key = bool(api_key) or provider == AGGREGATE_PROVIDER
            for d in discoveries:
                if d.get("_slow"):
                    row = self._slow_row(d, gate_ms)
                else:
                    row = build_quality_row(
                        d, scores.get(d["exit_ip"], {}), has_key)
                sh = shared_map.get(d.get("exit_ip") or "")
                if sh:
                    # Flag the row itself so a shared IP is visible in the
                    # table, not just in the summary.
                    row["shared"] = sh
                    row["flags"] = (f"{len(sh)} pools "
                                    + (row.get("flags") or "")).strip()
                self.queue.put(row)
        finally:
            self.queue.put({"_done": True, "resolved": resolved,
                            "unique": unique_n, "provider_err": provider_err,
                            "err_ct": err_ct, "gated_out": gated_out,
                            "prov_status": prov_status, "overlap": overlap})

    def _drain_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item.get("_status"):
                    self.status_lbl.config(text=item["_status"])
                    continue
                if item.get("_done"):
                    self._finish(item)
                    return
                self._rows.append(item)
        except queue.Empty:
            pass
        if self.running:
            self.after(100, self._drain_queue)

    def _finish(self, info=None):
        info = info or {}
        stopped = self.stop_event.is_set()
        self.running = False
        self.run_btn.config(text="Score", style="Accent.TButton",
                            command=self.on_run, state="normal")

        # Best-first: highest Trust, then lowest fraud; failures sink to bottom.
        def sort_key(r):
            t = r.get("trust")
            f = r.get("fraud")
            ok = r.get("status") == "OK"
            return (0 if ok else 1,
                    -(t if isinstance(t, int) else -1),
                    int(f) if f not in ("", None) else 999)

        self._rows.sort(key=sort_key)
        scored = sum(1 for r in self._rows if r.get("status") == "OK")
        dedup = ""
        if "resolved" in info:
            deduped = info["resolved"] - info.get("unique", info["resolved"])
            dedup = (f", {info.get('unique', 0)} unique exit IPs "
                     f"({deduped} deduped)")
        gate_note = ""
        if info.get("gated_out"):
            gate_note = f", {info['gated_out']} slow-filtered (no paid lookup)"
        # Loud provider-error banner: if the reputation API rejected every
        # lookup (bad/expired key, rate limit), say so instead of leaving a
        # silent wall of Trust 50.
        err_note = ""
        if info.get("err_ct") and info.get("provider_err"):
            hint = ""
            if "401" in info["provider_err"] or "403" in info["provider_err"]:
                hint = " - check the key/token in Settings"
            elif "429" in info["provider_err"]:
                hint = " - rate limited, slow down or wait"
            err_note = (f"  |  {info['provider_err']} on {info['err_ct']} "
                        f"IP(s){hint}")
        # Per-provider status for the fused run (ok / stopped / skipped-no-key).
        prov_note = ""
        if info.get("prov_status"):
            prov_note = "  |  providers - " + "; ".join(info["prov_status"])
        elapsed_s = (time.perf_counter()
                    - getattr(self, "_run_started", time.perf_counter()))
        elapsed = _fmt_elapsed(elapsed_s)
        total = getattr(self, "_run_total", 0)
        rate = f", {total / max(elapsed_s, 0.001):.0f}/s" if total else ""
        # Persistent summary so filtering never wipes the scored/dedupe counts.
        self._summary = ("Stopped" if stopped
                         else f"Done in {elapsed}{rate} - {scored} scored"
                              f"{dedup}{gate_note}{err_note}{prov_note}")
        # Same-pool warning: shown ONLY when two providers actually collided.
        self._overlap = info.get("overlap")
        note = overlap_summary(self._overlap or {})
        if note:
            self.overlap_lbl.config(text=note)
            self.overlap_row.pack(fill="x", pady=(2, 4), before=self.tree)
        else:
            self.overlap_row.pack_forget()
        self._trust_buckets = set()       # a fresh run clears prior filters
        self._type_filter = set()
        self._render_rows()

    def _show_overlap(self):
        """Full breakdown of which providers are handing back the same IPs."""
        ov = self._overlap or {}
        shared = ov.get("shared") or {}
        if not shared:
            messagebox.showinfo("Pool overlap", "No shared exit IPs found.")
            return
        per = ov.get("per_provider", {})
        uniq = ov.get("unique_ips", 0)
        lines = [
            f"{len(shared)} of {uniq} unique exit IPs came back from more than "
            f"one provider.",
            "",
            "An IP that two providers both serve is ONE IP you are renting "
            "twice - so it also gets used (and burned) twice as fast.",
            "",
            "Unique exit IPs seen per provider:",
        ]
        for p in sorted(per, key=lambda k: -per[k]):
            lines.append(f"   {p}: {per[p]}")
        lines += ["", "Shared between:"]
        for (a, b), n in sorted(ov.get("pairs", {}).items(),
                                key=lambda kv: -kv[1]):
            # Percentage is of the SMALLER pool - that's the one being diluted.
            base = min(per.get(a, 0), per.get(b, 0)) or 1
            lines.append(f"   {a} + {b}: {n} IPs "
                         f"({100.0 * n / base:.1f}% of the smaller pool)")
        lines += ["", f"Shared exit IPs ({len(shared)}):"]
        for ip in sorted(shared):
            lines.append(f"   {ip}   <- {', '.join(shared[ip])}")
        text = "\n".join(lines)

        top = tk.Toplevel(self)
        top.title("Pool overlap - providers sharing exit IPs")
        top.configure(bg=BASE)
        center_over_parent(top, self, 720, 520)
        box = tk.Text(top, wrap="none", height=24)
        style_text(box)
        box.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        box.insert("1.0", text)
        box.config(state="disabled")
        bar = ttk.Frame(top)
        bar.pack(fill="x", padx=12, pady=(0, 12))

        def copy_ips():
            self.clipboard_clear()
            self.clipboard_append("\n".join(sorted(shared)))
            messagebox.showinfo("Pool overlap",
                                f"Copied {len(shared)} shared exit IP(s).",
                                parent=top)

        ttk.Button(bar, text="Copy shared IPs",
                   command=copy_ips).pack(side="left")
        ttk.Button(bar, text="Close", command=top.destroy).pack(side="right")

    def _trust_tag(self, r):
        # No Trust does NOT mean bad. A proxy that resolved fine but fell
        # outside the speed gate was never sent to the reputation API at all -
        # colouring it red reads as "dirty IP" when it actually means "not
        # measured". Those are greyed; only a proxy that failed to resolve
        # (no exit IP) is red.
        if r.get("trust") is None:
            return "bad" if not r.get("exit_ip") else "muted"
        if r.get("status") != "OK":
            return "bad"
        t = r["trust"]
        # Any Spamhaus listing (XBL/SBL/PBL) is never shown green - a flagged IP
        # caps at a caution colour even if its number is otherwise high.
        listed = r.get("blacklist") not in (None, "", "clean", "-")
        if listed:
            return "warn" if t >= 50 else "bad"
        if t >= 75:
            return "ok"
        return "warn" if t >= 50 else "bad"

    def _insert_row(self, r):
        item = self.tree.insert("", "end", values=(
            r["proxy"], r["exit_ip"] or r.get("status", ""), r["fraud"],
            r["type"], r["flags"], r["blacklist"], _fmt_ms(r["ping"]),
            "" if r["trust"] is None else r["trust"],
        ), tags=(self._trust_tag(r),))
        self._item_full[item] = r.get("full", "")

    def _update_sel_count(self, _event=None):
        n = len(self.tree.selection())
        self.sel_lbl.config(text=f"{n} selected" if n else "")

    def _render_rows(self):
        """Re-render applying the active Trust-range + Type filters. Rows are
        inserted in chunks (yielding to the GUI between batches) so a large
        result set - thousands of rows - never freezes the window; the status
        shows live paint progress and only flips to the final summary once every
        row is actually on screen."""
        rows = getattr(self, "_rows", [])
        # Min-trust floor: the default view after a run. Blank the box (or
        # lower it) to reveal poorer proxies - nothing is discarded, only the
        # display changes, same as every other filter here.
        min_trust = None
        raw_mt = (self.min_trust.get() or "").strip()
        if raw_mt:
            try:
                min_trust = max(0, min(100, int(raw_mt)))
            except (TypeError, ValueError):
                min_trust = None
            if min_trust is not None:
                rows = [r for r in rows
                        if isinstance(r.get("trust"), int)
                        and r["trust"] >= min_trust]
        if self._trust_buckets:
            preds = [p for (lbl, p) in TRUST_BUCKETS
                     if lbl in self._trust_buckets]
            rows = [r for r in rows if any(p(r.get("trust")) for p in preds)]
        if self._type_filter:
            rows = [r for r in rows if r.get("type") in self._type_filter]
        # Speed gate also acts as a post-run display filter: hide rows whose
        # resolve latency is over the threshold, using the ping we already have
        # - so you can filter a finished list without re-scanning.
        gate_ms = None
        if self.gate_on.get():
            try:
                gate_ms = max(1, int(self.gate_ms.get().strip()))
            except (TypeError, ValueError):
                gate_ms = 1000
            rows = [r for r in rows
                    if isinstance(r.get("ping"), (int, float))
                    and r["ping"] <= gate_ms]
        unique_only = self._unique_only.get()
        if unique_only:
            # Rows arrive best-Trust-first, so first seen per exit IP is the
            # best proxy for that IP. Rows without an exit IP (failures) drop.
            seen, collapsed = set(), []
            for r in rows:
                ip = r.get("exit_ip")
                if not ip or ip in seen:
                    continue
                seen.add(ip)
                collapsed.append(r)
            rows = collapsed

        filt = []
        if unique_only:
            filt.append("unique IPs")
        if min_trust is not None:
            filt.append(f"trust≥{min_trust}")
        if gate_ms is not None:
            filt.append(f"≤{gate_ms}ms")
        if self._trust_buckets:
            filt.append("trust=" + "/".join(
                lbl for (lbl, _) in TRUST_BUCKETS if lbl in self._trust_buckets))
        if self._type_filter:
            filt.append("type=" + "/".join(sorted(self._type_filter)))
        self._final_status = self._summary or f"Showing {len(rows)}"
        if filt:
            self._final_status += f"  |  showing {len(rows)} [{', '.join(filt)}]"

        # Cancel any in-flight paint (e.g. a filter toggled mid-render).
        if getattr(self, "_render_job", None):
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
            self._render_job = None
        self.tree.delete(*self.tree.get_children())
        self._item_full = {}
        self._pending_rows = rows
        self._render_chunk(0)

    def _render_chunk(self, start):
        rows = self._pending_rows
        end = min(start + 500, len(rows))
        for r in rows[start:end]:
            self._insert_row(r)
        if end < len(rows):
            self.status_lbl.config(text=f"Rendering {end}/{len(rows)} rows...")
            self._render_job = self.after(1, lambda: self._render_chunk(end))
        else:
            self._render_job = None
            self.status_lbl.config(text=self._final_status)
            self._update_sel_count()

    def _open_checkbox_filter(self, title, options, current, on_apply):
        """Shared multi-select dropdown for the Type and Trust headers. `options`
        is a list of labels; `on_apply` receives the selected set (an empty set
        means no filter / show all)."""
        if not options:
            self.status_lbl.config(text="No results to filter yet - Score first.")
            return
        top = tk.Toplevel(self)
        top.title(title)
        top.configure(bg=BASE)
        top.transient(self.winfo_toplevel())
        top.resizable(False, False)
        cbvars = {}
        ttk.Label(top, text=title + ":", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        for i, opt in enumerate(options):
            v = tk.BooleanVar(value=(opt in current) if current else True)
            cbvars[opt] = v
            ttk.Checkbutton(top, text=opt, variable=v).grid(
                row=i + 1, column=0, sticky="w", padx=18, pady=1)
        btns = ttk.Frame(top)
        btns.grid(row=len(options) + 1, column=0, sticky="ew", padx=12,
                  pady=(10, 12))

        def apply_():
            sel = {o for o, v in cbvars.items() if v.get()}
            on_apply(set() if not sel or len(sel) == len(options) else sel)
            top.destroy()

        ttk.Button(btns, text="Apply", style="Accent.TButton",
                   command=apply_).pack(side="left")
        ttk.Button(btns, text="All",
                   command=lambda: [v.set(True) for v in cbvars.values()]).pack(
            side="left", padx=6)
        ttk.Button(btns, text="None",
                   command=lambda: [v.set(False) for v in cbvars.values()]).pack(
            side="left")
        try:
            top.geometry(f"+{self.tree.winfo_rootx() + 300}"
                         f"+{self.tree.winfo_rooty()}")
        except Exception:
            pass
        top.grab_set()

    def _open_type_filter(self):
        types = sorted({r.get("type", "") for r in self._rows
                        if r.get("status") == "OK" and r.get("type")})

        def apply(sel):
            self._type_filter = sel
            self._render_rows()

        self._open_checkbox_filter("Filter by Type", types, self._type_filter,
                                   apply)

    def _open_trust_filter(self):
        # Only offer trust ranges that actually have matching rows.
        labels = [lbl for (lbl, p) in TRUST_BUCKETS
                  if any(p(r.get("trust")) for r in self._rows)]

        def apply(sel):
            self._trust_buckets = sel
            self._render_rows()

        self._open_checkbox_filter("Filter by Trust range", labels,
                                   self._trust_buckets, apply)

    def _sort_by(self, col):
        """Sort the visible rows by a column (numeric when possible),
        toggling direction each click. Click 'Trust' to rank by trust."""
        items = [(self.tree.set(i, col), i) for i in self.tree.get_children("")]

        def key(pair):
            v = pair[0]
            try:
                return (0, float(v))
            except ValueError:
                return (1, v.lower())

        rev = self._sort_dir.get(col, False)
        items.sort(key=key, reverse=rev)
        self._sort_dir[col] = not rev
        for idx, (_, i) in enumerate(items):
            self.tree.move(i, "", idx)

    def _select_all_rows(self):
        """Ctrl+A: select every currently-shown row in the results tree."""
        rows = self.tree.get_children()
        if rows:
            self.tree.selection_set(rows)

    def on_copy_selected(self):
        """Copy the highlighted proxies (full host:port:user:pass) to clipboard."""
        lines = [self._item_full.get(i, "") for i in self.tree.selection()]
        lines = [ln for ln in lines if ln]
        if not lines:
            self.status_lbl.config(text="No rows selected to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.update_idletasks()
        self.status_lbl.config(
            text=f"Copied {len(lines)} proxy(ies) to clipboard.")

    def on_export(self):
        # Export the highlighted rows; if nothing is highlighted, export every
        # currently-shown (filtered) row.
        sel = self.tree.selection()
        export_tree_csv(self.tree, self.COLUMNS,
                        [self.HEADINGS[c] for c in self.COLUMNS],
                        full_map=self._item_full, full_col=0,
                        items=sel if sel else None)


class SettingsTab(ttk.Frame):
    """Central place for API keys and performance. Keys are stored in
    settings.json in your config dir (never hard-coded)."""

    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self._on_saved = on_saved
        # The Settings content is taller than the window, so host it in a
        # scrollable canvas - otherwise the Save button falls off the bottom.
        self._canvas = tk.Canvas(self, highlightthickness=0, bg=BASE,
                                 borderwidth=0)
        vsb = ttk.Scrollbar(self, orient="vertical",
                            command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self._canvas, padding=20)
        self._win = self._canvas.create_window((0, 0), window=self.inner,
                                               anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        # Stretch the inner frame to the viewport AND reflow the help
        # paragraphs to that width, so long text wraps instead of running off
        # the right edge of the window.
        self._wrap_labels = []
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # Mousewheel only while the pointer is over this tab.
        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all(
            "<MouseWheel>", self._on_wheel))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all(
            "<MouseWheel>"))
        self._build()

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_canvas_configure(self, e):
        self._canvas.itemconfigure(self._win, width=e.width)
        # inner frame has padding=20 each side; leave a little slack so text
        # never touches the scrollbar.
        wl = max(200, e.width - 56)
        for lbl in self._wrap_labels:
            lbl.configure(wraplength=wl)

    def _help(self, text, r, pady=(0, 0)):
        """A muted help paragraph that reflows to the window width."""
        lbl = ttk.Label(self.inner, text=text, style="Muted.TLabel",
                        justify="left")
        lbl.grid(row=r, column=0, columnspan=2, sticky="w", pady=pady)
        self._wrap_labels.append(lbl)
        return lbl

    def _build(self):
        host = self.inner
        r = 0
        self._help("Changes save automatically as you type - no need to "
                   "click anything.", r, pady=(0, 14))
        r += 1
        ttk.Label(host, text="IP reputation API keys",
                  style="Header.TLabel").grid(row=r, column=0, columnspan=2,
                                              sticky="w", pady=(0, 4))
        r += 1
        self._help("Used by the IP Quality tab. Only the public exit IP is "
                   "ever sent to these - never your proxy credentials.",
                   r, pady=(0, 12))
        r += 1

        self.ipqs = tk.StringVar(value=load_setting("ipqs_api_key", ""))
        self.pcheck = tk.StringVar(value=load_setting("proxycheck_api_key", ""))
        self.ipinfo = tk.StringVar(value=load_setting("ipinfo_token", ""))

        def key_row(label, var):
            nonlocal r
            ttk.Label(host, text=label).grid(row=r, column=0, sticky="w", pady=4)
            e = ttk.Entry(host, textvariable=var, width=46, show="•")
            e.grid(row=r, column=1, sticky="w", pady=4, padx=(10, 0))
            reveal_on_focus(e)
            e.bind("<FocusOut>", lambda _e: self._persist(), add="+")
            r += 1

        key_row("proxycheck.io key", self.pcheck)
        key_row("IPinfo token (Max = residential proxy)", self.ipinfo)
        key_row("IPQualityScore key", self.ipqs)

        # IPinfo bulk endpoint: one POST per 1000 IPs instead of one connection
        # per IP - the fix for socket exhaustion on big runs. On by default.
        self.ipinfo_batch = tk.BooleanVar(
            value=bool(load_setting("ipinfo_batch", True)))
        ttk.Checkbutton(
            host, text="Use IPinfo batch API (1000 IPs/request)",
            variable=self.ipinfo_batch,
            command=lambda: (save_setting("ipinfo_batch",
                                          bool(self.ipinfo_batch.get())),
                             self.status_lbl.config(text="Saved."))
            ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 0))
        r += 1
        self._help("Scores the IP Quality tab far faster on large lists and "
                   "avoids the connection failures single-lookup mode hit on "
                   "10k+ runs. Applies to the 'IPinfo' provider; turn off only "
                   "if batch results look wrong.", r, pady=(0, 4))
        r += 1

        ttk.Separator(host, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=14)
        r += 1
        ttk.Label(host, text="Proxy provider credentials",
                  style="Header.TLabel").grid(row=r, column=0, columnspan=2,
                                              sticky="w", pady=(0, 4))
        r += 1
        self._help("One box per provider, as username:password. Oxylabs "
                   "Mobile fills the ASN Tester login; the residential "
                   "providers feed 'Generate batch'.", r, pady=(0, 8))
        r += 1
        self.oxy_mobile = tk.StringVar(
            value=provider_creds_display("oxylabs_mobile"))
        self.oxy_resi = tk.StringVar(value=provider_creds_display(
            "oxylabs_resi", ("oxylabs_resi_user", "oxylabs_resi_pass")))
        self.ipr = tk.StringVar(value=provider_creds_display(
            "iproyal", ("iproyal_user", "iproyal_pass")))
        self.brightdata = tk.StringVar(value=provider_creds_display("brightdata"))
        self.proxyhaus = tk.StringVar(value=provider_creds_display("proxyhaus"))
        self.rayobyte = tk.StringVar(value=provider_creds_display("rayobyte"))
        self.packetstream = tk.StringVar(
            value=provider_creds_display("packetstream"))
        self.hellworld = tk.StringVar(value=provider_creds_display("hellworld"))
        self.thuproxy = tk.StringVar(value=provider_creds_display("thuproxy"))

        # Per-provider show/hide for the batch generator. Unchecking hides the
        # provider from Generate batch WITHOUT touching its saved credentials,
        # so turning it back on needs no re-typing.
        self.show_vars = {}

        def cred_row(label, var, gen_key=None):
            nonlocal r
            ttk.Label(host, text=label).grid(row=r, column=0, sticky="w", pady=3)
            # Entry + inline warning packed together in one cell so the warning
            # sits right next to the box (a separate grid column drifts to the
            # far edge when the column stretches).
            box = ttk.Frame(host)
            box.grid(row=r, column=1, sticky="w", pady=3, padx=(10, 0))
            e = ttk.Entry(box, textvariable=var, width=46)
            e.pack(side="left")
            e.bind("<FocusOut>", lambda _e: self._persist(), add="+")
            if gen_key:
                sv = tk.BooleanVar(value=gen_key not in hidden_resi_providers())
                self.show_vars[gen_key] = sv

                def _toggle(k=gen_key, v=sv):
                    set_resi_provider_hidden(k, not v.get())
                    self.status_lbl.config(
                        text=("Shown in Generate batch" if v.get()
                              else "Hidden from Generate batch "
                                   "(credentials kept)"))
                    if self._on_saved:
                        self._on_saved()

                ttk.Checkbutton(box, text="in generator", variable=sv,
                                command=_toggle).pack(side="left", padx=(10, 0))
            # Inline validation for the username:password format - flag a missing
            # colon or a space in the username right here, where creds are typed,
            # rather than at generate time.
            warn = ttk.Label(box, text="", style="Warn.TLabel")
            warn.pack(side="left", padx=(10, 0))
            var.trace_add("write",
                          lambda *_: warn.config(text=_cred_warning(var.get())))
            warn.config(text=_cred_warning(var.get()))
            r += 1

        # Oxylabs Mobile feeds the ASN Tester, not the batch generator, so it
        # has no 'in generator' toggle.
        cred_row("Oxylabs Mobile (username:password)", self.oxy_mobile)
        cred_row("Oxylabs Residential (username:password)", self.oxy_resi,
                 "oxylabs_resi")
        cred_row("IPRoyal (username:password)", self.ipr, "iproyal")
        cred_row("Bright Data (username:password)", self.brightdata,
                 "brightdata")
        cred_row("Proxy-Haus (username:password)", self.proxyhaus, "proxyhaus")
        cred_row("Rayobyte (username:password)", self.rayobyte, "rayobyte")
        cred_row("PacketStream (username:password)", self.packetstream,
                 "packetstream")
        cred_row("Hell World F-Private (username:password)", self.hellworld,
                 "hellworld")
        cred_row("ThuProxy (username:password)", self.thuproxy, "thuproxy")

        ttk.Separator(host, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=14)
        r += 1
        ttk.Label(host, text="Performance", style="Header.TLabel").grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
        r += 1
        self._help("Concurrency and timeouts are tuned for maximum throughput "
                   "and hard-coded - the liveness sweep runs up to ~1,200 "
                   "connections at once, the full/exit-IP path 500, and "
                   "reputation lookups 400 (IPinfo batches separately at "
                   "1,000/request; proxycheck.io self-paces to its own "
                   "documented per-second limit). Nothing to adjust.", r)
        r += 1

        # Auto-save: any edit persists after a short debounce, so a forgotten
        # click on 'Save settings' can never silently drop a key again.
        for _v in (self.ipqs, self.pcheck, self.ipinfo, self.oxy_mobile,
                   self.oxy_resi, self.ipr, self.brightdata, self.proxyhaus,
                   self.rayobyte, self.packetstream, self.hellworld,
                   self.thuproxy):
            _v.trace_add("write", self._schedule_autosave)

        # Settings auto-save (debounced on every edit), so there's no Save
        # button - this label just confirms the last write.
        self.status_lbl = ttk.Label(host, text="Settings save automatically",
                                     style="Muted.TLabel")
        self.status_lbl.grid(row=r, column=0, columnspan=2, sticky="w",
                             pady=(16, 4))

    def _schedule_autosave(self, *_):
        """Debounce rapid edits into a single write ~0.6s after typing stops."""
        job = getattr(self, "_save_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._save_job = self.after(600, self._persist)

    def _persist(self, announce=True):
        """Write every setting to disk. Called on auto-save and manual save."""
        save_setting("ipqs_api_key", self.ipqs.get().strip())
        save_setting("proxycheck_api_key", self.pcheck.get().strip())
        save_setting("ipinfo_token", self.ipinfo.get().strip())
        save_setting("oxylabs_mobile", self.oxy_mobile.get().strip())
        save_setting("oxylabs_resi", self.oxy_resi.get().strip())
        save_setting("iproyal", self.ipr.get().strip())
        save_setting("brightdata", self.brightdata.get().strip())
        save_setting("proxyhaus", self.proxyhaus.get().strip())
        save_setting("rayobyte", self.rayobyte.get().strip())
        save_setting("packetstream", self.packetstream.get().strip())
        save_setting("hellworld", self.hellworld.get().strip())
        save_setting("thuproxy", self.thuproxy.get().strip())
        if announce:
            self.status_lbl.config(text="Saved.")
        if self._on_saved:
            self._on_saved()

    def on_save(self):
        self._persist(announce=True)


class HeaderBar(ttk.Frame):
    """Top bar: branding + the settings gear (Check for updates)."""

    def __init__(self, master):
        super().__init__(master, padding=(14, 12, 14, 4))
        if LOGO_HEADER_B64:
            try:
                self._logo_img = tk.PhotoImage(data=LOGO_HEADER_B64)
                ttk.Label(self, image=self._logo_img).pack(side="left")
                ttk.Label(self, text=" ProxyTester", style="Header.TLabel").pack(
                    side="left")
            except Exception:
                ttk.Label(self, text="◆ ProxyTester",
                          style="Header.TLabel").pack(side="left")
        else:
            ttk.Label(self, text="◆ ProxyTester", style="Header.TLabel").pack(
                side="left")
        ttk.Label(self, text="made by codyrandolph",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0),
                                             anchor="s", pady=(0, 4))

        self._settings_menu = tk.Menu(self, tearoff=0, bg=SURFACE, fg=TEXT,
                                      activebackground=MAUVE, activeforeground=BASE,
                                      bd=0, relief="flat")
        self._settings_menu.add_command(label="Check for updates",
                                        command=lambda: check_for_updates(self))
        self._settings_menu.add_separator()
        self._settings_menu.add_command(
            label=f"ProxyTester v{APP_VERSION}", state="disabled")
        self._settings_btn = ttk.Button(self, text="⚙", width=3,
                                        style="Gear.TButton",
                                        command=self._open_settings)
        self._settings_btn.pack(side="right", padx=(8, 0))

    def _open_settings(self):
        btn = self._settings_btn
        self._settings_menu.tk_popup(btn.winfo_rootx(),
                                     btn.winfo_rooty() + btn.winfo_height())


# --------------------------------------------------------------------------- #
# Self-update (pulls the latest release from the public GitHub repo)
# --------------------------------------------------------------------------- #
def _version_tuple(v):
    nums = []
    for part in str(v).lstrip("vV").split("."):
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    return tuple(nums)


def _release_asset_url(rel):
    """Download URL of a release's app asset: prefer the onedir .zip (no runtime
    unpacking); fall back to a legacy .exe. None if the release has neither."""
    assets = rel.get("assets", [])
    asset = next((a for a in assets
                  if a.get("name", "").lower().endswith(".zip")), None)
    if asset is None:
        asset = next((a for a in assets
                      if a.get("name", "").lower().endswith(".exe")), None)
    return (asset or {}).get("browser_download_url")


def _fetch_latest_release():
    """Return (tag, download_url) for the HIGHEST-VERSION release. We scan the
    full release list and pick the max version number - NOT GitHub's
    /releases/latest, which is ordered by publish time and can point at an older
    tag if a release was re-published. This guarantees one update hops straight
    to the newest version instead of one version at a time. Releases without a
    downloadable asset (e.g. a build that failed mid-publish) are skipped so
    they can't block or short-hop the update."""
    url = f"https://api.github.com/repos/{UPDATE_REPO}/releases?per_page=100"
    req = urllib.request.Request(url, headers={
        "User-Agent": "ProxyTester", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    best_tag, best_url = "", None
    for rel in (data if isinstance(data, list) else []):
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = rel.get("tag_name", "")
        durl = _release_asset_url(rel)
        if not tag or not durl:
            continue
        if not best_tag or _version_tuple(tag) > _version_tuple(best_tag):
            best_tag, best_url = tag, durl
    return best_tag, best_url


def check_for_updates(parent, silent=False):
    """Check GitHub for a newer release; offer to download+install it."""
    try:
        tag, dl = _fetch_latest_release()
    except Exception as e:
        if not silent:
            messagebox.showerror(
                "Check for updates",
                f"Couldn't reach the update server:\n{e}\n\n"
                "The repo/releases must be public for updates to work.")
        return
    if not tag or not dl:
        if not silent:
            messagebox.showinfo("Check for updates", "No release found.")
        return
    if _version_tuple(tag) <= _version_tuple(APP_VERSION):
        if not silent:
            messagebox.showinfo("Check for updates",
                                f"You're on the latest version (v{APP_VERSION}).")
        return
    # The installer swaps a packaged Windows build. Running from source - which
    # is how this runs on macOS/Linux - there is no .exe to swap, so hand over
    # the exact command instead of downloading a Windows zip that can't be
    # applied.
    if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
        if not silent:
            show_source_update_dialog(parent, tag)
        return
    if messagebox.askyesno(
            "Update available",
            f"{tag} is available - you have v{APP_VERSION}.\n\n"
            "Download and install now?"):
        _download_and_apply(parent, dl, tag)


def open_terminal_at(folder):
    """Open a terminal already sitting in `folder`. Returns True on success."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", folder])
            return True
        if sys.platform.startswith("win"):
            subprocess.Popen(f'start "" cmd /k cd /d "{folder}"', shell=True)
            return True
        for term in ("x-terminal-emulator", "gnome-terminal", "konsole",
                     "xfce4-terminal", "xterm"):
            try:
                subprocess.Popen([term], cwd=folder)
                return True
            except (FileNotFoundError, OSError):
                continue
    except Exception:
        pass
    return False


def show_source_update_dialog(parent, tag):
    """Update notice for a run-from-source copy. A plain messagebox can't be
    selected or copied, so the exact shell command goes in a real text box -
    pre-selected, with a Copy button - and is built from THIS install's actual
    path so it can be pasted from any directory."""
    folder = _install_dir()
    is_git = os.path.isdir(os.path.join(folder, ".git"))
    cmd = f'cd "{folder}" && git pull' if is_git else folder

    top = tk.Toplevel(parent)
    top.title("Update available")
    top.configure(bg=BASE)
    top.transient(parent.winfo_toplevel())
    frm = ttk.Frame(top, padding=(16, 14))
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text=f"{tag} is available - you have v{APP_VERSION}.",
              style="Header.TLabel").pack(anchor="w")
    note = ttk.Label(
        frm,
        text=("This copy runs from source. Paste this into Terminal, then "
              "restart the app:") if is_git else
             ("This copy runs from source but isn't a git checkout, so "
              "download the latest ZIP from the repo and replace this folder. "
              "Your settings live elsewhere and won't be lost. The folder is:"),
        style="Muted.TLabel", justify="left", wraplength=470)
    note.pack(anchor="w", pady=(6, 8))

    box = tk.Text(frm, height=2, wrap="word")
    style_text(box)
    box.pack(fill="x")
    box.insert("1.0", cmd)
    box.tag_add("sel", "1.0", "end-1c")   # arrives pre-selected
    box.focus_set()

    status = ttk.Label(frm, text="", style="Muted.TLabel")

    def copy_cmd():
        top.clipboard_clear()
        top.clipboard_append(cmd)
        top.update_idletasks()
        status.config(text="Copied to clipboard")

    def open_term():
        # Copy first, so the Terminal window that appears only needs a paste.
        copy_cmd()
        if open_terminal_at(folder):
            status.config(text="Copied - paste it into the Terminal window "
                               "(Cmd+V, Enter)")
        else:
            status.config(text="Couldn't open a terminal - paste the command "
                               "into one yourself")

    bar = ttk.Frame(frm)
    bar.pack(fill="x", pady=(10, 0))
    ttk.Button(bar, text="Copy command" if is_git else "Copy folder path",
               style="Accent.TButton", command=copy_cmd).pack(side="left")
    ttk.Button(bar, text="Open Terminal",
               command=open_term).pack(side="left", padx=8)
    ttk.Button(bar, text="Close", command=top.destroy).pack(side="right")
    status.pack(anchor="w", pady=(6, 0))

    center_over_parent(top, parent, 520)
    make_modal(top)


def _app_root_in(base):
    """Find the folder holding ProxyTester.exe inside an extracted update."""
    if os.path.isfile(os.path.join(base, "ProxyTester.exe")):
        return base
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path) and \
                os.path.isfile(os.path.join(path, "ProxyTester.exe")):
            return path
    return base


def _download_and_apply(parent, url, tag):
    is_zip = url.lower().split("?", 1)[0].endswith(".zip")
    tmpdir = tempfile.gettempdir()
    dl = os.path.join(tmpdir, f"ProxyTester-{tag}." + ("zip" if is_zip else "exe"))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProxyTester"})
        with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as r, \
                open(dl, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        messagebox.showerror("Update", f"Download failed:\n{e}")
        return

    frozen_win = getattr(sys, "frozen", False) and os.name == "nt"
    bat = os.path.join(tmpdir, "proxytester_update.bat")

    if is_zip:
        # onedir update: unpack the app folder and mirror it over the install
        # directory. No runtime DLL unpacking, so nothing races antivirus.
        staging = os.path.join(tmpdir, f"ProxyTester-{tag}-new")
        try:
            if os.path.isdir(staging):
                shutil.rmtree(staging, ignore_errors=True)
            with zipfile.ZipFile(dl) as z:
                z.extractall(staging)
        except Exception as e:
            messagebox.showerror("Update", f"Could not unpack the update:\n{e}")
            return
        if not frozen_win:
            messagebox.showinfo(
                "Update downloaded",
                f"Unpacked {tag} to:\n{staging}\n\n"
                "Close ProxyTester and replace your install folder with it.")
            return
        src = _app_root_in(staging)
        install_dir = os.path.dirname(sys.executable)
        script = (
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            "set n=0\r\n"
            ":retry\r\n"
            # /XD exports: never delete the user's exported CSVs on update.
            f'robocopy "{src}" "{install_dir}" /MIR /R:15 /W:1 '
            f'/XD "{os.path.join(install_dir, "exports")}" '
            "/NFL /NDL /NJH /NJS /NC /NS /NP >nul\r\n"
            "if errorlevel 8 if %n% lss 20 "
            "(set /a n+=1 & timeout /t 1 /nobreak >nul & goto retry)\r\n"
            f'start "" "{os.path.join(install_dir, "ProxyTester.exe")}"\r\n'
            f'rmdir /s /q "{staging}" >nul 2>&1\r\n'
            f'del "{dl}" >nul 2>&1\r\n'
            'del "%~f0"\r\n'
        )
    else:
        # Legacy single-file swap (older releases that ship a bare .exe).
        if not frozen_win:
            messagebox.showinfo(
                "Update downloaded",
                f"Saved {tag} to:\n{dl}\n\nClose ProxyTester and run that file.")
            return
        current = sys.executable
        script = (
            "@echo off\r\n"
            "set n=0\r\n"
            ":retry\r\n"
            f'move /y "{dl}" "{current}" >nul 2>&1\r\n'
            "if errorlevel 1 if %n% lss 20 "
            "(set /a n+=1 & timeout /t 1 /nobreak >nul & goto retry)\r\n"
            f'start "" "{current}"\r\n'
            'del "%~f0"\r\n'
        )

    try:
        with open(bat, "w") as f:
            f.write(script)
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
    except Exception as e:
        messagebox.showerror(
            "Update",
            f"Could not launch the updater:\n{e}\n\nUpdate saved at:\n{dl}")
        return
    parent.winfo_toplevel().destroy()  # exit so the files can be replaced


# --------------------------------------------------------------------------- #
# Single-instance guard: a later launch pings the running copy and exits, and
# the running copy brings its window to the front (handy with multi-monitor
# taskbars). Uses a fixed localhost port as the lock - standard library only.
# --------------------------------------------------------------------------- #
_SINGLE_INSTANCE_PORT = 50573
_SINGLE_INSTANCE_TOKEN = b"ProxyTester-show"


def _signal_existing_instance():
    """If another instance is already running, ask it to come to the front and
    return True. Returns False if we are the first instance (or the port is held
    by something that isn't us, so we should just start normally)."""
    try:
        with socket.create_connection(
                ("127.0.0.1", _SINGLE_INSTANCE_PORT), timeout=0.6) as s:
            s.sendall(_SINGLE_INSTANCE_TOKEN)
            s.settimeout(0.6)
            ack = s.recv(8)
        return ack.strip() == b"OK"   # only true when the peer is really us
    except OSError:
        return False


def _bring_to_front(root):
    """Restore, raise, and focus the window (called on the GUI thread)."""
    try:
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
        root.focus_force()
    except Exception:
        pass


def _listen_for_second_instance(root):
    """Hold the single-instance port; when a later launch pings it, raise this
    window. Returns the server socket (keep a reference so it isn't GC'd) or
    None if we couldn't bind - in which case the guard is simply skipped."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # No SO_REUSEADDR on purpose: on Windows that would let a 2nd instance
        # bind the same port and defeat the lock.
        srv.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        srv.listen(5)
    except OSError:
        return None

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return          # socket closed on exit
            try:
                data = conn.recv(64)
                if _SINGLE_INSTANCE_TOKEN in data:
                    try:
                        conn.sendall(b"OK")
                    except OSError:
                        pass
                    root.after(0, lambda: _bring_to_front(root))
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    return srv


def _raise_fd_limit():
    """The connect-only fast path opens hundreds-to-thousands of sockets at
    once. On macOS/Linux the default soft file-descriptor limit is often 256,
    which would cap concurrency and throw 'Too many open files'. Raise the soft
    limit toward the hard limit. POSIX-only; Windows has no such limit and no
    `resource` module."""
    if sys.platform.startswith("win"):
        return
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = min(hard, 4096) if hard != resource.RLIM_INFINITY else 4096
        if soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except Exception:
        pass


def main():
    if _signal_existing_instance():
        return  # another instance is already open - brought it to the front

    _raise_fd_limit()

    root = tk.Tk()
    root.title("ProxyTester")
    root.geometry("1340x900")  # wide enough that result columns show untruncated
    root.minsize(900, 640)
    apply_theme(root)

    if LOGO_ICON_B64:
        try:
            root._icon_img = tk.PhotoImage(data=LOGO_ICON_B64)
            root.iconphoto(True, root._icon_img)
        except Exception:
            pass

    notebook = ttk.Notebook(root)
    asn_tab = AsnTab(notebook)
    proxy_tab = ProxyTab(notebook)
    quality_tab = QualityTab(notebook)
    converter_tab = ConverterTab(notebook)
    settings_tab = SettingsTab(notebook, on_saved=asn_tab.load_mobile_creds)
    notebook.add(asn_tab, text="ASN Tester")
    notebook.add(proxy_tab, text="Proxy Tester")
    notebook.add(quality_tab, text="IP Quality")
    notebook.add(converter_tab, text="Converter")
    notebook.add(settings_tab, text="Settings")

    bar = HeaderBar(root)
    bar.pack(fill="x")
    notebook.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    # Keep a reference so the listening socket lives as long as the window.
    root._instance_server = _listen_for_second_instance(root)

    # macOS system Tk 8.5 sometimes opens a blank/white window until something
    # forces a repaint - nudge it. Harmless elsewhere; the real fix for old Tk
    # is python.org Python (Tk 8.6).
    root.update_idletasks()
    root.lift()
    root.after(60, lambda: (root.deiconify(), root.update()))

    root.mainloop()


if __name__ == "__main__":
    main()
