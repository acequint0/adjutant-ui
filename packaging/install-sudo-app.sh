#!/usr/bin/env bash
# Install the standalone Adjutant NOPASSWD desktop utility.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-${HOME}/.local}"
if [[ -d "${HERE}/sudo_app" ]]; then
  ADJ_SHARE="${ADJUTANT_UI_ROOT:-$HERE}"
  SRC="${HERE}/sudo_app"
elif [[ -d "${HERE}/../sudo_app" ]]; then
  ADJ_SHARE="${ADJUTANT_UI_ROOT:-$(cd "${HERE}/.." && pwd)}"
  SRC="$(cd "${HERE}/../sudo_app" && pwd)"
else
  ADJ_SHARE="${ADJUTANT_UI_ROOT:-${PREFIX}/share/adjutant-ui}"
  SRC="${ADJ_SHARE}/sudo_app"
fi
if [[ ! -f "$SRC/server.py" ]]; then
  echo "adjutant-sudo: source UI not found at $SRC" >&2
  exit 1
fi

SHARE="${PREFIX}/share/adjutant-sudo"
BIN="${PREFIX}/bin"
APP="${PREFIX}/share/applications"
ICON="${PREFIX}/share/icons/hicolor/scalable/apps"
DESKTOP="${XDG_DESKTOP_DIR:-$HOME/Desktop}"

mkdir -p "$SHARE/www" "$BIN" "$APP" "$ICON"
rm -rf "$SHARE/www"
cp -a "$SRC/server.py" "$SHARE/"
cp -a "$SRC/www" "$SHARE/"
chmod 755 "$SHARE/server.py"

if [[ -d "${ADJ_SHARE}/www/fonts" ]]; then
  mkdir -p "$SHARE/www/fonts"
  cp -a "${ADJ_SHARE}/www/fonts/." "$SHARE/www/fonts/"
elif [[ -d "${HERE}/../www/fonts" ]]; then
  mkdir -p "$SHARE/www/fonts"
  cp -a "${HERE}/../www/fonts/." "$SHARE/www/fonts/"
fi
if [[ -f "${ADJ_SHARE}/www/icons/adjutant.svg" ]]; then
  mkdir -p "$SHARE/www/icons"
  cp "${ADJ_SHARE}/www/icons/adjutant.svg" "$SHARE/www/icons/"
  cp "${ADJ_SHARE}/www/icons/adjutant.svg" "$ICON/adjutant-sudo.svg"
elif [[ -f "${HERE}/../www/icons/adjutant.svg" ]]; then
  mkdir -p "$SHARE/www/icons"
  cp "${HERE}/../www/icons/adjutant.svg" "$SHARE/www/icons/"
  cp "${HERE}/../www/icons/adjutant.svg" "$ICON/adjutant-sudo.svg"
fi

UNINSTALL="${ADJ_SHARE}/uninstall-sudo-app.sh"
if [[ ! -f "$UNINSTALL" ]]; then
  UNINSTALL="${HERE}/uninstall-sudo-app.sh"
fi

cat > "$BIN/adjutant-sudo" <<EOF
#!/usr/bin/env bash
export ADJUTANT_SUDO_UI_ROOT="${SHARE}"
export ADJUTANT_UI_ROOT="${ADJ_SHARE}"
export ADJUTANT_SUDO_UNINSTALL="${UNINSTALL}"
exec python3 "${SHARE}/server.py" "\$@"
EOF
chmod 755 "$BIN/adjutant-sudo"

cat > "$APP/adjutant-sudo.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Adjutant NOPASSWD
Comment=Passwordless sudo toggle
Exec=${BIN}/adjutant-sudo
Icon=${ICON}/adjutant-sudo.svg
Terminal=false
Categories=System;Settings;Utility;
Keywords=sudo;passwordless;adjutant;nopasswd;
StartupNotify=true
EOF

if [[ -d "$DESKTOP" ]]; then
  cp "$APP/adjutant-sudo.desktop" "$DESKTOP/adjutant-sudo.desktop"
  chmod +x "$DESKTOP/adjutant-sudo.desktop"
  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP/adjutant-sudo.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP" >/dev/null 2>&1 || true
fi

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/adjutant-ui"
mkdir -p "$STATE_DIR"
printf '{"installed":true,"declined":false}\n' > "$STATE_DIR/sudo-app.json"

echo "Adjutant NOPASSWD utility installed."
echo "  command : ${BIN}/adjutant-sudo"
echo "  desktop : ${APP}/adjutant-sudo.desktop"
