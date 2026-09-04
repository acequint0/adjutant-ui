#!/usr/bin/env bash
# Build an architecture-independent .deb for Debian, Ubuntu, Mint, and Kali.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(cat VERSION)"
PKG="adjutant-ui_${VERSION}_all"
DEST="$(pwd)/dist/${PKG}"

rm -rf "$DEST" "$(pwd)/dist/${PKG}.deb"
mkdir -p "$DEST/DEBIAN"
mkdir -p "$DEST/usr/bin"
mkdir -p "$DEST/usr/share/adjutant-ui"
mkdir -p "$DEST/usr/share/applications"
mkdir -p "$DEST/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$(pwd)/dist"

cp server.py VERSION "$DEST/usr/share/adjutant-ui/"
cp -a www "$DEST/usr/share/adjutant-ui/"
chmod 755 "$DEST/usr/share/adjutant-ui/server.py"

cat > "$DEST/usr/bin/adjutant" <<'EOF'
#!/usr/bin/env bash
export ADJUTANT_UI_ROOT="/usr/share/adjutant-ui"
exec python3 "${ADJUTANT_UI_ROOT}/server.py" "$@"
EOF
chmod 755 "$DEST/usr/bin/adjutant"

cp www/icons/adjutant.svg "$DEST/usr/share/icons/hicolor/scalable/apps/adjutant.svg"

cat > "$DEST/usr/share/applications/adjutant.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Adjutant
Comment=Grok Build command console
Exec=/usr/bin/adjutant --web
Icon=adjutant
Terminal=false
Categories=Development;Utility;
Keywords=grok;agent;terminal;adjutant;kali;
StartupNotify=true
EOF

cat > "$DEST/DEBIAN/control" <<EOF
Package: adjutant-ui
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9)
Recommends: xdg-utils, chromium | chromium-browser | firefox-esr | firefox | google-chrome-stable
Maintainer: acequint0 <aceaftercolorado@gmail.com>
Homepage: https://github.com/acequint0/adjutant-ui
Description: Adjutant web console for Grok Build (version 0.2)
 Local-only web terminal that wraps Grok Build in the Adjutant command
 console. Works on Debian, Ubuntu, Linux Mint, and Kali Linux.
 Grok Build (~/.grok/bin/agent) is required for the agent console;
 adjutant --shell still works without it.
EOF

cat > "$DEST/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$DEST/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$DEST" "$(pwd)/dist/${PKG}.deb"
echo "built $(pwd)/dist/${PKG}.deb"
echo "install with:  sudo apt-get install -y ./dist/${PKG}.deb"
