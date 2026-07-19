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

1. **ASN Tester** — targets specific carrier ASNs and reports which carrier you
   actually landed on. Pick a **Provider** (Oxylabs mobile or Proxy-Haus); the
   provider's saved login and its supported ASN set load automatically
   (Proxy-Haus restricts to AT&T / Comcast / Cox / T-Mobile / Verizon). A
   **target picker** lets you point the test at a retailer (Walmart, Target, …)
   instead of `ipinfo.io/json`, to see which ASNs' IPs reach the site.
2. **Proxy Tester (general)** — plain reachability + latency testing for any
   list of proxies against any URL.
3. **IP Quality** — scores each proxy's exit-IP reputation into a single
   **Trust** score. Pick a **provider** —
   [proxycheck.io](https://proxycheck.io/) (cheap, high daily volume),
   [IPinfo](https://ipinfo.io/) (neutral IP-data vendor; the **Max** plan adds
   residential-proxy detection + carrier/mobile), or
   [IPQualityScore](https://www.ipqualityscore.com/) — for fraud/risk score,
   connection type (residential · mobile · datacenter · residential-proxy) and
   abuse/bot/VPN/Tor flags, plus a free **Spamhaus** blocklist check (no key)
   and latency. The Spamhaus result is broken out by sublist — **XBL**
   (compromised/botnet host, a real dirty-IP signal, heavily penalized),
   **SBL** (spam source, penalized), and **PBL** (dynamic/residential policy
   range, which describes almost every consumer IP and is only lightly
   penalized) — and any listing keeps a row out of the green Trust band. Unique
   exit IPs are **deduped** so you only spend one lookup per IP. An optional
   **Speed gate** runs a **two-stage funnel**: exit-IP resolution already times
   each proxy against the *neutral* `ipinfo.io/json` endpoint (**no retailer is
   ever contacted during scanning**), and the *paid* reputation lookup runs
   **only on proxies that resolved under your millisecond threshold** — so a
   slow proxy never costs an API call. (The actual retailer latency test is your
   deliberate final step on the vetted list — use the Proxy Tester tab with the
   retailer as the test URL.) Results sort best-first; click any header to re-sort, filter by **min
   trust**, and **copy selected** proxies straight to the clipboard (full
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

**Custom ASNs.** On the **ASN Tester** tab, paste any ASN number(s) into the
custom-ASN box (one per line or comma-separated) and click **Look up & add to
list**. Each is looked up against public registries (BGPView for the provider
name, PeeringDB for the network type, RIPEstat as a fallback) and pinned into
the ASN list above with an auto-detected provider name and type — shown even
under **Strict only**. No API key needed; pinned ASNs persist in
`settings.json`. The status line reports a summary like `2/5 added,
3 duplicate`.

### Generate batch (residential)

**Generate batch** (Proxy Tester / IP Quality tabs) builds sticky or rotating
residential proxies for **one or more providers at once** —
**Oxylabs Residential**, **IPRoyal**, **Bright Data**, **Proxy-Haus**, and
**Rayobyte**. Check
the providers you want; each checked provider gets **its own sticky-lifetime
box** (with its max shown), and a **Set all to max** button fills them all to
their caps at once. The **sticky-lifetime cap is hardcoded and enforced** —
Oxylabs 1440 min (24 h), IPRoyal 59 min / 168 h, Proxy-Haus 120 min, Rayobyte
60 min (always sticky — no rotating mode), Bright Data inherent (~30 min, no
token). If any provider's lifetime exceeds its cap it warns
and generates nothing. Set **count per provider** and **location** once for the
whole batch. Proxy-Haus adds a **click-to-pick ASN menu** (choose any number of
carriers): it always emits **at least one proxy per selected ASN**, and when the
count exceeds the number of ASNs it **splits the count evenly across them**
(e.g. 5 ASNs / count 10 → 2 each; count 12 → 3,3,2,2,2). Lifetime accepts `30`,
`30m`, or `2h`.

The **ASN Tester** tab also generates per-ASN proxies (static or rotating) for
the selected provider. Adding a provider is a small change in `RESI_PROVIDERS` /
`PROVIDERS` (`proxy_tester.py`).

### Saved credentials

Provider logins live on the **Settings** tab, one box per provider as
`username:password`:

- **Oxylabs Mobile** and **Proxy-Haus** — auto-fill the ASN Tester's
  Username/Password when their provider is selected.
- **Oxylabs Residential**, **IPRoyal**, **Bright Data**, **Proxy-Haus** — feed
  the **Generate batch** dialog; a provider only appears there once its box is
  filled in.

Settings are saved to `%APPDATA%\ProxyTester\settings.json`. Credentials
(including passwords) are stored there in **plain text** on your own machine —
fine for local use, but don't sync that file anywhere public.

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

**Site ping.** The Proxy Tester tab also has a **Site ping** control that
measures latency to a site's edge — pick a preset retailer (Walmart, Target,
Best Buy, Nike, Foot Locker, Adidas, Amazon, GameStop, Pokémon Center, Costco,
Newegg, Shopify), **All presets** to compare them all, or **Custom (Test URL)**
to ping whatever host is in the Test URL box. By default it's a raw TCP-connect
round-trip from *your* machine (not an HTTP request), so bot-protection `403`s
never skew the number — you get clean min / median / max latency to the edge.

Tick **through proxies (PX-safe CONNECT)** to instead ping the chosen site
**through every proxy in the list**. Each proxy opens an HTTP `CONNECT` tunnel
to the retailer edge — the exact transport handshake that begins every real
HTTPS session through that proxy — and the round-trip to `200 Connection
established` is timed. **No HTTP request is ever sent**, so PerimeterX / Akamai
never engage and no IPs get touched: it's a fast, safe per-proxy latency screen
against the actual target. The `HTTP code` column shows each proxy's CONNECT
status (`200` reachable, `407` auth, `502`/`504` upstream). Pick a single site
(not *All presets*) for this mode. Results append to the table prefixed with
`PING`. Click any column header to sort.

---

## Notes

- Requests use `urllib.request` with a `ProxyHandler` (standard library).
- Tests run on a background thread with a `ThreadPoolExecutor` so the GUI never
  freezes; results are marshalled back to the table via a thread-safe queue.
  Worker count comes from **Settings ▸ Concurrency** (default 40); the Proxy
  Tester floors it at 40 for large lists so a run isn't throttled by a low
  saved value. Raise it for more parallelism.
- **Fail-fast:** on the Proxy Tester tab, a proxy whose first request fails at
  the connection level (timeout / refused / tunnel failure) is marked dead
  immediately instead of retrying every run — so dead proxies no longer hold a
  worker for `runs × timeout` seconds. A proxy that gets an HTTP response (even
  a `403`) reached the target and is still tested every run.
- A live **counter** on the Proxy Tester tab shows progress as results stream
  in — e.g. `Tested 137/223 (61%) - 130 live, 7 dead`.
- **Median** latency is reported (not mean) so one slow sample doesn't skew the
  numbers.
- Per-request timeout defaults to 15s.
- A dead proxy or ASN shows a status in its own row and never blocks the others
  or crashes the app.
- **Export CSV** on each tab writes the current results table to a `.csv`.
