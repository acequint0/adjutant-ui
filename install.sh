#!/usr/bin/env bash
# Install the Adjutant web console for Grok Build on Debian-based systems
# (Debian, Ubuntu, Linux Mint, Kali Linux).
# Usage:
#   ./install.sh              # user install to ~/.local  (no root)
#   ./install.sh --prefix DIR
#   sudo ./install.sh --system   # /usr/local
set -euo pipefail

cd "$(dirname "$0")"
VERSION="$(cat VERSION 2>/dev/null || echo 0.2.2)"
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
  echo "Note: Grok Build is not installed for this user yet."
  echo "Adjutant UI will still install. The agent console needs ~/.grok/bin/agent;"
  echo "adjutant --shell works without it."
  echo
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

# Hotkey launcher: raise an existing Adjutant window, otherwise open the UI.
cat > "$BIN/adjutant-ui" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ADJUTANT="${BIN}/adjutant"
if command -v wmctrl >/dev/null 2>&1; then
  if wmctrl -l | grep -qE '[[:space:]]ADJUTANT\$'; then
    wmctrl -F -a ADJUTANT
    exit 0
  fi
fi
exec "\$ADJUTANT" --web
EOF
chmod 755 "$BIN/adjutant-ui"

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

# Super+T (Meta+T) opens Adjutant when that shortcut is free.
HOTKEY_STATE="${XDG_DATA_HOME:-$HOME/.local/share}/adjutant/hotkey"
HOTKEY_CMD="${BIN}/adjutant-ui"

is_our_hotkey_cmd() {
  local cmd="${1:-}"
  [[ "$cmd" == *adjutant* ]]
}

accel_has_super_t() {
  printf '%s' "${1:-}" | grep -Fq "'<Super>t'"
}

ensure_session_bus() {
  if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "/run/user/$(id -u)/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
  fi
  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    export DISPLAY="${DISPLAY:-:0}"
  fi
}

detect_desktop() {
  local d
  d="$(printf '%s %s %s' "${XDG_CURRENT_DESKTOP:-}" "${DESKTOP_SESSION:-}" "${GDMSESSION:-}" | tr '[:upper:]' '[:lower:]')"
  case "$d" in
    *cinnamon*) echo cinnamon ;;
    *xfce*) echo xfce ;;
    *mate*) echo mate ;;
    *kde*|*plasma*) echo kde ;;
    *gnome*|*ubuntu*|*pop*) echo gnome ;;
    *)
      if command -v xfconf-query >/dev/null 2>&1 && [[ -d "${HOME}/.config/xfce4" ]]; then
        echo xfce
      elif command -v gsettings >/dev/null 2>&1 && gsettings list-schemas 2>/dev/null | grep -qx org.cinnamon.desktop.keybindings; then
        echo cinnamon
      elif command -v gsettings >/dev/null 2>&1 && gsettings list-schemas 2>/dev/null | grep -qx org.gnome.settings-daemon.plugins.media-keys; then
        echo gnome
      else
        echo unknown
      fi
      ;;
  esac
}

write_hotkey_state() {
  mkdir -p "$(dirname "$HOTKEY_STATE")"
  cat > "$HOTKEY_STATE" <<EOF
desktop=$1
command=$HOTKEY_CMD
binding=<Super>t
extra=${2:-}
EOF
}

bind_hotkey_xfce() {
  command -v xfconf-query >/dev/null 2>&1 || return 1
  local ch=xfce4-keyboard-shortcuts p cmd
  for p in \
    "/commands/custom/<Super>t" \
    "/commands/default/<Super>t" \
    "/xfwm4/custom/<Super>t" \
    "/xfwm4/default/<Super>t"
  do
    cmd="$(xfconf-query -c "$ch" -p "$p" 2>/dev/null || true)"
    if [[ -n "$cmd" ]]; then
      if is_our_hotkey_cmd "$cmd"; then
        xfconf-query -c "$ch" -n -t string -p "/commands/custom/<Super>t" -s "$HOTKEY_CMD"
        write_hotkey_state xfce "/commands/custom/<Super>t"
        echo "Super+T already opened Adjutant; updated it to ${HOTKEY_CMD}"
        return 0
      fi
      echo "Note: Super+T is already bound (${p} -> ${cmd}); left it unchanged."
      return 0
    fi
  done
  xfconf-query -c "$ch" -n -t string -p "/commands/custom/<Super>t" -s "$HOTKEY_CMD"
  write_hotkey_state xfce "/commands/custom/<Super>t"
  echo "Bound Super+T to ${HOTKEY_CMD}"
}

gsettings_super_t_taken() {
  local out
  out="$(gsettings list-recursively 2>/dev/null | grep -F "'<Super>t'" || true)"
  [[ -n "$out" ]]
}

bind_hotkey_gnome() {
  command -v gsettings >/dev/null 2>&1 || return 1
  local schema=org.gnome.settings-daemon.plugins.media-keys
  gsettings list-schemas 2>/dev/null | grep -qx "$schema" || return 1
  local rel=org.gnome.settings-daemon.plugins.media-keys.custom-keybinding
  local prefix=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/
  local list i path binding command n next
  list="$(gsettings get "$schema" custom-keybindings 2>/dev/null || echo "@as []")"
  i=0
  while [[ $i -lt 32 ]]; do
    path="${prefix}custom${i}/"
    if printf '%s' "$list" | grep -Fq "$path"; then
      binding="$(gsettings get "${rel}:${path}" binding 2>/dev/null || true)"
      command="$(gsettings get "${rel}:${path}" command 2>/dev/null || true)"
      command="${command#\'}"; command="${command%\'}"
      if accel_has_super_t "$binding" || [[ "$binding" == "'<Super>t'" ]]; then
        if is_our_hotkey_cmd "$command"; then
          gsettings set "${rel}:${path}" name "Adjutant"
          gsettings set "${rel}:${path}" command "$HOTKEY_CMD"
          gsettings set "${rel}:${path}" binding "<Super>t"
          write_hotkey_state gnome "$path"
          echo "Super+T already opened Adjutant; updated it to ${HOTKEY_CMD}"
          return 0
        fi
        echo "Note: Super+T is already bound (${command}); left it unchanged."
        return 0
      fi
    fi
    i=$((i + 1))
  done
  if gsettings_super_t_taken; then
    echo "Note: Super+T is already bound; left it unchanged."
    return 0
  fi
  next=""
  i=0
  while [[ $i -lt 32 ]]; do
    path="${prefix}custom${i}/"
    if ! printf '%s' "$list" | grep -Fq "$path"; then
      next="$path"
      n="custom${i}"
      break
    fi
    i=$((i + 1))
  done
  [[ -n "$next" ]] || return 1
  if [[ "$list" == "@as []" || "$list" == "[]" ]]; then
    gsettings set "$schema" custom-keybindings "['${next}']"
  else
    list="${list%]}"
    gsettings set "$schema" custom-keybindings "${list}, '${next}']"
  fi
  gsettings set "${rel}:${next}" name "Adjutant"
  gsettings set "${rel}:${next}" command "$HOTKEY_CMD"
  gsettings set "${rel}:${next}" binding "<Super>t"
  write_hotkey_state gnome "$next"
  echo "Bound Super+T to ${HOTKEY_CMD}"
}

bind_hotkey_cinnamon() {
  command -v gsettings >/dev/null 2>&1 || return 1
  gsettings list-schemas 2>/dev/null | grep -qx org.cinnamon.desktop.keybindings || return 1
  local rel=org.cinnamon.desktop.keybindings.custom-keybinding
  local prefix=/org/cinnamon/desktop/keybindings/custom-keybindings/
  local list i path binding command n next
  list="$(gsettings get org.cinnamon.desktop.keybindings custom-list 2>/dev/null || echo "@as []")"
  i=0
  while [[ $i -lt 32 ]]; do
    n="custom${i}"
    path="${prefix}${n}/"
    if printf '%s' "$list" | grep -Fq "'${n}'"; then
      binding="$(gsettings get "${rel}:${path}" binding 2>/dev/null || true)"
      command="$(gsettings get "${rel}:${path}" command 2>/dev/null || true)"
      command="${command#\'}"; command="${command%\'}"
      if accel_has_super_t "$binding"; then
        if is_our_hotkey_cmd "$command"; then
          gsettings set "${rel}:${path}" name "Adjutant"
          gsettings set "${rel}:${path}" command "$HOTKEY_CMD"
          gsettings set "${rel}:${path}" binding "['<Super>t']"
          write_hotkey_state cinnamon "$n"
          echo "Super+T already opened Adjutant; updated it to ${HOTKEY_CMD}"
          return 0
        fi
        echo "Note: Super+T is already bound (${command}); left it unchanged."
        return 0
      fi
    fi
    i=$((i + 1))
  done
  if gsettings_super_t_taken; then
    echo "Note: Super+T is already bound; left it unchanged."
    return 0
  fi
  next=""
  i=0
  while [[ $i -lt 32 ]]; do
    n="custom${i}"
    if ! printf '%s' "$list" | grep -Fq "'${n}'"; then
      next="$n"
      break
    fi
    i=$((i + 1))
  done
  [[ -n "$next" ]] || return 1
  path="${prefix}${next}/"
  if [[ "$list" == "@as []" || "$list" == "[]" ]]; then
    gsettings set org.cinnamon.desktop.keybindings custom-list "['${next}']"
  else
    list="${list%]}"
    gsettings set org.cinnamon.desktop.keybindings custom-list "${list}, '${next}']"
  fi
  gsettings set "${rel}:${path}" name "Adjutant"
  gsettings set "${rel}:${path}" command "$HOTKEY_CMD"
  gsettings set "${rel}:${path}" binding "['<Super>t']"
  write_hotkey_state cinnamon "$next"
  echo "Bound Super+T to ${HOTKEY_CMD}"
}

bind_hotkey_mate() {
  command -v dconf >/dev/null 2>&1 || return 1
  local base=/org/mate/desktop/keybindings/ i name binding command next
  i=0
  while [[ $i -lt 32 ]]; do
    name="custom${i}"
    binding="$(dconf read "${base}${name}/binding" 2>/dev/null || true)"
    command="$(dconf read "${base}${name}/action" 2>/dev/null || true)"
    command="${command#\'}"; command="${command%\'}"
    if accel_has_super_t "$binding" || [[ "$binding" == "'<Super>t'" ]]; then
      if is_our_hotkey_cmd "$command"; then
        dconf write "${base}${name}/name" "'Adjutant'"
        dconf write "${base}${name}/action" "'${HOTKEY_CMD}'"
        dconf write "${base}${name}/binding" "'<Super>t'"
        write_hotkey_state mate "$name"
        echo "Super+T already opened Adjutant; updated it to ${HOTKEY_CMD}"
        return 0
      fi
      echo "Note: Super+T is already bound (${command}); left it unchanged."
      return 0
    fi
    i=$((i + 1))
  done
  next=""
  i=0
  while [[ $i -lt 32 ]]; do
    name="custom${i}"
    if [[ -z "$(dconf read "${base}${name}/binding" 2>/dev/null || true)" ]]; then
      next="$name"
      break
    fi
    i=$((i + 1))
  done
  [[ -n "$next" ]] || return 1
  dconf write "${base}${next}/name" "'Adjutant'"
  dconf write "${base}${next}/action" "'${HOTKEY_CMD}'"
  dconf write "${base}${next}/binding" "'<Super>t'"
  write_hotkey_state mate "$next"
  echo "Bound Super+T to ${HOTKEY_CMD}"
}

bind_hotkey_kde() {
  local cfg="${HOME}/.config/kglobalshortcutsrc"
  mkdir -p "$(dirname "$cfg")"
  if [[ -f "$cfg" ]] && grep -Eq '(^|[=,])Meta\+T(,|$)' "$cfg"; then
    if grep -E '(^|[=,])Meta\+T(,|$)' "$cfg" | grep -qi adjutant; then
      echo "Super+T (Meta+T) already opens Adjutant; left it unchanged."
      write_hotkey_state kde kglobalshortcutsrc
      return 0
    fi
    echo "Note: Super+T (Meta+T) is already bound; left it unchanged."
    return 0
  fi
  if [[ -f "$cfg" ]] && grep -q '^\[adjutant.desktop\]' "$cfg"; then
    :
  else
    {
      echo
      echo "[adjutant.desktop]"
      echo "_k_friendly_name=Adjutant"
      echo "_launch=Meta+T,none,Adjutant"
    } >> "$cfg"
  fi
  write_hotkey_state kde kglobalshortcutsrc
  echo "Bound Super+T (Meta+T) to ${HOTKEY_CMD}"
}

bind_super_t() {
  if [[ "$(id -u)" -eq 0 ]]; then
    echo "Note: skipped Super+T binding for root. Run ./install.sh as your desktop user to bind it."
    return 0
  fi
  ensure_session_bus
  local de
  de="$(detect_desktop)"
  case "$de" in
    xfce) bind_hotkey_xfce ;;
    gnome) bind_hotkey_gnome ;;
    cinnamon) bind_hotkey_cinnamon ;;
    mate) bind_hotkey_mate ;;
    kde) bind_hotkey_kde ;;
    *)
      echo "Note: could not detect a supported desktop; Super+T was not bound."
      return 0
      ;;
  esac
}

bind_super_t || echo "Note: could not bind Super+T (desktop shortcut setup failed)."

# Persist the user-install bin dir on PATH for interactive bash shells.
if [[ "$SYSTEM" -eq 0 ]]; then
  BASHRC="${HOME}/.bashrc"
  MARKER_BEGIN="# >>> adjutant-ui >>>"
  MARKER_END="# <<< adjutant-ui <<<"
  if [[ -n "${HOME:-}" ]]; then
    touch "$BASHRC"
    if ! grep -Fq "$MARKER_BEGIN" "$BASHRC"; then
      if [[ "$BIN" == "${HOME}/.local/bin" ]]; then
        PATH_EXPR='$HOME/.local/bin'
      else
        PATH_EXPR="$BIN"
      fi
      {
        echo
        echo "$MARKER_BEGIN"
        echo "export PATH=\"${PATH_EXPR}:\$PATH\""
        echo "$MARKER_END"
      } >> "$BASHRC"
      echo
      echo "Added ${BIN} to PATH in ~/.bashrc"
    fi
  fi
fi

case ":$PATH:" in
  *":${BIN}:"*) ;;
  *)
    echo
    echo "Note: ${BIN} is not on your PATH in this shell."
    echo "Open a new terminal, or run:  export PATH=\"${BIN}:\$PATH\""
    ;;
esac

echo
echo "Adjutant UI ${VERSION} installed."
echo "  command : ${BIN}/adjutant"
echo "  files   : ${SHARE}"
echo "  grok    : ${AGENT:-not found (install Grok Build for the agent console)}"
echo
echo "Launch:  adjutant"
echo "Imagine: adjutant --imagine"
echo "Classic: adjutant --tui"
echo "Stop:    adjutant --stop"
echo
echo "Kali / another Debian machine — clone from GitHub:"
echo "  git clone https://github.com/acequint0/adjutant-ui.git"
echo "  cd adjutant-ui && git checkout v0.2.2 && ./install.sh"
echo
echo "Or one-liner:"
echo "  curl -fsSL https://raw.githubusercontent.com/acequint0/adjutant-ui/v0.2.2/packaging/kali-install.sh | bash"
