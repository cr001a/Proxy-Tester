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

APP_VERSION = "3.16"                    # single source of truth (CI tags v<this>)
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
# IP quality / trust scoring
# --------------------------------------------------------------------------- #
# A proxy is only as good as the reputation of the IP it exits on. We measure
# that two ways: IPQualityScore (paid, best-in-class fraud/bot/proxy scoring)
# and Spamhaus ZEN (free DNS blocklist, no key). Both feed a single 0-100
# Trust score - higher is cleaner / more likely to pass anti-bot queues.
IPINFO_URL = "https://ipinfo.io/json"


def http_get_json(url, timeout=DEFAULT_TIMEOUT, extra_headers=None):
    """Direct (no-proxy) HTTPS GET returning parsed JSON, or None on any error."""
    try:
        headers = {"User-Agent": USER_AGENT}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers)
        opener = (urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=SSL_CTX)) if SSL_CTX
            else urllib.request.build_opener())
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


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


def spur_lookup(ip, token, timeout=DEFAULT_TIMEOUT):
    """Query Spur's Context API (api.spur.us) - the residential-proxy specialist.
    Auth is a `Token` header. Spur gives no 0-100 score, so we synthesize one
    from whether it detects anonymization (tunnels / client proxies / risks)."""
    data = http_get_json("https://api.spur.us/v2/context/" + quote(ip, safe=""),
                         timeout, extra_headers={"Token": token})
    if not isinstance(data, dict):
        return None
    infra = (data.get("infrastructure") or "").upper()
    tunnels = data.get("tunnels") if isinstance(data.get("tunnels"), list) else []
    risks = data.get("risks") if isinstance(data.get("risks"), list) else []
    client = data.get("client") if isinstance(data.get("client"), dict) else {}
    client_proxies = (client.get("proxies")
                      if isinstance(client.get("proxies"), list) else [])
    risk_txt = " ".join(str(r) for r in risks).upper()

    anon = bool(tunnels) or bool(client_proxies) or "TUNNEL" in risk_txt \
        or "PROXY" in risk_txt
    if anon:
        fraud = 90                       # Spur sees anonymization -> burnt
    elif "DATACENTER" in infra:
        fraud = 60
    else:
        fraud = 5                        # clean residential/mobile, no tunnel
    is_vpn = any(isinstance(t, dict) and str(t.get("type", "")).upper() == "VPN"
                 for t in tunnels)
    conn = infra.title() if infra else ("Proxy" if anon else "Residential")
    org = data.get("organization", "")
    if not org and isinstance(data.get("as"), dict):
        org = data["as"].get("organization", "")
    behaviours = " ".join(str(b) for b in (client.get("behaviors") or [])).upper()
    # The killer signal: which residential-proxy networks this IP belongs to,
    # plus any VPN service - shown in the Flags column so you see WHY it's burnt.
    services = data.get("services") if isinstance(data.get("services"),
                                                  list) else []
    extra = [str(p).replace("_PROXY", "").replace("_", " ").lower().strip()
             for p in client_proxies]
    extra += [str(s).lower() for s in services]
    return {
        "fraud_score": fraud,
        "connection_type": conn,        # Datacenter / Mobile / Residential
        "proxy": anon,
        "vpn": is_vpn,
        "tor": "TOR" in risk_txt or "TOR" in behaviours,
        "recent_abuse": anon,
        "bot_status": ("SCRAP" in risk_txt or "BOT" in risk_txt),
        "isp": org,
        "country": (data.get("location") or {}).get("country", ""),
        "flag_extra": list(dict.fromkeys(extra)),   # deduped, order-preserved
    }


# Supported IP-reputation providers. The key for each lives in settings.json
# (entered on the Settings tab), never in code.
QUALITY_PROVIDERS = {
    "proxycheck.io": ("proxycheck_api_key", proxycheck_lookup),
    "Spur": ("spur_api_token", spur_lookup),
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
    # Provider-supplied detail (e.g. Spur's named residential-proxy networks).
    flags += [f for f in (q.get("flag_extra") or []) if f and f not in flags]
    bl = q.get("blacklisted")
    fs = q.get("fraud_score")
    return {
        "proxy": display,
        "full": full,
        "exit_ip": disc["exit_ip"],
        "fraud": "" if fs is None else str(fs),
        "type": q.get("connection_type", "") or ("-" if has_key else "no key"),
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
        # Status/org stretch, are left-aligned, and have a minwidth so the
        # exact response and carrier org stay readable (can't be squeezed).
        layout = {
            "asn":     (90,  70,  False, "center"),
            "status":  (200, 150, True,  "w"),
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
        self.shuffle_btn = ttk.Button(btns, text="Shuffle list",
                                      command=self.on_shuffle)
        self.shuffle_btn.pack(side="left", padx=8)
        self.status_lbl = ttk.Label(btns, text="Idle", style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)

        self.tree = ttk.Treeview(self, columns=self.COLUMNS,
                                 show="headings", height=12)
        # (width, minwidth, stretch, anchor). Status stretches, is left-aligned,
        # and has a minwidth so the exact response (e.g. "502 exit node not
        # found") stays readable and can never be squeezed down to "5xx".
        layout = {
            "proxy":   (280, 150, True,  "w"),
            "status":  (200, 150, True,  "w"),
            "code":    (80,  60,  False, "center"),
            "median":  (90,  70,  False, "center"),
            "success": (110, 90,  False, "center"),
            "exit_ip": (140, 110, False, "center"),
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
        self._min_trust = None    # active min-trust filter
        self._type_filter = set() # active Type filter (empty = all)
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

        self.provider = tk.StringVar(value=load_setting("quality_provider",
                                                        "proxycheck.io"))
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

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 4))
        self.run_btn = ttk.Button(btns, text="Score", style="Accent.TButton",
                                  command=self.on_run)
        self.run_btn.pack(side="left")
        ttk.Button(btns, text="Copy selected",
                   command=self.on_copy_selected).pack(side="left", padx=8)
        ttk.Button(btns, text="Export CSV", command=self.on_export).pack(
            side="left", padx=(0, 8))
        ttk.Label(btns, text="Min trust").pack(side="left", padx=(8, 2))
        self.min_trust = tk.StringVar(value="")
        mt = ttk.Entry(btns, textvariable=self.min_trust, width=5)
        mt.pack(side="left")
        mt.bind("<Return>", lambda e: self._apply_filter())
        ttk.Button(btns, text="Filter", command=self._apply_filter).pack(
            side="left", padx=(4, 0))
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
        for col in self.COLUMNS:
            w, mw, st, anc = layout[col]
            # Clicking the Type header opens a multi-select filter; other
            # headers sort. (▾ hints the Type column is a filter dropdown.)
            if col == "type":
                self.tree.heading(col, text=self.HEADINGS[col] + " ▾",
                                  command=self._open_type_filter)
            else:
                self.tree.heading(col, text=self.HEADINGS[col],
                                  command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, minwidth=mw, stretch=st, anchor=anc)
        tag_tree(self.tree)
        enable_drag_select(self.tree)
        self.tree.bind("<<TreeviewSelect>>", self._update_sel_count)
        self.tree.bind("<Control-c>", lambda e: (self.on_copy_selected(), "break"))
        self.tree.bind("<Control-C>", lambda e: (self.on_copy_selected(), "break"))
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        vsb = ttk.Scrollbar(self.tree, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

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

        self.tree.delete(*self.tree.get_children())
        self._rows = []
        self.running = True
        self.stop_event.clear()
        self.run_btn.config(text="Stop", style="Stop.TButton",
                            command=self.on_stop)
        engine = provider if api_key else "no key (Spamhaus + latency)"
        self.status_lbl.config(
            text=f"Resolving exit IPs for {len(proxies)} proxy(ies) [{engine}]...")
        worker = threading.Thread(target=self._run_pool,
                                  args=(proxies, provider, api_key), daemon=True)
        worker.start()
        self.after(100, self._drain_queue)

    def on_stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.run_btn.config(state="disabled")
        self.status_lbl.config(text="Stopping...")

    def _run_pool(self, proxies, provider, api_key):
        """Phase 1: resolve each proxy's exit IP (concurrent). Phase 2: score
        each UNIQUE exit IP once (dedupe -> fewer paid lookups). Then map the
        score back onto every proxy that shares that exit IP."""
        workers = get_workers()
        resolved = unique_n = 0
        try:
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
                             "ping": None, "status": str(e)[:60]}
                    discoveries.append(d)
                    done += 1
                    if done % 25 == 0:
                        self.queue.put({"_status":
                                        f"Resolved {done}/{len(proxies)} "
                                        "exit IPs..."})

            unique = sorted({d["exit_ip"] for d in discoveries if d["exit_ip"]})
            unique_n = len(unique)
            resolved = sum(1 for d in discoveries if d["exit_ip"])
            self.queue.put({"_status": f"Scoring {unique_n} unique IP(s) from "
                                       f"{resolved} live proxies "
                                       f"({resolved - unique_n} deduped)..."})
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

            has_key = bool(api_key)
            for d in discoveries:
                self.queue.put(build_quality_row(
                    d, scores.get(d["exit_ip"], {}), has_key))
        finally:
            self.queue.put({"_done": True, "resolved": resolved,
                            "unique": unique_n})

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
        # Persistent summary so filtering never wipes the scored/dedupe counts.
        self._summary = "Stopped" if stopped else f"Done - {scored} scored{dedup}"
        self._min_trust = None            # a fresh run clears prior filters
        self._type_filter = set()
        self.min_trust.set("")
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

    def _apply_filter(self):
        """Apply the Min-trust threshold (blank = no trust filter)."""
        raw = self.min_trust.get().strip()
        try:
            self._min_trust = int(raw) if raw else None
        except ValueError:
            self._min_trust = None
        self._render_rows()

    def _render_rows(self):
        """Re-render the table applying the active Trust + Type filters, while
        keeping the run summary (scored / unique / deduped) in the status."""
        rows = self._rows
        if self._min_trust is not None:
            rows = [r for r in rows if isinstance(r.get("trust"), int)
                    and r["trust"] >= self._min_trust]
        if self._type_filter:
            rows = [r for r in rows if r.get("type") in self._type_filter]
        self.tree.delete(*self.tree.get_children())
        self._item_full = {}
        for r in rows:
            self._insert_row(r)
        self._update_sel_count()
        filt = []
        if self._min_trust is not None:
            filt.append(f"trust>={self._min_trust}")
        if self._type_filter:
            filt.append("type=" + "/".join(sorted(self._type_filter)))
        status = self._summary or f"Showing {len(rows)}"
        if filt:
            status += f"  |  showing {len(rows)} [{', '.join(filt)}]"
        self.status_lbl.config(text=status)

    def _open_type_filter(self):
        """Dropdown from the Type header: multi-select which connection types to
        show. Options are pulled from the actual results."""
        types = sorted({r.get("type", "") for r in self._rows
                        if r.get("status") == "OK" and r.get("type")})
        if not types:
            self.status_lbl.config(text="No results to filter yet - Score first.")
            return
        top = tk.Toplevel(self)
        top.title("Filter by Type")
        top.configure(bg=BASE)
        top.transient(self.winfo_toplevel())
        top.resizable(False, False)
        cur = self._type_filter
        cbvars = {}
        ttk.Label(top, text="Show types:", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        for i, t in enumerate(types):
            v = tk.BooleanVar(value=(t in cur) if cur else True)
            cbvars[t] = v
            ttk.Checkbutton(top, text=t, variable=v).grid(
                row=i + 1, column=0, sticky="w", padx=18, pady=1)
        btns = ttk.Frame(top)
        btns.grid(row=len(types) + 1, column=0, sticky="ew", padx=12,
                  pady=(10, 12))

        def apply_():
            sel = {t for t, v in cbvars.items() if v.get()}
            # all (or none) selected => no filter, show everything
            self._type_filter = (set() if not sel or len(sel) == len(types)
                                 else sel)
            self._render_rows()
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
        export_tree_csv(self.tree, self.COLUMNS,
                        [self.HEADINGS[c] for c in self.COLUMNS])


class SettingsTab(ttk.Frame):
    """Central place for API keys and performance. Keys are stored in
    settings.json in your config dir (never hard-coded)."""

    def __init__(self, master):
        super().__init__(master, padding=20)
        self._build()

    def _build(self):
        r = 0
        ttk.Label(self, text="IP reputation API keys",
                  style="Header.TLabel").grid(row=r, column=0, columnspan=2,
                                              sticky="w", pady=(0, 4))
        r += 1
        ttk.Label(self,
                  text="Used by the IP Quality tab. Only the public exit IP is "
                       "ever sent to these - never your proxy credentials.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=2,
                                             sticky="w", pady=(0, 12))
        r += 1

        self.ipqs = tk.StringVar(value=load_setting("ipqs_api_key", ""))
        self.pcheck = tk.StringVar(value=load_setting("proxycheck_api_key", ""))
        self.spur = tk.StringVar(value=load_setting("spur_api_token", ""))
        self.workers = tk.StringVar(value=str(get_workers()))

        def key_row(label, var):
            nonlocal r
            ttk.Label(self, text=label).grid(row=r, column=0, sticky="w", pady=4)
            e = ttk.Entry(self, textvariable=var, width=46, show="•")
            e.grid(row=r, column=1, sticky="w", pady=4, padx=(10, 0))
            reveal_on_focus(e)
            r += 1

        key_row("proxycheck.io key", self.pcheck)
        key_row("Spur token (Context API)", self.spur)
        key_row("IPQualityScore key", self.ipqs)

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=14)
        r += 1
        ttk.Label(self, text="Performance", style="Header.TLabel").grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
        r += 1
        ttk.Label(self, text="Concurrency (parallel workers, 1-100)").grid(
            row=r, column=0, sticky="w", pady=4)
        ttk.Entry(self, textvariable=self.workers, width=6).grid(
            row=r, column=1, sticky="w", pady=4, padx=(10, 0))
        r += 1
        ttk.Label(self,
                  text="Higher = faster on big lists (network-bound). Too high "
                       "may trip a provider's rate limit. 20-40 is a good range.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=2,
                                             sticky="w")
        r += 1

        ttk.Button(self, text="Save settings", style="Accent.TButton",
                   command=self.on_save).grid(row=r, column=0, sticky="w",
                                              pady=(16, 4))
        self.status_lbl = ttk.Label(self, text="", style="Muted.TLabel")
        self.status_lbl.grid(row=r, column=1, sticky="w", pady=(16, 4))

    def on_save(self):
        save_setting("ipqs_api_key", self.ipqs.get().strip())
        save_setting("proxycheck_api_key", self.pcheck.get().strip())
        save_setting("spur_api_token", self.spur.get().strip())
        try:
            w = max(1, min(100, int(self.workers.get().strip())))
        except (TypeError, ValueError):
            w = DEFAULT_WORKERS
        save_setting("concurrency", w)
        self.workers.set(str(w))
        self.status_lbl.config(text="Saved.")


class ProfileBar(ttk.Frame):
    """Top bar: pick / save / delete named credential profiles."""

    def __init__(self, master, store, tabs):
        super().__init__(master, padding=(14, 12, 14, 4))
        self.store = store
        self.tabs = tabs  # dict: key -> tab with get_state/set_state

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

        # Settings: a filled button (matching Save/Delete height) that drops a
        # small menu. Coloured so it's obviously a button, cog centred.
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

        ttk.Button(self, text="Delete", command=self.on_delete).pack(
            side="right", padx=(8, 0))
        ttk.Button(self, text="Save", style="Accent.TButton",
                   command=self.on_save).pack(side="right", padx=8)
        self.combo = ttk.Combobox(self, values=self.store.names(), width=26)
        self.combo.pack(side="right")
        self.combo.bind("<<ComboboxSelected>>", self.on_select)
        ttk.Label(self, text="Profile:").pack(side="right", padx=(0, 8))

    def _open_settings(self):
        btn = self._settings_btn
        self._settings_menu.tk_popup(btn.winfo_rootx(),
                                     btn.winfo_rooty() + btn.winfo_height())

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
            f'robocopy "{src}" "{install_dir}" /MIR /R:15 /W:1 '
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
    root.geometry("1100x880")  # roomy enough for the wide ASN selector
    root.minsize(820, 640)
    apply_theme(root)

    if LOGO_ICON_B64:
        try:
            root._icon_img = tk.PhotoImage(data=LOGO_ICON_B64)
            root.iconphoto(True, root._icon_img)
        except Exception:
            pass

    store = ProfileStore()

    notebook = ttk.Notebook(root)
    asn_tab = AsnTab(notebook)
    proxy_tab = ProxyTab(notebook)
    quality_tab = QualityTab(notebook)
    converter_tab = ConverterTab(notebook)
    settings_tab = SettingsTab(notebook)
    notebook.add(asn_tab, text="ASN Tester")
    notebook.add(proxy_tab, text="Proxy Tester")
    notebook.add(quality_tab, text="IP Quality")
    notebook.add(converter_tab, text="Converter")
    notebook.add(settings_tab, text="Settings")

    # The top Profile bar covers the testing-credential tabs. The IP Quality
    # tab is driven by the Settings tab (API keys), kept deliberately separate.
    bar = ProfileBar(root, store, {"asn": asn_tab, "proxy": proxy_tab})
    bar.pack(fill="x")
    notebook.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    # Keep a reference so the listening socket lives as long as the window.
    root._instance_server = _listen_for_second_instance(root)

    root.mainloop()


if __name__ == "__main__":
    main()
