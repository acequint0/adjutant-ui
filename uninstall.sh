#!/usr/bin/env bash
set -euo pipefail

SYSTEM=0
PREFIX="${PREFIX:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --system) SYSTEM=1; shift ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$PREFIX" ]]; then
  if [[ "$SYSTEM" -eq 1 ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="${HOME}/.local"
  fi
fi

if command -v adjutant >/dev/null 2>&1; then
  adjutant --stop >/dev/null 2>&1 || true
fi

rm -rf "${PREFIX}/share/adjutant-ui"
rm -f "${PREFIX}/bin/adjutant"
rm -f "${PREFIX}/share/applications/adjutant.desktop"
rm -f "${PREFIX}/share/icons/hicolor/scalable/apps/adjutant.svg"

# Restore a classic TUI launcher so `adjutant` still starts Grok.
cat > "${PREFIX}/bin/adjutant" <<'EOF'
#!/usr/bin/env bash
set -u
CLIP="${ADJUTANT_ONLINE_CLIP:-${XDG_DATA_HOME:-$HOME/.local/share}/adjutant/adjutant-online.wav}"
AGENT="${ADJUTANT_AGENT:-$HOME/.grok/bin/agent}"
if [[ -f "$CLIP" ]]; then
  if command -v paplay >/dev/null 2>&1; then
    paplay "$CLIP" >/dev/null 2>&1 &
  elif command -v aplay >/dev/null 2>&1; then
    aplay -q "$CLIP" >/dev/null 2>&1 &
  fi
fi
if [[ -x "$AGENT" ]]; then
  exec "$AGENT" "$@"
fi
if command -v agent >/dev/null 2>&1; then
  exec agent "$@"
fi
echo "adjutant: grok agent not found (expected $AGENT)" >&2
exit 127
EOF
chmod 755 "${PREFIX}/bin/adjutant"

echo "Adjutant UI removed. ${PREFIX}/bin/adjutant now launches Grok in the terminal."
