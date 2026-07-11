# ProxyTester

*Made by codyrandolph.*

A barebones Windows GUI tool for testing proxies. Written in Python with the
**standard library only** (tkinter) so the packaged `.exe` has zero external
runtime dependencies and never shells out to `curl`.

Three tabs:

1. **ASN Tester (Oxylabs mobile)** — targets specific carrier ASNs and reports
   which carrier you actually landed on.
2. **Proxy Tester (general)** — plain reachability + latency testing for any
   list of proxies against any URL.
3. **Converter** — paste any provider proxy format (full URLs, Python snippets,
   `user:pass@host:port`) and get copy-ready `host:port:user:pass` lines.

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

## Building the standalone Windows .exe

PyInstaller is the only third-party package required, and only for building.

```
pip install pyinstaller
pyinstaller --onefile --windowed --name ProxyTester proxy_tester.py
```

The result is `dist/ProxyTester.exe`. It is fully self-contained: copy it to a
Windows machine **with no Python installed** and double-click it.

> PyInstaller does not cross-compile. A Windows `.exe` must be built on Windows.
> This repo includes a GitHub Actions workflow
> (`.github/workflows/build-windows.yml`) that builds the `.exe` on a
> `windows-latest` runner and uploads it as a downloadable artifact — so you can
> get a working `.exe` without owning a Windows machine.

### Getting the .exe from GitHub Actions

1. Push this branch (already done) or open the **Actions** tab.
2. Open the latest **Build Windows EXE** run.
3. Download the **ProxyTester-windows** artifact — it contains `ProxyTester.exe`.

Tag a commit `v1.0` (etc.) to also publish the `.exe` on a GitHub Release.

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
