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
   exit IPs are **deduped** so you only spend one lookup per IP. For the
   **IPinfo** provider, lookups use its **batch endpoint** (up to 1000 IPs per
   POST, several chunks run concurrently) — including under **fused** mode,
   which previously called IPinfo per-IP like every other provider and never
   batched at all. A 10k+ run now finishes IPinfo in a handful of requests
   instead of one connection per IP — the fix for the socket-exhaustion
   failures single-lookup mode hit at scale. Any IP a batch doesn't answer
   falls back to a single lookup, and the whole thing is a Settings toggle (on
   by default). **proxycheck.io is bulk-queried the same way** — its API takes
   up to 1,000 addresses in one POST, so a 17k-IP run is ~17 requests instead
   of 17,000 individually-paced GETs (which alone imposed a ~34s floor before
   any other work). Each address still counts as one query against your daily
   allowance — batching saves wall-clock, not quota. **Spamhaus** is checked
   free over DNS, but it refuses queries from public/cloud resolvers; the app
   now samples the first few lookups and, if the resolver is clearly being
   refused, skips the rest of the run and says so instead of burning a DNS
   round-trip per unique IP to collect nothing. An optional
   **Speed gate** runs a **two-stage funnel**. Stage 1 resolves each proxy's
   exit IP against the *neutral* `ipinfo.io/json` endpoint (**no retailer is
   ever contacted during scanning**) in a **single connection** — TCP →
   `CONNECT` tunnel → TLS → GET — with **staged timeouts**: a short budget on
   the connect/tunnel phase so dead proxies fail fast, a longer one on the
   request itself. (This replaced a two-pass design that opened a throwaway
   `CONNECT` probe, closed it, then redialled the same proxy from scratch; the
   probe only ever saved time on *dead* proxies, so on a mostly-live list —
   a real 20k run measured 92% alive — it was a wasted round trip on nearly
   every proxy.) When the **Speed gate** is on, its threshold also becomes each
   proxy's **total time budget** — anything slower is going to be filtered out
   of scoring anyway, so it's abandoned early rather than being allowed to hold
   a worker (and the run's wall clock) for the full read timeout. Results stream
   back in **completion order**, so one straggler can't hide results that have
   already finished behind it. The *paid* reputation lookup then runs
   **only on proxies that resolved under your millisecond threshold** — so a
   slow proxy never costs an API call. (The actual retailer latency test is your
   deliberate final step on the vetted list — use the Proxy Tester tab with the
   retailer as the test URL.) Both this tab and the Proxy Tester report **how
   long the run took and its rate** (e.g. `Done in 4m 07s, 812/s`) when finished.
   Results sort best-first; click any header to re-sort. A **Min trust** box
   (default **92**) shows only the healthy majority after a run — nothing is
   discarded, it's a display filter, so blank the box (or lower it) to reveal
   the poorer proxies too, stacking with the header Type/Trust filters. **Copy
   selected** proxies straight to the clipboard (full `host:port:user:pass`). A
   large **green count** ("N shown") sits next to the buttons so you always
   know how many proxies pass every active filter at a glance, without reading
   the full status line. API keys live on the **Settings** tab; concurrency is
   hard-coded for maximum throughput (nothing to tune).

   **proxycheck.io status handling.** Their API has four status values, and
   only two are real failures — `ok` and `warning` both mean the query
   succeeded (a `warning` just carries an advisory, e.g. nearing your daily
   quota or per-second limit); only `denied`/`error` are actual failures. This
   used to treat any non-`ok` status as a failure and silently drop the data —
   meaning an account anywhere near its daily quota had every lookup discarded
   and got disabled by the fused breaker after a handful of them, even though
   every one of those lookups had actually succeeded. A real failure now
   surfaces the vendor's own message (e.g. `proxycheck.io: denied - 100 queries
   exhausted...`) instead of a bare "failed (stopped)", and a `warning` is
   shown once per run so you know if you're approaching a limit.

   **Scoring detail (IPinfo).** Verified against IPinfo's own Batch Enrichment
   API docs: an exit resolving to a **government**-typed network is a real red
   flag (previously fell through to clean-Residential, which was wrong) —
   there's essentially no legitimate retail-shopper traffic from a `.mil`-type
   network, so a "residential" proxy exiting there is almost certainly a
   compromised host acting as an unauthorized relay. **Education** is flagged
   much more mildly — a university/dorm connection can be a real student's
   genuine home-like internet, so it's noted (the provider's "residential" pool
   includes non-consumer-ISP space, worth knowing) without being treated as
   risky as an actual VPN or government exit. An **anycast** IP is treated as a
   near-certain non-residential
   tell (anycast address space is never a genuine home connection) and floors
   Trust hard. **Satellite** ISPs (Starlink etc.) get their own Type instead of
   hiding inside generic Residential — legitimate, but operationally different
   (much higher/variable latency, coarse geolocation). A confirmed positive
   detection also carries **when IPinfo last saw it** (e.g. `seen 2026-03-24`),
   so a stale flag can be weighed differently from a fresh one.

   **Pool-overlap detection.** Because every exit IP is resolved anyway, the tab
   also checks whether *two different providers handed back the same exit IP* —
   the signature of two brands reselling one underlying pool (white-labeling).
   If it finds any, a warning bar appears above the results with the headline
   number, and **Details** opens a full breakdown: unique exits per provider,
   which pairs overlap and by how much (as a share of the smaller pool), and the
   list of shared IPs with a copy button. Rows whose exit IP is shared are
   flagged `N pools` in the **Flags** column. It costs no extra API calls and
   stays completely hidden when there's no overlap.

   Providers are normally identified by hostname, but resellers serve many
   different products from **one** hostname. To compare two SKUs from the same
   host, put a **group label** above each block — `# F-Oxylab`, `// Oxylab`, or
   `[Oxylab]`. Everything under a label is treated as that group, labels win
   over the hostname, and label lines aren't counted as proxies. This is how you
   check whether two products are really the same pool.
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
**Oxylabs Residential**, **IPRoyal**, **Bright Data**, **Proxy-Haus**,
**Rayobyte**, **PacketStream**, **F-Private** (Hell World's own pool), and
**ThuProxy** (a NetNut reseller). The dialog **remembers everything between
opens** — checked providers, each one's sticky lifetime, count, region type and
regions, Proxy-Haus ASNs, Fresh, Rotating, Append, plus the window's size and
position — saved whether you hit Generate, Cancel, or close it. On a first-ever
run nothing is pre-selected; you opt in to each provider once. Providers are laid out in **columns of five**, so
adding one widens the dialog instead of lengthening it. Each checked provider
gets **its own sticky-lifetime box** (with its max shown), and a **Set all to
max** button fills them all to their caps at once. The **sticky-lifetime cap is
hardcoded and enforced** — Oxylabs 1440 min (24 h), IPRoyal 59 min / 168 h,
Proxy-Haus 120 min, Rayobyte 60 min (always sticky — no rotating mode), Bright
Data inherent (~30 min, no token), PacketStream fixed at its own ~60 min max
(no token exists to lower it, so it gets no lifetime box), F-Private 120 min
(its token is in *seconds*, so minutes are converted for you). ThuProxy has no
duration token at all — its `sid` **is** the session and holds until you change
it — so it gets no lifetime box either. If any provider's
lifetime exceeds its cap it warns and generates nothing. Set **count per provider** and **location** once for the
whole batch. Proxy-Haus adds a **click-to-pick ASN menu** (choose any number of
carriers): it always emits **at least one proxy per selected ASN**, and when the
count exceeds the number of ASNs it **splits the count evenly across them**
(e.g. 5 ASNs / count 10 → 2 each; count 12 → 3,3,2,2,2). Lifetime accepts `30`,
`30m`, or `2h`. Proxy-Haus also exposes a **Fresh** toggle
(`-pool-experimental1`) — freshly-added, less-used US IPs — which works with or
without an ASN and sits with the ASN picker, shown only while Proxy-Haus is
checked. **Fresh is a different pool with a much longer sticky cap**: ticking it
raises Proxy-Haus from 120 min / 2 h to **3600 min / 60 h**, and the grey rule
text next to its lifetime box updates to match as you toggle it.

The **ASN Tester** tab also generates per-ASN proxies (static or rotating) for
the selected provider. Adding a provider is a small change in `RESI_PROVIDERS` /
`PROVIDERS` (`proxy_tester.py`).

### Saved credentials

Provider logins live on the **Settings** tab, one box per provider as
`username:password`:

- **Oxylabs Mobile** and **Proxy-Haus** — auto-fill the ASN Tester's
  Username/Password when their provider is selected.
- **Oxylabs Residential**, **IPRoyal**, **Bright Data**, **Proxy-Haus**,
  **Rayobyte**, **PacketStream**, **Hell World F-Private**, **ThuProxy** — feed the
  **Generate batch** dialog; a
  provider only appears there once its box is filled in.

Each generator provider has an **in generator** tick-box next to its credentials.
Untick it to hide that provider from **Generate batch** *without deleting the
credentials* — ticking it back restores it with nothing to re-type.

**Editing keys.** Every text field — including the masked API-key and
password boxes — supports **copy / cut / paste / select-all / undo / redo**
(`Ctrl`- and `Cmd`-based). tkinter doesn't give an `Entry` an undo stack at all,
and it flatly refuses to copy from a masked field, so the app drives the
clipboard itself; typing coalesces into sensible undo steps rather than one per
character.

Settings are saved to `%APPDATA%\ProxyTester\settings.json`. Credentials
(including passwords) are stored there in **plain text** on your own machine —
fine for local use, but don't sync that file anywhere public.

---

## macOS: a Dock icon

There's no prebuilt Mac app (CI only builds Windows), but `make_mac_app.sh`
wraps the source in a real `.app` bundle so it gets the logo as its icon and can
be pinned to the Dock:

```
./make_mac_app.sh
```

It uses only tools that ship with macOS (`sips`, `iconutil`), builds
`ProxyTester.app` next to the source, and needs no `pip install`. Drag the
result to the Dock (or to **Applications**) and launch it like any other app.

The bundle **doesn't copy the code** — it launches `proxy_tester.py` from this
folder. Re-run the script only if the logo changes or you want the bundle's
version string refreshed. Keep the `.app` inside this folder if you can: it
looks for the source next to itself first, and falls back to the path it was
built at, so an `.app` moved to `/Applications` keeps working as long as the
source folder stays put.

### Updating on macOS — no Terminal

Two automatic paths, neither involving a copied command:

- **Opening the app updates it.** The launcher runs `git pull --ff-only` before
  starting Python, so launching from the Dock always runs the current version.
- **"Update & restart"** in ⚙ ▸ *Check for updates* pulls and relaunches in
  place while the app is already open.

Both use `--ff-only`, which **refuses** rather than merging — local edits and a
diverged branch can never be silently overwritten by an update. When a pull is
refused the app says why and falls back to handing over the command.

The launch-time pull is bounded by an 8-second watchdog, so being offline costs
a few seconds of startup rather than hanging, and the app then runs the code it
already has. Set `PROXYTESTER_NO_AUTOPULL=1` to disable the launch-time pull.

> Re-run `./make_mac_app.sh` once to pick this up — the auto-update lives in the
> bundle's launcher, so an `.app` built before this change still needs a manual
> `git pull` that one last time.

### Which Python the launcher uses

macOS Macs routinely have several `python3` binaries, and **not all of them have
tkinter** — Homebrew's ships without it unless you also `brew install
python-tk`. The launcher therefore **probes candidates and picks the first one
that can actually `import tkinter`**, rather than taking whatever is first on
`PATH` and giving up if that one can't.

Preference order: the python.org framework build (it bundles **Tk 8.6**), then
Homebrew, then `/usr/local/bin`, then `PATH`, and Apple's `/usr/bin/python3`
last — that one links the **system Tk 8.5**, which renders a blank window on
some macOS versions, so it's a working-but-ugly fallback rather than a first
choice.

If nothing on the machine has tkinter, the dialog **lists every interpreter it
tried** so you can see what's installed, and points at the two fixes (python.org
installer, or `brew install python-tk`).

If `python3` can't be found at all, the launcher says so in a dialog instead of
failing silently.

### The blank white window on Apple's Python

`/usr/bin/python3` links **Tcl/Tk 8.5.9**, a build from around 2010 whose Aqua
port misses the initial damage event on modern macOS: the window maps but never
paints, so you get a white rectangle. Dragging the window's corner has always
fixed it, because a real resize is what makes the window server send the expose
event the redraw is waiting on.

The app now does that resize itself — one pixel out and back, retried a few
times as the window settles, plus a repaint when you switch tabs. Note that
`update_idletasks()`, `lift()` and `deiconify()` do **not** work here: they
flush Tk's own queue, but the missing event is on the macOS side.

This only runs on macOS with Tk older than 8.6. Everywhere else it's off —
forcing redraws that aren't needed just makes the window flicker on open.

It's a workaround, not a cure. Apple's Tk 8.5 is fifteen years old and has other
rough edges. If you can install Python from python.org (Tk 8.6), do — the app
prefers it automatically once it's there.

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

**Landed on** works with **any** test URL. Only `ipinfo.io/json` returns an
`org` field, so when you point the test at a retailer the carrier is resolved
with one extra `ipinfo.io/json` call through the *same sticky session* — made
only until that ASN has an answer (at most one extra request per ASN, and none
at all on the default URL). A `4xx` from the target still counts as "the exit
connected", so a PerimeterX `403` on Walmart still tells you which carrier you
landed on.

## Tab 2: Proxy Tester

Paste proxies one per line as `host:port:user:pass` (or `host:port` for no
auth), then pick a **Test mode** — cheapest first:

- **Liveness (fast)** — the bare minimum. Opens one HTTP `CONNECT` tunnel per
  proxy to a neutral host and times the round-trip to `200 Connection
  established` — no TLS-to-target, no GET, no body. Runs up to ~1,200 wide on a
  short connect timeout, so a 200k list finishes in minutes. It proves the
  tunnel opens, *not* that egress works or what the exit IP is. **There is no
  exit IP to report in this mode, so the Exit IP / Provider / Location columns
  are hidden** rather than left blank — three empty columns read as a broken
  run, not a deliberate trade-off. The Test URL is ignored.
- **Exit IP + geo (fast)** — ***the default, and the one to reach for.*** One
  connection does `TCP → CONNECT → TLS → GET → body` with **staged timeouts**
  (short for the tunnel, longer for the request), returning the **exit IP,
  provider/ASN, location and latency**. This is the same single-pass resolver
  IP Quality uses, and it runs at the same ~1,200 concurrency as connect-only —
  the extra cost is a TLS handshake and one small GET on a tunnel that is
  already open. The provider and location come out of the *same response body*
  the exit-IP lookup already paid for, so they are free. The Test URL is
  ignored.
- **Full (custom URL)** — the `urllib` path: a real `GET` to your Test URL,
  repeated once per run, redialling each time with no staged timeouts. The
  slowest by a wide margin. Use it to test a *specific URL*, not to sweep a
  list.

Results table: `Proxy | Status | HTTP code | Median ms | Success (n/N) |
Exit IP | Provider / ASN | Location`.

This tab is a **plain connectivity/latency tester** — it reports reachability,
speed, and HTTP status only. No site-specific bot-protection scoring.

**Dedupe** removes duplicate lines from the paste box, keeping the first of each
and the original order. It matches on the full `host:port:user:pass` (password
included), so proxies that differ only by a session token count as distinct
sessions and are kept; unparseable lines are never dropped.

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
- Tests run on a background thread so the GUI never freezes; results are
  marshalled back to the table via a thread-safe queue. Concurrency is **tuned
  for maximum throughput and hard-coded** — no knobs to get wrong: the
  connect-only liveness sweep runs up to ~1,200 connections at once, the
  full/exit-IP path 800, and reputation lookups 400.
- **Built for lists in the hundreds of thousands.** Memory stays flat as the
  list grows, which is what makes a 400k run survivable:
  - Work is handed to a **fixed pool of threads pulling from a shared
    iterator**, not one `Future` per proxy. A `Future` carries its own
    `threading.Condition` (a lock plus a waiter deque) and measures ~1.6 KB, so
    `submit()`-per-item allocated **639 MB of bookkeeping on a 400k list before
    a single socket opened** — and the two-stage IP Quality funnel paid that
    bill twice. Measured at 200k items: **358 MB → 7.8 MB, a 46× reduction.**
  - Stage-1 records are **drained into result rows** rather than kept alongside
    them, and the reputation-score map is released once rows are built.
  - Worker threads get a **512 KB stack** instead of the 8 MB platform default —
    1,200 threads reserved ~9.4 GB of address space otherwise.
  - Progress updates **scale with list size** (~400 per run, however big).
    A fixed "every 200" fired 2,000 times on 400k, and the live counter behind
    it rescanned the whole result list each time — O(n²), hundreds of millions
    of lookups, all while holding the lock every worker needed.
  - End to end, a 400k-proxy scoring run drops from **~1.83 GB of Python heap
    to ~429 MB (4.3× less)**, before counting the Tk saving below.
- **Results tables are capped at 20,000 painted rows.** A `ttk.Treeview` keeps
  every row as Tcl objects, far heavier than the Python dict behind it, and a
  table 400,000 rows long is unreadable anyway. **Nothing is lost:** rows are
  sorted best-first, the full set stays in memory, and *Cull dead*, the speed
  filter, the counters and **Export CSV all operate on every result**, not just
  the painted ones. The status line says so whenever the table is showing less
  than the run produced.
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
- **Copy proxies** is the primary action on IP Quality, because what the list
  is *for* is feeding proxies into something else. With rows highlighted it
  copies those; with nothing highlighted it copies **every proxy that passed
  the filters** — including rows past the 20,000-row display cap, and it says
  so in the status line when the count copied exceeds the count on screen.
  (Copying from the visible table instead would hand back a short list that
  looks entirely correct until it's already loaded somewhere else.) Full CSV
  with every column is still there, on the table's **right-click menu**.
- **Export CSV** on the other tabs writes the current results to a `.csv`. With
  rows highlighted it exports just those; with nothing highlighted it exports
  every row that passed the filters.
- **Copying:** `Ctrl+C` / `Ctrl+A` and `Cmd+C` / `Cmd+A` both work on every
  results table and the ASN catalog — **both modifiers are bound**, because on
  a Mac the shortcut is `Cmd`, which Tk reports as a different modifier that no
  `Control` binding ever sees. Clicking a table also claims keyboard focus, or
  the keystroke would go nowhere. There's a **right-click menu** with *Copy
  selected* / *Select all* as well, which is what covers a Mac keyboard driving
  a Windows box over RDP — there `Cmd` isn't delivered as `Ctrl` at all, so no
  binding on either side can catch it. Right-clicking a row outside the current
  selection selects it; right-clicking inside a multi-row selection keeps the
  whole selection. ASN results copy as tab-separated rows (paste-ready for a
  spreadsheet); proxy tables copy full `host:port:user:pass`.
