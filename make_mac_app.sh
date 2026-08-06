#!/bin/bash
# Build ProxyTester.app - a small macOS bundle that wraps the source in this
# folder, so the app gets a real Dock icon and can be pinned like any other app.
#
# It does NOT copy the code: the bundle just launches proxy_tester.py from here,
# so `git pull` updates the app with no rebuild. Re-run this only if the logo or
# the version changes.
#
# It also drops a shortcut on the Desktop so the app is reachable without
# digging through Finder. Pass --no-desktop-icon (or set
# PROXYTESTER_NO_DESKTOP_ICON=1) to skip that.
#
# Uses nothing but tools that ship with macOS (sips, iconutil, osascript).
set -e
cd "$(dirname "$0")"
REPO="$PWD"
APP="$REPO/ProxyTester.app"

DESKTOP_ICON=1
[ -z "$PROXYTESTER_NO_DESKTOP_ICON" ] || DESKTOP_ICON=0
for arg in "$@"; do
    case "$arg" in
        --no-desktop-icon) DESKTOP_ICON=0 ;;
        -h|--help)
            echo "usage: ./make_mac_app.sh [--no-desktop-icon]"
            echo "  Builds ProxyTester.app here and puts a shortcut to it on the Desktop."
            exit 0 ;;
        *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
    esac
done

if ! command -v sips >/dev/null 2>&1 || ! command -v iconutil >/dev/null 2>&1; then
    echo "This builds a macOS app bundle and needs sips/iconutil (macOS only)."
    exit 1
fi
[ -f "$REPO/proxy_tester.py" ] || { echo "proxy_tester.py not found here."; exit 1; }
[ -f "$REPO/logo.png" ]        || { echo "logo.png not found here."; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- icon -------------------------------------------------------------------
# macOS icons must be square; logo.png isn't, so centre-crop to its shorter side
# first. Cropping keeps the circle round - resizing to a square would squash it.
W="$(sips -g pixelWidth  logo.png | awk '/pixelWidth:/  {print $2}')"
H="$(sips -g pixelHeight logo.png | awk '/pixelHeight:/ {print $2}')"
SIDE=$(( W < H ? W : H ))
sips -c "$SIDE" "$SIDE" logo.png --out "$TMP/square.png" >/dev/null

ICONSET="$TMP/ProxyTester.iconset"
mkdir -p "$ICONSET"
for SZ in 16 32 128 256 512; do
    sips -z "$SZ" "$SZ" "$TMP/square.png" \
         --out "$ICONSET/icon_${SZ}x${SZ}.png" >/dev/null
    sips -z "$((SZ * 2))" "$((SZ * 2))" "$TMP/square.png" \
         --out "$ICONSET/icon_${SZ}x${SZ}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$TMP/ProxyTester.icns"

# --- bundle -----------------------------------------------------------------
VERSION="$(python3 -c "import re,io;print(re.search(r'APP_VERSION\s*=\s*\"([^\"]+)\"',io.open('proxy_tester.py',encoding='utf-8').read()).group(1))")"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$TMP/ProxyTester.icns" "$APP/Contents/Resources/ProxyTester.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>                <string>ProxyTester</string>
    <key>CFBundleDisplayName</key>         <string>ProxyTester</string>
    <key>CFBundleIdentifier</key>          <string>io.github.cr001a.proxytester</string>
    <key>CFBundleVersion</key>             <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>  <string>${VERSION}</string>
    <key>CFBundleExecutable</key>          <string>ProxyTester</string>
    <key>CFBundleIconFile</key>            <string>ProxyTester</string>
    <key>CFBundlePackageType</key>         <string>APPL</string>
    <key>NSHighResolutionCapable</key>     <true/>
    <key>LSMinimumSystemVersion</key>      <string>10.13</string>
</dict>
</plist>
PLIST

# The launcher prefers its own enclosing folder, so moving the whole repo keeps
# working; the baked-in path is the fallback for an .app dragged elsewhere.
cat > "$APP/Contents/MacOS/ProxyTester" <<LAUNCHER
#!/bin/bash
# A GUI launch gets a bare PATH, so Homebrew's and python.org's python3 aren't
# on it - add both before looking. git lives in /usr/bin, already on PATH.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:\$PATH"

# Tell the app which bundle launched it, so its "Update & restart" button can
# relaunch through the bundle and keep the Dock icon instead of spawning a
# bare python process.
export PROXYTESTER_APP_BUNDLE="\$(cd "\$(dirname "\$0")/../.." && pwd)"

HERE="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
if [ -f "\$HERE/proxy_tester.py" ]; then
    cd "\$HERE"
elif [ -f "${REPO}/proxy_tester.py" ]; then
    cd "${REPO}"
else
    osascript -e 'display alert "ProxyTester" message "Could not find proxy_tester.py. Keep ProxyTester.app in the Proxy-Tester folder, or re-run make_mac_app.sh."'
    exit 1
fi

# Pick a python3 by what it can actually DO, not by where it sits on PATH.
#
# Two things are being decided at once:
#   1. Can it import tkinter? Homebrew's python3 can't unless python-tk was
#      installed separately, and it sits near the front of the PATH above - so
#      taking the first python3 found would fail on a Mac that has a perfectly
#      good one elsewhere.
#   2. Which Tk does it link? Apple's /usr/bin/python3 uses the system Tk
#      8.5.9 (circa 2010), whose Aqua port opens blank white windows. A Tk 8.6
#      interpreter is strictly better, so it WINS even if a Tk 8.5 one was
#      found first. A Tk 8.5 interpreter is only used when nothing else works -
#      ugly-but-running beats not starting, and the app has a repaint
#      workaround for exactly that case.
#
# Candidates include user-writable locations (~/Desktop, uv, ~/.local, and a
# 'python' folder beside the source) because installing to /Library needs admin
# - which plenty of managed and remote Macs don't grant. A relocatable Python
# unpacked into a folder you own is a perfectly good answer, and unmatched
# globs simply fail the executable test below.
BEST=""
FALLBACK=""
TRIED=""
SEEN=""
for cand in \\
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \\
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \\
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \\
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \\
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \\
    ./python/bin/python3 \\
    ./python/python3 \\
    "\$HOME"/Desktop/python/bin/python3 \\
    "\$HOME"/Desktop/python/python3 \\
    "\$HOME"/Desktop/python/*/bin/python3 \\
    "\$HOME"/.local/share/uv/python/*/bin/python3 \\
    "\$HOME"/Desktop/uv-bin/python/*/bin/python3 \\
    "\$HOME"/.local/bin/python3 \\
    /opt/homebrew/bin/python3 \\
    /usr/local/bin/python3 \\
    python3 \\
    /usr/bin/python3
do
    resolved="\$(command -v "\$cand" 2>/dev/null)" || continue
    [ -n "\$resolved" ] && [ -x "\$resolved" ] || continue
    case "\$SEEN " in *"\$resolved "*) continue ;; esac
    SEEN="\$SEEN\$resolved "
    # One probe answers both questions. Keep the REASON on failure, not just
    # the fact of it: a GUI launch gets a different environment from Terminal,
    # so an interpreter that imports tkinter fine by hand can still fail here,
    # and a bare "no tkinter" sends you off installing a Python you already own.
    out="\$("\$resolved" -c 'import tkinter; print("TK86" if tkinter.TkVersion >= 8.6 else "TK85")' 2>&1)"
    if [ \$? -eq 0 ]; then
        case "\$out" in
            *TK86*)
                BEST="\$resolved"
                break ;;                      # modern Tk - stop looking
            *TK85*)
                # Usable, but blank-window prone. Remember it and keep looking
                # for something better before settling.
                [ -n "\$FALLBACK" ] || FALLBACK="\$resolved"
                continue ;;
        esac
    fi
    why="\$(printf '%s' "\$out" | tail -1 | tr -d '\\"' | cut -c1-120)"
    [ -n "\$why" ] || why="exited non-zero with no output"
    TRIED="\$TRIED
  \$resolved
      \$why"
done

PY="\$BEST"
[ -n "\$PY" ] || PY="\$FALLBACK"

if [ -z "\$PY" ]; then
    if [ -z "\$TRIED" ]; then
        MSG="No python3 was found on this Mac. Install Python from python.org - it includes the tkinter GUI toolkit."
    else
        MSG="No python3 on this Mac could import tkinter when launched from the Dock. What each one said:
\$TRIED

If one of these works in Terminal, the app is hitting a GUI-launch environment difference - run it from Terminal to confirm:
  cd \\"\$PWD\\" && ./ProxyTester.app/Contents/MacOS/ProxyTester

Otherwise install Python from python.org (it bundles Tk 8.6), or with Homebrew: brew install python-tk"
    fi
    osascript -e "display alert \\"ProxyTester\\" message \\"\$MSG\\""
    exit 1
fi

# Pull the latest source before launching, so opening from the Dock always runs
# the current version - no Terminal, no update prompt. --ff-only means a pull
# is REFUSED rather than merged if there are local edits or a diverged branch,
# so this can never clobber uncommitted work; it just launches what's there.
#
# The watchdog matters: offline, git sits in DNS/TCP retries far longer than
# anyone will wait for an app to open, and that delay would be paid on EVERY
# launch. macOS ships no timeout(1), hence the background-kill pair. 8s is the
# budget - this repo is a couple of files, so a real pull takes about a second;
# anything near 8s means the network isn't there and the app should just start.
# Set PROXYTESTER_NO_AUTOPULL=1 to skip the whole thing.
if [ -z "\$PROXYTESTER_NO_AUTOPULL" ] && [ -d .git ] && command -v git >/dev/null 2>&1; then
    git pull --ff-only --quiet >/dev/null 2>&1 &
    pull_pid=\$!
    ( sleep 8; kill -9 \$pull_pid >/dev/null 2>&1 ) &
    watchdog_pid=\$!
    wait \$pull_pid 2>/dev/null
    kill -9 \$watchdog_pid >/dev/null 2>&1
    wait \$watchdog_pid 2>/dev/null
fi

exec "\$PY" proxy_tester.py
LAUNCHER
chmod +x "$APP/Contents/MacOS/ProxyTester"

# Make Finder pick the new icon up straight away.
touch "$APP"

# --- Desktop shortcut --------------------------------------------------------
# The bundle lives next to the source, which may be several folders deep. A
# shortcut on the Desktop makes it a double-click away without moving the .app
# out of the repo (it looks for proxy_tester.py beside itself first).
#
# A real Finder alias is the better artifact - it keeps the app's icon and
# survives the repo folder being renamed or moved. But making one drives Finder
# through AppleScript, which needs Automation permission; a managed Mac can
# refuse that. So: try the alias, fall back to a symlink, which needs no
# permission at all and Finder still resolves to the app's icon.
desktop_shortcut() {
    DESK="$HOME/Desktop"
    [ -d "$DESK" ] || { echo "No ~/Desktop here - skipped the Desktop shortcut."; return 0; }
    if [ "$REPO" = "$DESK" ]; then
        echo "ProxyTester.app is already on the Desktop - no shortcut needed."
        return 0
    fi

    # Never touch a real bundle or folder someone put there by hand; only clear
    # our own shortcuts (a symlink, or a Finder alias - which is a plain file).
    for old in "$DESK/ProxyTester" "$DESK/ProxyTester.app"; do
        if [ ! -L "$old" ] && [ -d "$old" ]; then
            echo "Left $old alone - it's a real app/folder, not a shortcut."
            echo "Rename or remove it, then re-run this script."
            return 0
        fi
    done
    rm -f "$DESK/ProxyTester" "$DESK/ProxyTester.app"

    if osascript >/dev/null 2>&1 <<OSA
tell application "Finder"
    set d to POSIX file "$DESK" as alias
    set t to POSIX file "$APP" as alias
    make new alias file at d to t with properties {name:"ProxyTester"}
end tell
OSA
    then
        if [ -e "$DESK/ProxyTester" ]; then
            echo "Desktop shortcut: ProxyTester (alias)"
            return 0
        fi
    fi

    if ln -s "$APP" "$DESK/ProxyTester.app" 2>/dev/null; then
        echo "Desktop shortcut: ProxyTester (link)"
        return 0
    fi

    # Both paths failed - almost always macOS withholding Desktop access from
    # the terminal. Say so, and say where the app is, rather than dying.
    echo "Could not write to the Desktop (macOS may be withholding access)."
    echo "Allow it in System Settings > Privacy & Security > Files and Folders,"
    echo "or just drag ProxyTester.app out of this folder yourself."
    return 0
}

echo "Built $APP  (v${VERSION})"
if [ "$DESKTOP_ICON" -eq 1 ]; then
    desktop_shortcut
fi
echo "Drag ProxyTester.app to the Dock too, if you want it pinned."
