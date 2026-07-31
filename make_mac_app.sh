#!/bin/bash
# Build ProxyTester.app - a small macOS bundle that wraps the source in this
# folder, so the app gets a real Dock icon and can be pinned like any other app.
#
# It does NOT copy the code: the bundle just launches proxy_tester.py from here,
# so `git pull` updates the app with no rebuild. Re-run this only if the logo or
# the version changes.
#
# Uses nothing but tools that ship with macOS (sips, iconutil, osascript).
set -e
cd "$(dirname "$0")"
REPO="$PWD"
APP="$REPO/ProxyTester.app"

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
# on it - add both before looking.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:\$PATH"

HERE="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
if [ -f "\$HERE/proxy_tester.py" ]; then
    cd "\$HERE"
elif [ -f "${REPO}/proxy_tester.py" ]; then
    cd "${REPO}"
else
    osascript -e 'display alert "ProxyTester" message "Could not find proxy_tester.py. Keep ProxyTester.app in the Proxy-Tester folder, or re-run make_mac_app.sh."'
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    osascript -e 'display alert "ProxyTester" message "python3 was not found. Install Python from python.org (it includes the tkinter GUI toolkit)."'
    exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    osascript -e 'display alert "ProxyTester" message "Your python3 has no tkinter. Install Python from python.org, or run: brew install python-tk"'
    exit 1
fi

exec python3 proxy_tester.py
LAUNCHER
chmod +x "$APP/Contents/MacOS/ProxyTester"

# Make Finder pick the new icon up straight away.
touch "$APP"

echo "Built $APP  (v${VERSION})"
echo "Open the folder in Finder and drag ProxyTester.app to the Dock."
