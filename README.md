# ProxyTester

*Made by codyrandolph.*

© 2026 Cody Randolph. **Noncommercial use only** — licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE). You may view, use, and modify
this for personal/noncommercial purposes, but **commercial use or resale is not
permitted** without the author's written permission.

A barebones Windows GUI tool for testing proxies. Written in Python with the
**standard library only** (tkinter) so the packaged `.exe` has zero external
runtime dependencies and never shells out to `curl`.

Four tabs:

1. **ASN Tester (Oxylabs mobile)** — targets specific carrier ASNs and reports
   which carrier you actually landed on.
2. **Proxy Tester (general)** — plain reachability + latency testing for any
   list of proxies against any URL.
3. **IP Quality** — scores each proxy's exit-IP reputation into a single
   **Trust** score. Pick a **provider** —
   [proxycheck.io](https://proxycheck.io/) (cheap, high daily volume) or
   [IPQualityScore](https://www.ipqualityscore.com/) — for fraud/risk score,
   connection type (residential · mobile · datacenter) and abuse/bot/VPN/Tor
   flags, plus a free **Spamhaus** blocklist check (no key) and latency. Unique
   exit IPs are **deduped** so you only spend one lookup per IP. Results sort
   best-first; click any header to re-sort, filter by **min trust**, and
   **copy selected** proxies straight to the clipboard (full
   `host:port:user:pass`). API keys and worker concurrency live on the
   **Settings** tab.
4. **Converter** — paste any provider proxy format (full URLs, Python snippets,
   `user:pass@host:port`, `host,port,user,pass`) and get copy-ready
   `host:port:user:pass` lines.

Features: a classified **ASN catalog** you filter by type
(Mobile / Residential / Business / Datacenter, plus a "Strict only" toggle that
hides dual-use ISPs) and search; a **Provider** dropdown (starts with Oxylabs)
that applies the provider's username rules for you; **Generate** proxies from
your run results (static or rotating, N per ASN, with shuffle); a **Stop**
button; dark purple theme; saved credential **profiles**; password reveal on
focus; per-tab CSV export; and colour-coded result statuses.

### ASN types

Each catalog ASN is tagged mobile / residential / business / datacenter
(researched via ipinfo / PeeringDB / CAIDA). **Strict only** (on by default)
shows just pure consumer-eyeball networks and hides dual-use ISPs that also
carry business/transit (e.g. AT&T 7018, Lumen 209, Starlink 14593). Business
and datacenter ASNs are off by default since mobile pools won't contain them.

### Generate rotating proxies

On the ASN Tester tab, pick a **Provider**, enter your username/password, list
the ASNs you want (one per line), and click **Generate proxies**. You get one
**rotating** proxy per ASN (new IP each request, US carrier via the ASN) as
copy-ready `host:port:user:pass`, e.g.:

```
pr.oxylabs.io:7777:customer-USERNAME-ASN-21928:PASSWORD
```

Adding a new provider later is a one-function change in `PROVIDERS`
(`proxy_tester.py`) — tell me the provider's username format and I'll wire it in
as another dropdown option.

### Profiles

Type a name in the **Profile** box (top bar) and click **Save** to store the
current inputs of both testing tabs; pick it from the dropdown next launch to
reload everything. Profiles are saved to `%APPDATA%\ProxyTester\profiles.json`.
Note: credentials (including passwords) are stored there in **plain text** on
your own machine — fine for local use, but don't sync that file anywhere public.

---

## Running from source

Requires Python 3.8+ (tkinter ships with the standard Windows/macOS installers;
on Linux install `python3-tk`).

```
python proxy_tester.py
```

No `pip install` needed to run — everything is standard library.

---

## Building the standalone Windows app

PyInstaller is the only third-party package required, and only for building.
The app is built as a **onedir** bundle — a folder containing `ProxyTester.exe`
plus an `_internal/` folder with the bundled Python runtime. This is
deliberately *not* a single `.exe`: onedir doesn't unpack DLLs to a temp folder
at every launch, which is what made in-app self-updates unreliable (a
freshly-swapped one-file exe races antivirus while it unpacks and can fail with
*"Failed to load Python DLL"*). onedir has none of that.

```
pip install pyinstaller
pyinstaller --onedir --windowed --name ProxyTester proxy_tester.py
```

The result is the `dist/ProxyTester/` folder. It is fully self-contained: copy
the whole folder to a Windows machine **with no Python installed** and
double-click `ProxyTester.exe` inside it.

> PyInstaller does not cross-compile. A Windows build must be made on Windows.
> This repo includes a GitHub Actions workflow
> (`.github/workflows/build-windows.yml`) that builds the app on a
> `windows-latest` runner, zips the folder, and uploads
> `ProxyTester-windows.zip` — so you can get a working build without owning a
> Windows machine.

### Getting the app from GitHub Actions / Releases

1. Open the latest **Build Windows EXE** run in the **Actions** tab, or the
   latest **Release**.
2. Download **ProxyTester-windows.zip**.
3. Extract it anywhere and run **ProxyTester.exe** from inside the extracted
   `ProxyTester` folder.

Pushing to `main` publishes a Release automatically, tagged `v<APP_VERSION>`.

### Updating

Use **⚙ → Check for updates** inside the app. It downloads the latest
`ProxyTester-windows.zip`, unpacks it, swaps the files in your install folder,
and relaunches — no manual steps. (Updating from an old single-`.exe` build to a
onedir build is a one-time manual download of the zip; every update after that
is in-app.)

---

## Tab 1: ASN Tester

| Field         | Default               |
|---------------|-----------------------|
| Host          | `pr.oxylabs.io`       |
| Port          | `7777`                |
| Username      | `customer-XXXXX_xxxxx`|
| Password      | (yours)               |
| ASNs          | one per line          |
| Runs per ASN  | `5`                   |
| Test URL      | `https://ipinfo.io/json` |

For each ASN the proxy username is built as
`{username}-ASN-{asn}-sessid-{random}` and the request goes through
`http://{user}:{pass}@{host}:{port}`. Each ASN is tested N times; latency is
recorded per run and the `org` field is parsed from the JSON response so you can
see the carrier you landed on.

**Status mapping**

| Condition                 | Status             |
|---------------------------|--------------------|
| HTTP 403                  | `restricted (KYC)` |
| HTTP 502                  | `empty pool`       |
| connection timeout/reset  | `unavailable`      |
| success                   | `OK`               |

Results table: `ASN | Status | Median ms | Min ms | Max ms | Success (n/N) |
Landed on (org)`. OK rows are sorted first, by ascending median latency.

## Tab 2: Proxy Tester

Paste proxies one per line as `host:port:user:pass` (or `host:port` for no
auth). Set any test URL. Each proxy is tested N times.

Results table: `Proxy | Status | HTTP code | Median ms | Success (n/N) |
Exit IP`. The exit IP is parsed from the `ip` field if the response is JSON.

This tab is a **plain connectivity/latency tester** — it reports reachability,
speed, and HTTP status only. No site-specific bot-protection scoring.

---

## Notes

- Requests use `urllib.request` with a `ProxyHandler` (standard library).
- Tests run on a background thread with a `ThreadPoolExecutor` (max 6 workers)
  so the GUI never freezes; results are marshalled back to the table via a
  thread-safe queue.
- **Median** latency is reported (not mean) so one slow sample doesn't skew the
  numbers.
- Per-request timeout defaults to 15s.
- A dead proxy or ASN shows a status in its own row and never blocks the others
  or crashes the app.
- **Export CSV** on each tab writes the current results table to a `.csv`.
