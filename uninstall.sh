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
rm -f "${PREFIX}/bin/adjutant-ui"
rm -f "${PREFIX}/share/applications/adjutant.desktop"
rm -f "${PREFIX}/share/icons/hicolor/scalable/apps/adjutant.svg"

HOTKEY_STATE="${XDG_DATA_HOME:-$HOME/.local/share}/adjutant/hotkey"
if [[ -f "$HOTKEY_STATE" && "$(id -u)" -ne 0 ]]; then
  # shellcheck disable=SC1090
  desktop=""; extra=""; command=""
  desktop="$(awk -F= '/^desktop=/{print $2}' "$HOTKEY_STATE" 2>/dev/null || true)"
  extra="$(awk -F= '/^extra=/{print $2}' "$HOTKEY_STATE" 2>/dev/null || true)"
  command="$(awk -F= '/^command=/{print $2}' "$HOTKEY_STATE" 2>/dev/null || true)"
  case "$desktop" in
    xfce)
      if command -v xfconf-query >/dev/null 2>&1; then
        cur="$(xfconf-query -c xfce4-keyboard-shortcuts -p "${extra:-/commands/custom/<Super>t}" 2>/dev/null || true)"
        if [[ "$cur" == *adjutant* ]]; then
          xfconf-query -c xfce4-keyboard-shortcuts -p "${extra:-/commands/custom/<Super>t}" -r 2>/dev/null || true
        fi
      fi
      ;;
    gnome)
      if command -v gsettings >/dev/null 2>&1 && [[ -n "$extra" ]]; then
        gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${extra}" name 2>/dev/null || true
        gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${extra}" command 2>/dev/null || true
        gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${extra}" binding 2>/dev/null || true
      fi
      ;;
    cinnamon)
      if command -v gsettings >/dev/null 2>&1 && [[ -n "$extra" ]]; then
        path="/org/cinnamon/desktop/keybindings/custom-keybindings/${extra}/"
        gsettings reset "org.cinnamon.desktop.keybindings.custom-keybinding:${path}" name 2>/dev/null || true
        gsettings reset "org.cinnamon.desktop.keybindings.custom-keybinding:${path}" command 2>/dev/null || true
        gsettings reset "org.cinnamon.desktop.keybindings.custom-keybinding:${path}" binding 2>/dev/null || true
      fi
      ;;
    mate)
      if command -v dconf >/dev/null 2>&1 && [[ -n "$extra" ]]; then
        dconf reset -f "/org/mate/desktop/keybindings/${extra}/" 2>/dev/null || true
      fi
      ;;
    kde)
      cfg="${HOME}/.config/kglobalshortcutsrc"
      if [[ -f "$cfg" ]]; then
        python3 - "$cfg" <<'PY' 2>/dev/null || true
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text()
out, skip, i = [], False, 0
lines = text.splitlines(True)
while i < len(lines):
    line = lines[i]
    if line.strip() == "[adjutant.desktop]":
        skip = True
        i += 1
        continue
    if skip:
        if line.startswith("[") and line.strip() != "[adjutant.desktop]":
            skip = False
        else:
            i += 1
            continue
    out.append(line)
    i += 1
p.write_text("".join(out))
PY
      fi
      ;;
  esac
  rm -f "$HOTKEY_STATE"
fi

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
