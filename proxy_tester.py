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

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from logo_assets import LOGO_HEADER_B64, LOGO_ICON_B64
except ImportError:  # logo is optional
    LOGO_HEADER_B64 = LOGO_ICON_B64 = None

DEFAULT_TIMEOUT = 15   # seconds, per request
MAX_WORKERS = 6        # legacy default (kept for reference)
DEFAULT_WORKERS = 20   # parallel workers; overridable on the Settings tab
USER_AGENT = "ProxyTester/1.0"

APP_VERSION = "3.44"                    # single source of truth (CI tags v<this>)
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


# --------------------------------------------------------------------------- #
# IP quality / trust scoring
# --------------------------------------------------------------------------- #
# A proxy is only as good as the reputation of the IP it exits on. We measure
# that two ways: IPQualityScore (paid, best-in-class fraud/bot/proxy scoring)
# and Spamhaus ZEN (free DNS blocklist, no key). Both feed a single 0-100
# Trust score - higher is cleaner / more likely to pass anti-bot queues.
IPINFO_URL = "https://ipinfo.io/json"


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


def spamhaus_listed(ip):
    """Spamhaus ZEN DNSBL check (free, no key). True=listed, False=clean,
    None=couldn't tell. Real listings answer 127.0.0.2-127.0.0.11; a
    127.255.255.x answer means the query was refused (e.g. a public/cloud DNS
    resolver) - that's 'unknown', NOT listed. Treating those as listed is what
    made every row flip between listed/clean run to run."""
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return None
    query = ".".join(reversed(parts)) + ".zen.spamhaus.org"
    try:
        answers = socket.gethostbyname_ex(query)[2]
    except socket.gaierror:
        return False                # NXDOMAIN => not on the list
    except OSError:
        return None
    if any(a.startswith("127.0.0.") for a in answers):
        return True                 # a genuine listing code
    return None                     # 127.255.255.x => resolver refused, unknown


def ipqs_lookup(ip, api_key, timeout=DEFAULT_TIMEOUT):
    """Query IPQualityScore for an IP. Returns a normalized dict or None."""
    url = ("https://ipqualityscore.com/api/json/ip/"
           f"{quote(api_key, safe='')}/{quote(ip, safe='')}"
           "?strictness=1&allow_public_access_points=true")
    data = http_get_json(url, timeout)
    if not isinstance(data, dict) or not data.get("success", False):
        return None
    return {
        "fraud_score": data.get("fraud_score"),
        "connection_type": data.get("connection_type", ""),
        "recent_abuse": bool(data.get("recent_abuse")),
        "bot_status": bool(data.get("bot_status")),
        "proxy": bool(data.get("proxy")),
        "vpn": bool(data.get("vpn")),
        "tor": bool(data.get("tor")),
        "isp": data.get("ISP", "") or data.get("organization", ""),
        "country": data.get("country_code", ""),
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
        score -= 20
    lat = q.get("latency_ms")
    if isinstance(lat, (int, float)) and lat > 2500:
        score -= 5
    return max(0, min(100, int(round(score))))


def proxycheck_lookup(ip, api_key, timeout=DEFAULT_TIMEOUT):
    """Query proxycheck.io for an IP. Cheap/high-volume alternative to IPQS
    (1,000/day free). Returns a normalized dict (same shape as ipqs_lookup)."""
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


def ipinfo_lookup(ip, token, timeout=DEFAULT_TIMEOUT):
    """Query IPinfo's api.ipinfo.io/lookup endpoint (Bearer auth) - a neutral
    IP-data vendor. The `anonymous` object carries is_proxy/is_vpn/is_tor/
    is_relay/is_res_proxy; `as` carries ASN type (hosting/isp/business); geo,
    mobile, and top-level is_hosting/is_mobile round it out. We synthesize a
    0-100 fraud score from those flags."""
    data, err = http_get_json_ex(
        "https://api.ipinfo.io/lookup/" + quote(ip, safe=""),
        timeout, extra_headers={"Authorization": "Bearer " + token})
    if err or not isinstance(data, dict):
        return {"_error": f"IPinfo: {err or 'no data'}"}
    anon_o = data.get("anonymous") if isinstance(data.get("anonymous"),
                                                 dict) else {}
    as_o = data.get("as") if isinstance(data.get("as"), dict) else {}
    geo_o = data.get("geo") if isinstance(data.get("geo"), dict) else {}
    mob_o = data.get("mobile") if isinstance(data.get("mobile"), dict) else {}

    vpn = bool(anon_o.get("is_vpn"))
    proxy = bool(anon_o.get("is_proxy"))
    tor = bool(anon_o.get("is_tor"))
    relay = bool(anon_o.get("is_relay"))
    res_proxy = bool(anon_o.get("is_res_proxy"))
    hosting = bool(data.get("is_hosting"))
    is_mobile = bool(data.get("is_mobile")) or bool(mob_o.get("carrier")
                                                    or mob_o.get("name"))
    # Some tiers include the residential-proxy service name; keep it if present.
    service = str(anon_o.get("service") or anon_o.get("res_proxy_service")
                  or "").strip()
    carrier_name = str(mob_o.get("carrier") or mob_o.get("name") or "").strip()

    org_type = (as_o.get("type") or "").lower()
    anon = res_proxy or proxy or vpn or tor or relay
    if res_proxy or proxy:
        fraud = 90                      # a proxy exit -> burnt
    elif vpn or tor or relay:
        fraud = 85
    elif hosting or org_type == "hosting":
        fraud = 60                      # datacenter / hosting
    else:
        fraud = 5                       # clean residential / ISP / mobile
    if res_proxy:
        conn = "Residential proxy"
    elif is_mobile:
        conn = "Mobile"
    elif hosting or org_type == "hosting":
        conn = "Datacenter"
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
    if service:
        extra.append(service.lower())
    if carrier_name:
        extra.append(carrier_name.lower())
    return {
        "fraud_score": fraud,
        "connection_type": conn,        # Mobile / Residential proxy / DC / ...
        "proxy": anon,
        "vpn": vpn,
        "tor": tor,
        "recent_abuse": res_proxy or proxy,
        "bot_status": False,
        "isp": org,
        "country": geo_o.get("country_code") or geo_o.get("country", ""),
        "flag_extra": list(dict.fromkeys(extra)),   # deduped, order-preserved
    }


# Supported IP-reputation providers. The key for each lives in settings.json
# (entered on the Settings tab), never in code.
QUALITY_PROVIDERS = {
    "proxycheck.io": ("proxycheck_api_key", proxycheck_lookup),
    "IPinfo": ("ipinfo_token", ipinfo_lookup),
    "IPQualityScore": ("ipqs_api_key", ipqs_lookup),
}


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


def score_ip(ip, provider, api_key, timeout=DEFAULT_TIMEOUT):
    """Score one exit IP: free Spamhaus check + the chosen provider (if a key is
    set). Only the public IP is sent to the provider - never any credential."""
    q = {"blacklisted": spamhaus_listed(ip)}
    lookup = QUALITY_PROVIDERS.get(provider, (None, None))[1]
    if api_key and lookup:
        q.update(lookup(ip, api_key, timeout) or {})
    return q


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
        "blacklist": "listed" if bl is True else ("clean" if bl is False else "-"),
        "ping": disc["ping"],
        "trust": _trust_score(q),
        "status": "OK",
    }


# --------------------------------------------------------------------------- #
# Profile persistence (JSON in the user's config dir)
# --------------------------------------------------------------------------- #
def _config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ProxyTester")


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


def get_workers():
    """Parallel worker count (from Settings), clamped to a sane range."""
    try:
        n = int(load_setting("concurrency", DEFAULT_WORKERS))
    except (TypeError, ValueError):
        n = DEFAULT_WORKERS
    return max(1, min(100, n))


def split_creds(value):
    """Split a 'user:pass' string into (user, pass) on the FIRST colon, so a
    password containing colons stays intact. Returns ('', '') if empty."""
    value = (value or "").strip()
    if ":" in value:
        u, p = value.split(":", 1)
        return u.strip(), p.strip()
    return value, ""


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


# --------------------------------------------------------------------------- #
# Residential batch generation (client-side session-string construction).
# Nothing is fetched from an API: you make N distinct proxies by putting a
# unique random session token in each line (same token = same sticky IP).
# Credentials come from the Settings tab, never hard-coded.
# --------------------------------------------------------------------------- #
def _resi_sessid(n=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))


def _build_oxylabs_resi(user, pw, state, city, lifetime, sessid):
    # pr.oxylabs.io: params live in the username; country/state/city + sticky.
    u = f"customer-{user}-cc-us"
    if state:
        u += f"-st-us_{state}"
    if city:
        u += f"-city-{city}"
    if sessid:
        u += f"-sessid-{sessid}"
        if lifetime:
            u += f"-sesstime-{lifetime}"          # minutes
    return f"pr.oxylabs.io:7777:{u}:{pw}"


def _build_iproyal_resi(user, pw, state, city, lifetime, sessid):
    # geo.iproyal.com: params live in the password; sticky via session+lifetime.
    p = f"{pw}_country-us"
    if state:
        p += f"_state-{state}"
    if city:
        p += f"_city-{city}"
    if sessid:
        p += f"_session-{sessid}"
        if lifetime:
            p += f"_lifetime-{lifetime}m"
    return f"geo.iproyal.com:12321:{user}:{p}"


# Residential providers for the batch generator. `key` -> a combined
# 'user:pass' setting; `legacy` -> the old split keys, kept for migration.
RESI_PROVIDERS = {
    "Oxylabs Residential": {
        "key": "oxylabs_resi",
        "legacy": ("oxylabs_resi_user", "oxylabs_resi_pass"),
        "build": _build_oxylabs_resi,
    },
    "IPRoyal": {
        "key": "iproyal",
        "legacy": ("iproyal_user", "iproyal_pass"),
        "build": _build_iproyal_resi,
    },
}


def configured_resi_providers():
    """Providers that have both a username and password saved in settings."""
    out = []
    for name, spec in RESI_PROVIDERS.items():
        u, p = load_provider_creds(spec["key"], spec.get("legacy"))
        if u and p:
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


def generate_resi_batch(provider, region_type, regions, lifetime, count,
                        rotating=False):
    """Build `count` residential proxy lines, spread round-robin across the
    selected `regions` (canonical state/city names). region_type is
    'Country'/'State'/'City'. Each line gets a unique session token unless
    rotating. Credentials load from settings. Returns (lines, error_or_None)."""
    spec = RESI_PROVIDERS.get(provider)
    if not spec:
        return [], f"Unknown provider: {provider}"
    user, pw = load_provider_creds(spec["key"], spec.get("legacy"))
    if not user or not pw:
        return [], f"Add {provider} username:password on the Settings tab first."
    targets = regions if (region_type in ("State", "City") and regions) else [""]
    lines = []
    for i in range(count):
        tgt = targets[i % len(targets)]
        state = tgt if region_type == "State" else ""
        city = tgt if region_type == "City" else ""
        lines.append(spec["build"](user, pw, state, city, lifetime,
                                   None if rotating else _resi_sessid()))
    return lines, None


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
    else:
        proxy_url = build_proxy_url(host, port)
        display = f"{host}:{port}"

    latencies = []
    successes = 0
    last_code = None
    exit_ip = ""
    org = city = region = country = ""
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
        "status": status,
        "code": str(last_code) if last_code is not None else "-",
        "median": statistics.median(latencies) if latencies else None,
        "success": successes,
        "runs": runs,
        "exit_ip": exit_ip,
        "org": org,
        "location": location,
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
            "asn":     (80,  60,  False, "center"),
            "type":    (110, 80,  False, "center"),
            "status":  (200, 150, True,  "center"),
            "median":  (90,  70,  False, "center"),
            "min":     (90,  70,  False, "center"),
            "max":     (90,  70,  False, "center"),
            "success": (110, 90,  False, "center"),
            "org":     (220, 140, True,  "w"),
        }
        for col in self.COLUMNS:
            w, mw, st, anc = layout[col]
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=w, minwidth=mw, stretch=st, anchor=anc)
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
        if not cats:                       # nothing checked -> show everything
            cats = set(CATEGORIES)
        strict_only = self.strict_var.get()
        # Search accepts several terms separated by commas or spaces; a row
        # matches if ANY term is found in its ASN number or provider name.
        terms = [t for t in re.split(r"[\s,]+",
                                     self.search_var.get().strip().lower()) if t]
        self.asn_list.delete(0, "end")
        self._visible_asns = []
        for asn, name, cat, strict in all_asns():
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
        """Fill Username/Password from the Oxylabs mobile creds saved in
        Settings. Called after Save so newly-entered creds sync into this tab
        without a restart (only while the provider is Oxylabs)."""
        if self.provider.get() != "Oxylabs":
            return
        u, p = load_provider_creds("oxylabs_mobile")
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
        ttk.Button(btns, text="Generate batch",
                   command=lambda: open_generate_dialog(
                       self, self.proxy_text)).pack(side="left", padx=8)
        self.shuffle_btn = ttk.Button(btns, text="Shuffle list",
                                      command=self.on_shuffle)
        self.shuffle_btn.pack(side="left", padx=8)
        self.status_lbl = ttk.Label(btns, text="Idle", style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)

        # Site ping: measure direct (no-proxy) latency to a retailer's edge.
        ping_bar = ttk.Frame(self)
        ping_bar.pack(fill="x", pady=(0, 2))
        ttk.Label(ping_bar,
                  text="Site ping (direct latency, no proxy):").pack(side="left")
        self.ping_site_var = tk.StringVar(value="Walmart")
        ttk.Combobox(
            ping_bar, textvariable=self.ping_site_var, state="readonly",
            width=22,
            values=["All presets"] + [n for n, _ in RETAIL_SITES]
            + ["Custom (Test URL)"]).pack(side="left", padx=8)
        self.ping_btn = ttk.Button(ping_bar, text="Ping site",
                                   command=self.on_ping_site)
        self.ping_btn.pack(side="left")

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        # (width, minwidth, stretch, anchor). Status stretches, is left-aligned,
        # and has a minwidth so the exact response (e.g. "502 exit node not
        # found") stays readable and can never be squeezed down to "5xx".
        layout = {
            "proxy":    (240, 140, True,  "w"),
            "status":   (150, 110, False, "w"),
            "code":     (75,  55,  False, "center"),
            "median":   (85,  65,  False, "center"),
            "success":  (95,  80,  False, "center"),
            "exit_ip":  (130, 100, False, "w"),
            "org":      (210, 130, True,  "w"),
            "location": (160, 110, True,  "w"),
        }
        for col in self.COLUMNS:
            w, mw, st, anc = layout[col]
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=w, minwidth=mw, stretch=st, anchor=anc)
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
            with ThreadPoolExecutor(max_workers=get_workers()) as pool:
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
        if r.get("_ping"):
            rng = ("-" if r["min"] is None
                   else f"min {r['min']:.0f} / max {r['max']:.0f} ms")
            self.tree.insert("", "end", values=(
                f"PING  {r['name']} - {r['host']}", r["status"], "-",
                _fmt_ms(r["median"]), f"{r['success']}/{r['runs']}",
                "", rng, "direct (no proxy)",
            ), tags=(status_tag(r["status"]),))
            return
        self.tree.insert("", "end", values=(
            r["proxy"], r["status"], r["code"], _fmt_ms(r["median"]),
            f"{r['success']}/{r['runs']}", r["exit_ip"],
            r.get("org", ""), r.get("location", ""),
        ), tags=(status_tag(r["status"]),))

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

        self.running = True
        self.stop_event.clear()
        self.run_btn.config(state="disabled")
        self.ping_btn.config(text="Stop", style="Stop.TButton",
                             command=self.on_stop)
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

    def _finish(self):
        stopped = self.stop_event.is_set()
        self.running = False
        self.run_btn.config(text="Run", style="Accent.TButton",
                            command=self.on_run, state="normal")
        self.ping_btn.config(text="Ping site", style="TButton",
                             command=self.on_ping_site, state="normal")
        self.status_lbl.config(text="Stopped" if stopped else "Done")

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
    """Batch generator: build N residential proxy lines by spec and drop them
    into `text_widget`. Optional - if unused, the text box works as before."""
    configured = configured_resi_providers()
    if not configured:
        messagebox.showinfo(
            "Generate batch",
            "Add a provider's username/password on the Settings tab first "
            "(Oxylabs Residential or IPRoyal).")
        return
    top = tk.Toplevel(parent)
    top.title("Generate residential batch")
    top.configure(bg=BASE)
    top.transient(parent.winfo_toplevel())
    top.resizable(False, False)

    provider = tk.StringVar(value=configured[0])
    region_type = tk.StringVar(value="Country")
    lifetime = tk.StringVar(value="30")
    count = tk.StringVar(value="500")
    rotating = tk.BooleanVar(value=False)
    append = tk.BooleanVar(value=False)
    region_vars = {}          # canonical -> BooleanVar (rebuilt per region type)

    frm = ttk.Frame(top, padding=(16, 14))
    frm.pack(fill="both", expand=True)

    row = 0

    def add(label, widget):
        nonlocal row
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
        widget.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=4)
        row += 1

    add("Provider", ttk.Combobox(frm, textvariable=provider, values=configured,
                                 width=22, state="readonly"))
    add("Country", ttk.Label(frm, text="United States (fixed)",
                             style="Muted.TLabel"))
    add("Region type", ttk.Combobox(frm, textvariable=region_type, width=12,
                                    state="readonly",
                                    values=["Country", "State", "City"]))

    # Scrollable checkbox list of regions - repopulated when region type changes.
    list_lbl = ttk.Label(frm, text="Regions (check one or more)")
    list_lbl.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 2))
    row += 1
    holder = ttk.Frame(frm)
    holder.grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    canvas = tk.Canvas(holder, bg=SURFACE, highlightthickness=1,
                       highlightbackground=SURFACE2, width=300, height=200)
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
            ttk.Label(inner, text="Country-wide (no region needed)",
                      style="Muted.TLabel").pack(anchor="w", padx=6, pady=6)
            list_lbl.grid_remove()
            return
        list_lbl.grid()
        for canon, disp in opts:
            v = tk.BooleanVar(value=False)
            region_vars[canon] = v
            ttk.Checkbutton(inner, text=disp, variable=v).pack(
                anchor="w", padx=6)
        canvas.yview_moveto(0)

    region_type.trace_add("write", rebuild_regions)
    rebuild_regions()

    opt = ttk.Frame(frm)
    opt.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
    row += 1
    ttk.Label(opt, text="Sticky lifetime (min)").pack(side="left")
    ttk.Entry(opt, textvariable=lifetime, width=6).pack(side="left", padx=(6, 16))
    ttk.Label(opt, text="Count (total)").pack(side="left")
    ttk.Entry(opt, textvariable=count, width=8).pack(side="left", padx=(6, 0))

    ttk.Checkbutton(frm, text="Rotating (new IP per request, no sticky session)",
                    variable=rotating).grid(row=row, column=0, columnspan=2,
                                            sticky="w", pady=(6, 0))
    row += 1
    ttk.Checkbutton(frm, text="Append to existing list (instead of replacing)",
                    variable=append).grid(row=row, column=0, columnspan=2,
                                          sticky="w")
    row += 1

    def gen():
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
        lt = None
        raw = lifetime.get().strip()
        if raw and not rotating.get():
            try:
                lt = max(1, int(raw))
            except ValueError:
                lt = None
        lines, err = generate_resi_batch(provider.get(), rtype, regions, lt, n,
                                         rotating.get())
        if err:
            messagebox.showerror("Generate batch", err)
            return
        text = "\n".join(lines)
        if append.get():
            cur = text_widget.get("1.0", "end").rstrip("\n")
            text = (cur + "\n" + text) if cur else text
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", text)
        top.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
    ttk.Button(btns, text="Generate", style="Accent.TButton",
               command=gen).pack(side="left")
    ttk.Button(btns, text="Cancel", command=top.destroy).pack(side="left",
                                                              padx=8)
    center_over_parent(top, parent)
    top.grab_set()


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
        ttk.Label(form, text="Proxies (host:port:user:pass, one per line)").grid(
            row=0, column=0, sticky="w")
        self.proxy_text = tk.Text(form, width=50, height=8)
        style_text(self.proxy_text)
        self.proxy_text.grid(row=1, column=0, rowspan=4, sticky="nw",
                             padx=(0, 24))
        self.proxy_text.bind("<<Paste>>", self._on_paste_proxies)

        # Fall back to a valid provider if the saved one no longer exists
        # (e.g. a removed provider like the old "Spur" lingering in settings).
        _saved_prov = load_setting("quality_provider", "proxycheck.io")
        if _saved_prov not in QUALITY_PROVIDERS:
            _saved_prov = "proxycheck.io"
        self.provider = tk.StringVar(value=_saved_prov)
        ttk.Label(form, text="Reputation provider").grid(
            row=1, column=1, sticky="w")
        ttk.Combobox(form, textvariable=self.provider,
                     values=list(QUALITY_PROVIDERS.keys()), width=20,
                     state="readonly").grid(row=1, column=2, sticky="w", pady=3)
        ttk.Label(
            form,
            text="API keys live in the Settings tab. No key = free Spamhaus "
                 "+ latency only. Unique exit IPs are scored once (deduped).",
            style="Muted.TLabel").grid(row=2, column=1, columnspan=2, sticky="w")

        # Speed gate (two-stage funnel): filter on the NEUTRAL exit-IP-discovery
        # latency (proxy -> ipinfo.io/json, which we measure anyway) - so slow
        # proxies never reach the paid reputation API, and NO retailer is
        # contacted during scanning. The retailer test is your deliberate final
        # step on the vetted list (Proxy Tester tab), not the bulk scan.
        self.gate_on = tk.BooleanVar(value=False)
        gate_row = ttk.Frame(form)
        gate_row.grid(row=3, column=1, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(
            gate_row, text="Speed gate: only score proxies that resolve under",
            variable=self.gate_on).pack(side="left")
        self.gate_ms = tk.StringVar(value="2500")
        ttk.Entry(gate_row, textvariable=self.gate_ms, width=6).pack(
            side="left", padx=4)
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
        ttk.Label(btns, text="Filter Type / Trust from headers ▾",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))
        self.status_lbl = ttk.Label(btns, text="Idle", style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)
        self.sel_lbl = ttk.Label(btns, text="", style="Muted.TLabel")
        self.sel_lbl.pack(side="right")

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        layout = {
            "proxy":     (260, 150, True,  "w"),
            "exit_ip":   (150, 100, True,  "w"),
            "fraud":     (70,  50,  False, "center"),
            "type":      (130, 90,  True,  "w"),
            "flags":     (150, 90,  True,  "w"),
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
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _on_paste_proxies(self, _event=None):
        """Paste always appends to the END of the list (never mid-cursor) and
        leaves the caret on a fresh blank line, so you can immediately paste the
        next batch without it running onto the last proxy."""
        try:
            clip = self.proxy_text.clipboard_get()
        except tk.TclError:
            return "break"
        cur = self.proxy_text.get("1.0", "end-1c").rstrip("\n")
        parts = [p for p in (cur, clip.strip("\n")) if p]
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", "\n".join(parts) + "\n")
        self.proxy_text.mark_set("insert", "end-1c")
        self.proxy_text.see("end")
        return "break"

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
        proxies, bad = [], 0
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

        gate_ms = None
        if self.gate_on.get():
            try:
                gate_ms = max(1, int(self.gate_ms.get().strip()))
            except (TypeError, ValueError):
                gate_ms = 2500

        self.tree.delete(*self.tree.get_children())
        self._rows = []
        self.running = True
        self.stop_event.clear()
        self.run_btn.config(text="Stop", style="Stop.TButton",
                            command=self.on_stop)
        engine = provider if api_key else "no key (Spamhaus + latency)"
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
                "flags": "", "blacklist": "-", "ping": ms, "trust": None,
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
        try:
            # --- Stage 1: resolve exit IPs (neutral endpoint, free) ---
            discoveries = []
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(discover_exit_ip, p, DEFAULT_TIMEOUT,
                                    self.stop_event): p for p in proxies}
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
                                        f"Resolved {done}/{len(proxies)} "
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
            scores = {}
            if not self.stop_event.is_set():
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = {pool.submit(score_ip, ip, provider, api_key,
                                        DEFAULT_TIMEOUT): ip for ip in unique}
                    for fut in futs:
                        ip = futs[fut]
                        try:
                            scores[ip] = fut.result()
                        except Exception:
                            scores[ip] = {"blacklisted": None}

            for q in scores.values():
                if q.get("_error"):
                    err_ct += 1
                    provider_err = q["_error"]
            has_key = bool(api_key)
            for d in discoveries:
                if d.get("_slow"):
                    self.queue.put(self._slow_row(d, gate_ms))
                else:
                    self.queue.put(build_quality_row(
                        d, scores.get(d["exit_ip"], {}), has_key))
        finally:
            self.queue.put({"_done": True, "resolved": resolved,
                            "unique": unique_n, "provider_err": provider_err,
                            "err_ct": err_ct, "gated_out": gated_out})

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
        # Persistent summary so filtering never wipes the scored/dedupe counts.
        self._summary = ("Stopped" if stopped
                         else f"Done - {scored} scored{dedup}{gate_note}"
                              f"{err_note}")
        self._trust_buckets = set()       # a fresh run clears prior filters
        self._type_filter = set()
        self._render_rows()

    def _trust_tag(self, r):
        if r.get("status") != "OK" or r.get("trust") is None:
            return "bad"
        t = r["trust"]
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
        """Re-render applying the active Trust-range + Type filters, keeping the
        run summary (scored / unique / deduped) in the status."""
        rows = self._rows
        if self._trust_buckets:
            preds = [p for (lbl, p) in TRUST_BUCKETS
                     if lbl in self._trust_buckets]
            rows = [r for r in rows if any(p(r.get("trust")) for p in preds)]
        if self._type_filter:
            rows = [r for r in rows if r.get("type") in self._type_filter]
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
        self.tree.delete(*self.tree.get_children())
        self._item_full = {}
        for r in rows:
            self._insert_row(r)
        self._update_sel_count()
        filt = []
        if unique_only:
            filt.append("unique IPs")
        if self._trust_buckets:
            filt.append("trust=" + "/".join(
                lbl for (lbl, _) in TRUST_BUCKETS if lbl in self._trust_buckets))
        if self._type_filter:
            filt.append("type=" + "/".join(sorted(self._type_filter)))
        status = self._summary or f"Showing {len(rows)}"
        if filt:
            status += f"  |  showing {len(rows)} [{', '.join(filt)}]"
        self.status_lbl.config(text=status)

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
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._win, width=e.width))
        # Mousewheel only while the pointer is over this tab.
        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all(
            "<MouseWheel>", self._on_wheel))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all(
            "<MouseWheel>"))
        self._build()

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _build(self):
        host = self.inner
        r = 0
        ttk.Label(host,
                  text="Changes save automatically as you type - no need to "
                       "click anything.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=2,
                                             sticky="w", pady=(0, 14))
        r += 1
        ttk.Label(host, text="IP reputation API keys",
                  style="Header.TLabel").grid(row=r, column=0, columnspan=2,
                                              sticky="w", pady=(0, 4))
        r += 1
        ttk.Label(host,
                  text="Used by the IP Quality tab. Only the public exit IP is "
                       "ever sent to these - never your proxy credentials.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=2,
                                             sticky="w", pady=(0, 12))
        r += 1

        self.ipqs = tk.StringVar(value=load_setting("ipqs_api_key", ""))
        self.pcheck = tk.StringVar(value=load_setting("proxycheck_api_key", ""))
        self.ipinfo = tk.StringVar(value=load_setting("ipinfo_token", ""))
        self.workers = tk.StringVar(value=str(get_workers()))

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

        ttk.Separator(host, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=14)
        r += 1
        ttk.Label(host, text="Proxy provider credentials",
                  style="Header.TLabel").grid(row=r, column=0, columnspan=2,
                                              sticky="w", pady=(0, 4))
        r += 1
        ttk.Label(host,
                  text="One box per provider, as username:password. Oxylabs "
                       "Mobile fills the ASN Tester login; Residential / IPRoyal "
                       "feed 'Generate batch'.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=2,
                                             sticky="w", pady=(0, 8))
        r += 1
        self.oxy_mobile = tk.StringVar(
            value=provider_creds_display("oxylabs_mobile"))
        self.oxy_resi = tk.StringVar(value=provider_creds_display(
            "oxylabs_resi", ("oxylabs_resi_user", "oxylabs_resi_pass")))
        self.ipr = tk.StringVar(value=provider_creds_display(
            "iproyal", ("iproyal_user", "iproyal_pass")))

        def cred_row(label, var):
            nonlocal r
            ttk.Label(host, text=label).grid(row=r, column=0, sticky="w", pady=3)
            e = ttk.Entry(host, textvariable=var, width=46)
            e.grid(row=r, column=1, sticky="w", pady=3, padx=(10, 0))
            e.bind("<FocusOut>", lambda _e: self._persist(), add="+")
            r += 1

        cred_row("Oxylabs Mobile (username:password)", self.oxy_mobile)
        cred_row("Oxylabs Residential (username:password)", self.oxy_resi)
        cred_row("IPRoyal (username:password)", self.ipr)

        ttk.Separator(host, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=14)
        r += 1
        ttk.Label(host, text="Performance", style="Header.TLabel").grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
        r += 1
        ttk.Label(host, text="Concurrency (parallel workers, 1-100)").grid(
            row=r, column=0, sticky="w", pady=4)
        wkr = ttk.Entry(host, textvariable=self.workers, width=6)
        wkr.grid(row=r, column=1, sticky="w", pady=4, padx=(10, 0))
        wkr.bind("<FocusOut>", lambda _e: self._persist(), add="+")
        r += 1

        # Auto-save: any edit persists after a short debounce, so a forgotten
        # click on 'Save settings' can never silently drop a key again.
        for _v in (self.ipqs, self.pcheck, self.ipinfo, self.oxy_mobile,
                   self.oxy_resi, self.ipr, self.workers):
            _v.trace_add("write", self._schedule_autosave)
        ttk.Label(host,
                  text="Higher = faster on big lists (network-bound). Too high "
                       "may trip a provider's rate limit. 20-40 is a good range.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=2,
                                             sticky="w")
        r += 1

        ttk.Button(host, text="Save now", style="Accent.TButton",
                   command=self.on_save).grid(row=r, column=0, sticky="w",
                                              pady=(16, 4))
        self.status_lbl = ttk.Label(host, text="", style="Muted.TLabel")
        self.status_lbl.grid(row=r, column=1, sticky="w", pady=(16, 4))

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
        try:
            w = max(1, min(100, int(self.workers.get().strip())))
        except (TypeError, ValueError):
            w = DEFAULT_WORKERS
        save_setting("concurrency", w)
        if announce:
            self.status_lbl.config(text="Saved.")
        if self._on_saved:
            self._on_saved()

    def on_save(self):
        # Manual save also normalizes the worker count shown in the box.
        try:
            w = max(1, min(100, int(self.workers.get().strip())))
        except (TypeError, ValueError):
            w = DEFAULT_WORKERS
        self.workers.set(str(w))
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


def _fetch_latest_release():
    url = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={
        "User-Agent": "ProxyTester", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    tag = data.get("tag_name", "")
    assets = data.get("assets", [])
    # Prefer the onedir .zip (reliable, no runtime unpacking); fall back to a
    # legacy .exe if that's all a release carries.
    asset = next((a for a in assets
                  if a.get("name", "").lower().endswith(".zip")), None)
    if asset is None:
        asset = next((a for a in assets
                      if a.get("name", "").lower().endswith(".exe")), None)
    return tag, (asset or {}).get("browser_download_url")


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
    if messagebox.askyesno(
            "Update available",
            f"{tag} is available - you have v{APP_VERSION}.\n\n"
            "Download and install now?"):
        _download_and_apply(parent, dl, tag)


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


def main():
    if _signal_existing_instance():
        return  # another instance is already open - brought it to the front

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

    root.mainloop()


if __name__ == "__main__":
    main()
