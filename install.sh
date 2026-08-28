#!/usr/bin/env bash
# Install the Adjutant web console for Grok Build on Debian-based systems.
# Usage:
#   ./install.sh              # user install to ~/.local  (no root)
#   ./install.sh --prefix DIR
#   sudo ./install.sh --system   # /usr/local
set -euo pipefail

cd "$(dirname "$0")"
VERSION="$(cat VERSION 2>/dev/null || echo 1.0.0)"
SYSTEM=0
PREFIX="${PREFIX:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --system) SYSTEM=1; shift ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PREFIX" ]]; then
  if [[ "$SYSTEM" -eq 1 ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="${HOME}/.local"
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. On Debian/Ubuntu/Mint:" >&2
  echo "  sudo apt-get install -y python3 xdg-utils" >&2
  exit 1
fi

AGENT=""
if [[ -n "${ADJUTANT_AGENT:-}" && -x "${ADJUTANT_AGENT}" ]]; then
  AGENT="$ADJUTANT_AGENT"
elif [[ -x "${HOME}/.grok/bin/agent" ]]; then
  AGENT="${HOME}/.grok/bin/agent"
elif command -v agent >/dev/null 2>&1; then
  AGENT="$(command -v agent)"
elif command -v grok >/dev/null 2>&1; then
  AGENT="$(command -v grok)"
fi

if [[ -z "$AGENT" ]]; then
  echo "Grok Build is not installed for this user." >&2
  echo "Install Grok Build first, then run this installer again." >&2
  echo "Expected: ${HOME}/.grok/bin/agent" >&2
  exit 1
fi

SHARE="${PREFIX}/share/adjutant-ui"
BIN="${PREFIX}/bin"
APP="${PREFIX}/share/applications"
ICON="${PREFIX}/share/icons/hicolor/scalable/apps"

mkdir -p "$SHARE" "$BIN" "$APP" "$ICON"
rm -rf "$SHARE/www"
cp -a server.py VERSION www "$SHARE/"
chmod 755 "$SHARE/server.py"

cat > "$BIN/adjutant" <<EOF
#!/usr/bin/env bash
export ADJUTANT_UI_ROOT="${SHARE}"
exec python3 "\${ADJUTANT_UI_ROOT}/server.py" "\$@"
EOF
chmod 755 "$BIN/adjutant"

cp www/icons/adjutant.svg "$ICON/adjutant.svg"

cat > "$APP/adjutant.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Adjutant
Comment=Grok Build command console
Exec=${BIN}/adjutant --web
Icon=${ICON}/adjutant.svg
Terminal=false
Categories=Development;Utility;
Keywords=grok;agent;terminal;adjutant;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${PREFIX}/share/applications" >/dev/null 2>&1 || true
fi

# Keep existing user sound clip; only seed a default if missing.
CLIP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/adjutant"
mkdir -p "$CLIP_DIR"
if [[ ! -f "$CLIP_DIR/adjutant-online.wav" && -f "$HOME/.local/share/adjutant/adjutant-online.wav" ]]; then
  :
fi

case ":$PATH:" in
  *":${BIN}:"*) ;;
  *)
    echo
    echo "Note: ${BIN} is not on your PATH."
    echo "Add this to ~/.bashrc:"
    echo "  export PATH=\"${BIN}:\$PATH\""
    ;;
esac

echo
echo "Adjutant UI ${VERSION} installed."
echo "  command : ${BIN}/adjutant"
echo "  files   : ${SHARE}"
echo "  grok    : ${AGENT}"
echo
echo "Launch:  adjutant"
echo "Classic: adjutant --tui"
echo "Stop:    adjutant --stop"
echo
echo "To copy this installer to another Debian machine that already has Grok Build:"
echo "  tar -C \"$(pwd)/..\" -czf adjutant-ui.tar.gz adjutant-ui"
echo "  # on the other machine:"
echo "  tar -xzf adjutant-ui.tar.gz && cd adjutant-ui && ./install.sh"
