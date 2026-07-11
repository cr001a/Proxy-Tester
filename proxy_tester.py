"""
ProxyTester - a proxy testing GUI.

Made by codyrandolph.

Two tabs:
  1. ASN Tester (Oxylabs mobile) - tests carrier/ASN targeting.
  2. Proxy Tester (general)      - plain reachability/latency testing.

Standard library only (tkinter, urllib, threading, concurrent.futures, ...).
Package with:
    pyinstaller --onefile --windowed --name ProxyTester proxy_tester.py
"""

import csv
import json
import os
import queue
import random
import re
import socket
import statistics
import string
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urlsplit

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DEFAULT_TIMEOUT = 15  # seconds, per request
MAX_WORKERS = 6       # thread pool size for parallel targets
USER_AGENT = "ProxyTester/1.0"

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
        # Only engage drag-select for a plain click; let Ctrl/Shift-click be
        # handled natively (toggle / extend) without interference.
        if event.state & (SHIFT | CTRL):
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
    opener = urllib.request.build_opener(handler)
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


# --------------------------------------------------------------------------- #
# Profile persistence (JSON in the user's config dir)
# --------------------------------------------------------------------------- #
def _config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ProxyTester")


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


PROVIDERS = {
    "Oxylabs": {"host": "pr.oxylabs.io", "port": "7777",
                "build": _oxylabs_username},
}


def build_username(provider, user, asn, sessid=None, sesstime=None):
    spec = PROVIDERS.get(provider) or next(iter(PROVIDERS.values()))
    return spec["build"](user, asn, sessid, sesstime)


def provider_hostport(provider):
    spec = PROVIDERS.get(provider)
    if spec:
        return spec["host"], spec["port"]
    return "", ""


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
    Parse 'host:port:user:pass' (or 'host:port') into a dict.
    Returns None if the line is not usable.
    """
    parts = line.strip().split(":")
    if len(parts) == 2:
        host, port = parts
        user = pw = None
    elif len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        pw = ":".join(parts[3:])  # allow ':' inside password
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
    else:
        proxy_url = build_proxy_url(host, port)
        display = f"{host}:{port}"

    latencies = []
    successes = 0
    last_code = None
    exit_ip = ""
    labels = []

    for _ in range(runs):
        if stop_event is not None and stop_event.is_set():
            break
        r = do_request(proxy_url, url, timeout)
        code = response_code(r)
        if code is not None:
            last_code = code
        if r["ok"]:
            successes += 1
            latencies.append(r["ms"])
            found_ip = _parse_json_field(r["body"], "ip")
            if found_ip:
                exit_ip = found_ip
        else:
            labels.append(response_label(r))

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
        "status": status,
        "code": str(last_code) if last_code is not None else "-",
        "median": statistics.median(latencies) if latencies else None,
        "success": successes,
        "runs": runs,
        "exit_ip": exit_ip,
        "reason": "",
    }


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class AsnTab(ttk.Frame):
    COLUMNS = ("asn", "status", "median", "min", "max", "success", "org")
    HEADINGS = {
        "asn": "ASN", "status": "Status", "median": "Median ms",
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

        self.host = tk.StringVar(value="pr.oxylabs.io")
        self.port = tk.StringVar(value="7777")
        self.username = tk.StringVar()
        self.password = tk.StringVar()
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
        field(5, "Test URL", self.url, width=40)
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
        ttk.Label(frow2, text="search").pack(side="left", padx=(12, 4))
        self.search_var = tk.StringVar()
        ttk.Entry(frow2, textvariable=self.search_var, width=14).pack(
            side="left")
        self.search_var.trace_add("write", lambda *a: self._refilter_asns())

        lb_row = ttk.Frame(asn_frame)
        lb_row.pack(fill="both")
        self.asn_list = tk.Listbox(
            lb_row, selectmode="extended", height=9, width=36,
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

        ttk.Label(asn_frame, text="+ paste custom ASNs (one per line)").pack(
            anchor="w", pady=(8, 0))
        self.asn_text = tk.Text(asn_frame, width=34, height=4)
        style_text(self.asn_text)
        self.asn_text.pack(fill="x")

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
        for col in self.COLUMNS:
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=110, anchor="center")
        self.tree.column("org", width=200, anchor="w")
        tag_tree(self.tree)
        enable_drag_select(self.tree)
        self.tree.pack(fill="both", expand=True, pady=(8, 0))

        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _refilter_asns(self):
        """Rebuild the ASN list from the active category/strict/search filters."""
        cats = {c for c, v in self.filter_vars.items() if v.get()}
        strict_only = self.strict_var.get()
        q = self.search_var.get().strip().lower()
        self.asn_list.delete(0, "end")
        self._visible_asns = []
        for asn, name, cat, strict in ASN_CATALOG:
            if cat not in cats:
                continue
            if strict_only and not strict:
                continue
            if q and q not in asn and q not in name.lower():
                continue
            label = f"{asn}  -  {name}  [{cat}]"
            if cat == "residential" and not strict:
                label += " +biz"
            self.asn_list.insert("end", label)
            self._visible_asns.append(asn)

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
        host, port = provider_hostport(self.provider.get())
        if host:
            self.host.set(host)
        if port:
            self.port.set(port)

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

        lines = []
        for asn in asns:
            for _ in range(count):
                if mode == "static":
                    user = build_username(provider, username, asn,
                                          _random_sessid(), sesstime)
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
        for asn in asns:
            iid = self.tree.insert(
                "", "end", values=(asn, "testing...", "-", "-", "-", "-", ""),
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
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
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
        values = (r["asn"], r["status"], _fmt_ms(r["median"]),
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
            if vals[1] == "testing...":
                self.tree.item(iid, values=(vals[0], "stopped") + vals[2:],
                               tags=("muted",))
        self._sort_rows()
        self.status_lbl.config(text="Stopped" if stopped else "Done")

    def _sort_rows(self):
        """OK rows first, ascending median; everything else after."""
        rows = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            try:
                median = float(vals[2])
            except (ValueError, TypeError):
                median = float("inf")
            ok_rank = 0 if vals[1] == "OK" else 1
            rows.append((ok_rank, median, iid))
        rows.sort(key=lambda t: (t[0], t[1]))
        for index, (_, _, iid) in enumerate(rows):
            self.tree.move(iid, "", index)

    def on_export(self):
        export_tree_csv(self.tree, self.COLUMNS,
                        [self.HEADINGS[c] for c in self.COLUMNS])


class ProxyTab(ttk.Frame):
    COLUMNS = ("proxy", "status", "code", "median", "success", "exit_ip")
    HEADINGS = {
        "proxy": "Proxy", "status": "Status", "code": "HTTP code",
        "median": "Median ms", "success": "Success (n/N)", "exit_ip": "Exit IP",
    }

    def __init__(self, master):
        super().__init__(master, padding=14)
        self.queue = queue.Queue()
        self.running = False
        self.stop_event = threading.Event()
        self._build()

    def _build(self):
        form = ttk.Frame(self)
        form.pack(fill="x")

        ttk.Label(form, text="Proxies (host:port:user:pass, one per line)").grid(
            row=0, column=0, sticky="w")
        self.proxy_text = tk.Text(form, width=50, height=8)
        style_text(self.proxy_text)
        self.proxy_text.grid(row=1, column=0, rowspan=4, sticky="nw", padx=(0, 24))

        self.url = tk.StringVar(value="https://ipinfo.io/json")
        self.runs = tk.StringVar(value="3")

        ttk.Label(form, text="Test URL").grid(row=1, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.url, width=40).grid(
            row=1, column=2, sticky="w", pady=3)
        ttk.Label(form, text="Runs per proxy").grid(row=2, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.runs, width=6).grid(
            row=2, column=2, sticky="w", pady=3)

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 4))
        self.run_btn = ttk.Button(btns, text="Run", style="Accent.TButton",
                                  command=self.on_run)
        self.run_btn.pack(side="left")
        self.export_btn = ttk.Button(btns, text="Export CSV",
                                     command=self.on_export)
        self.export_btn.pack(side="left", padx=8)
        self.status_lbl = ttk.Label(btns, text="Idle", style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        for col in self.COLUMNS:
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=120, anchor="center")
        self.tree.column("proxy", width=260, anchor="w")
        tag_tree(self.tree)
        enable_drag_select(self.tree)
        self.tree.pack(fill="both", expand=True, pady=(8, 0))

        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

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
        self.runs.set(d.get("runs", "3"))

    def on_run(self):
        if self.running:
            return
        url = self.url.get().strip()
        try:
            runs = max(1, int(self.runs.get().strip()))
        except ValueError:
            messagebox.showerror("ProxyTester", "Runs per proxy must be a number.")
            return
        if not url:
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
        self.running = True
        self.stop_event.clear()
        self.run_btn.config(text="Stop", style="Stop.TButton",
                            command=self.on_stop)
        self.status_lbl.config(text=f"Testing {len(proxies)} proxy(ies)...")

        worker = threading.Thread(
            target=self._run_pool, args=(proxies, url, runs), daemon=True)
        worker.start()
        self.after(100, self._drain_queue)

    def on_stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.run_btn.config(state="disabled")
        self.status_lbl.config(text="Stopping...")

    def _run_pool(self, proxies, url, runs):
        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {
                    pool.submit(test_proxy, p, url, runs, DEFAULT_TIMEOUT,
                                self.stop_event): p
                    for p in proxies
                }
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
        except queue.Empty:
            pass
        if self.running:
            self.after(100, self._drain_queue)

    def _insert_row(self, r):
        self.tree.insert("", "end", values=(
            r["proxy"], r["status"], r["code"], _fmt_ms(r["median"]),
            f"{r['success']}/{r['runs']}", r["exit_ip"],
        ), tags=(status_tag(r["status"]),))

    def _finish(self):
        stopped = self.stop_event.is_set()
        self.running = False
        self.run_btn.config(text="Run", style="Accent.TButton",
                            command=self.on_run, state="normal")
        self.status_lbl.config(text="Stopped" if stopped else "Done")

    def on_export(self):
        export_tree_csv(self.tree, self.COLUMNS,
                        [self.HEADINGS[c] for c in self.COLUMNS])


def center_over_parent(top, parent, w=None, h=None):
    """Position a popup centered over the main app window (not top-left of a
    huge monitor). Sets size too when w/h are given."""
    top.update_idletasks()
    root = parent.winfo_toplevel()
    w = w or top.winfo_reqwidth()
    h = h or top.winfo_reqheight()
    px, py = root.winfo_rootx(), root.winfo_rooty()
    pw, ph = root.winfo_width(), root.winfo_height()
    x = max(px, px + (pw - w) // 2)
    y = max(py, py + (ph - h) // 2)
    top.geometry(f"{w}x{h}+{x}+{y}")


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
                    variable=mode, value="rotating").pack(anchor="w", padx=24)
    ttk.Radiobutton(top, text="Static  -  sticky IP per proxy",
                    variable=mode, value="static").pack(anchor="w", padx=24)

    row = ttk.Frame(top)
    row.pack(anchor="w", padx=16, pady=(10, 2))
    ttk.Label(row, text="Proxies per ASN").pack(side="left")
    ttk.Entry(row, textvariable=count, width=6).pack(side="left", padx=8)

    row2 = ttk.Frame(top)
    row2.pack(anchor="w", padx=16, pady=(2, 4))
    ttk.Label(row2, text="Sticky minutes (static only, max 30, blank = none)").pack(
        side="left")
    ttk.Entry(row2, textvariable=sesstime, width=6).pack(side="left", padx=8)

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
        else:
            st = None
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
    top.grab_set()
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

    box = tk.Text(top, wrap="none")
    style_text(box)
    box.pack(fill="both", expand=True, padx=14)
    box.insert("1.0", text)

    btns = ttk.Frame(top)
    btns.pack(fill="x", padx=14, pady=12)

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
    center_over_parent(top, parent, 680, 440)
    box.focus_set()


def export_tree_csv(tree, columns, headings):
    rows = tree.get_children()
    if not rows:
        messagebox.showinfo("Export CSV", "No results to export yet.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        title="Export results to CSV")
    if not path:
        return
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headings)
            for iid in rows:
                writer.writerow(tree.item(iid, "values"))
    except OSError as e:
        messagebox.showerror("Export CSV", f"Could not write file:\n{e}")
        return
    messagebox.showinfo("Export CSV", f"Exported {len(rows)} row(s) to:\n{path}")


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


class ProfileBar(ttk.Frame):
    """Top bar: pick / save / delete named credential profiles."""

    def __init__(self, master, store, tabs):
        super().__init__(master, padding=(14, 12, 14, 4))
        self.store = store
        self.tabs = tabs  # dict: key -> tab with get_state/set_state

        ttk.Label(self, text="◆ ProxyTester", style="Header.TLabel").pack(
            side="left")
        ttk.Label(self, text="made by codyrandolph",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0),
                                             anchor="s", pady=(0, 4))

        ttk.Button(self, text="Delete", command=self.on_delete).pack(
            side="right", padx=(8, 0))
        ttk.Button(self, text="Save", style="Accent.TButton",
                   command=self.on_save).pack(side="right", padx=8)
        self.combo = ttk.Combobox(self, values=self.store.names(), width=26)
        self.combo.pack(side="right")
        self.combo.bind("<<ComboboxSelected>>", self.on_select)
        ttk.Label(self, text="Profile:").pack(side="right", padx=(0, 8))

    def _collect(self):
        return {key: tab.get_state() for key, tab in self.tabs.items()}

    def _apply(self, state):
        for key, tab in self.tabs.items():
            if isinstance(state, dict) and state.get(key):
                tab.set_state(state[key])

    def on_select(self, _event=None):
        state = self.store.get(self.combo.get())
        if state:
            self._apply(state)

    def on_save(self):
        name = self.combo.get().strip()
        if not name:
            messagebox.showerror("Profiles", "Type a profile name first.")
            return
        self.store.save(name, self._collect())
        self.combo.config(values=self.store.names())
        messagebox.showinfo(
            "Profiles",
            f"Saved profile '{name}'.\n\nStored locally (including passwords) at:\n"
            f"{self.store.path}")

    def on_delete(self):
        name = self.combo.get().strip()
        if name not in self.store.data:
            return
        if messagebox.askyesno("Profiles", f"Delete profile '{name}'?"):
            self.store.delete(name)
            self.combo.set("")
            self.combo.config(values=self.store.names())


def main():
    root = tk.Tk()
    root.title("ProxyTester")
    root.geometry("1000x880")  # roomy enough for ~10 result rows
    root.minsize(820, 640)
    apply_theme(root)

    store = ProfileStore()

    notebook = ttk.Notebook(root)
    asn_tab = AsnTab(notebook)
    proxy_tab = ProxyTab(notebook)
    converter_tab = ConverterTab(notebook)
    notebook.add(asn_tab, text="ASN Tester")
    notebook.add(proxy_tab, text="Proxy Tester")
    notebook.add(converter_tab, text="Converter")

    bar = ProfileBar(root, store, {"asn": asn_tab, "proxy": proxy_tab})
    bar.pack(fill="x")
    notebook.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    root.mainloop()


if __name__ == "__main__":
    main()
