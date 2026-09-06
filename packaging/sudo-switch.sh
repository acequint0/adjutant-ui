#!/usr/bin/env bash
# Root helper: toggle passwordless sudo for SUDO_USER only.
# Invoked as: sudo /usr/local/lib/adjutant-ui/sudo-switch {status|on|off}
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo '{"ok":false,"error":"root required"}' >&2
  exit 1
fi

USER_NAME="${SUDO_USER:-}"
if [[ ! "$USER_NAME" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]]; then
  echo '{"ok":false,"error":"invalid user"}' >&2
  exit 1
fi
if ! getent passwd "$USER_NAME" >/dev/null; then
  echo '{"ok":false,"error":"unknown user"}' >&2
  exit 1
fi

CMD="${1:-status}"
DROPIN="/etc/sudoers.d/zz-adjutant-nopasswd"
SWITCH="/etc/sudoers.d/zz-adjutant-switch"
STASH="/var/lib/adjutant-ui/sudo-stash"
HELPER="${ADJUTANT_SUDO_SWITCH:-/usr/local/lib/adjutant-ui/sudo-switch}"

user_passwordless() {
  sudo -l -U "$USER_NAME" 2>/dev/null | grep -Eq '\(ALL( : ALL)?\) NOPASSWD: ALL'
}

write_validated() {
  local dest="$1" body="$2"
  local tmp
  tmp="$(mktemp)"
  printf '%s\n' "$body" >"$tmp"
  chmod 0440 "$tmp"
  if ! visudo -c -f "$tmp" >/dev/null 2>&1; then
    rm -f "$tmp"
    echo '{"ok":false,"error":"sudoers fragment failed visudo"}' >&2
    exit 1
  fi
  install -m 0440 -o root -g root "$tmp" "$dest"
  rm -f "$tmp"
}

ensure_switch_rule() {
  local path body
  path="$HELPER"
  [[ -x "$path" ]] || path="/usr/lib/adjutant-ui/sudo-switch"
  [[ -x "$path" ]] || return 0
  body="# Managed by Adjutant UI. Do not edit.
${USER_NAME} ALL=(root) NOPASSWD: ${path}"
  write_validated "$SWITCH" "$body"
}

stash_foreign_nopasswd() {
  mkdir -p "$STASH"
  chmod 0700 /var/lib/adjutant-ui "$STASH" 2>/dev/null || true
  local f base
  shopt -s nullglob
  for f in /etc/sudoers.d/*; do
    base="$(basename "$f")"
    case "$base" in
      README|*.adjutant-off|zz-adjutant-switch|zz-adjutant-nopasswd) continue ;;
    esac
    [[ -f "$f" ]] || continue
    if grep -Eq "^${USER_NAME}[[:space:]]+ALL[[:space:]]*=[[:space:]]*\\(ALL(:ALL)?\\)[[:space:]]+NOPASSWD:[[:space:]]*ALL[[:space:]]*$" "$f"; then
      mv -f "$f" "$STASH/$base"
    fi
  done
  shopt -u nullglob
}

restore_stashed() {
  [[ -d "$STASH" ]] || return 0
  local f
  shopt -s nullglob
  for f in "$STASH"/*; do
    [[ -f "$f" ]] || continue
    install -m 0440 -o root -g root "$f" "/etc/sudoers.d/$(basename "$f")"
    rm -f "$f"
  done
  shopt -u nullglob
}

emit_status() {
  local enabled=false managed=false
  if user_passwordless; then
    enabled=true
  fi
  if [[ -f "$DROPIN" ]]; then
    managed=true
  fi
  printf '{"ok":true,"enabled":%s,"managed":%s,"user":"%s"}\n' \
    "$enabled" "$managed" "$USER_NAME"
}

case "$CMD" in
  status)
    emit_status
    ;;
  on)
    restore_stashed
    write_validated "$DROPIN" "# Managed by Adjutant UI. Do not edit.
${USER_NAME} ALL=(ALL:ALL) NOPASSWD: ALL"
    ensure_switch_rule
    if ! visudo -c >/dev/null 2>&1; then
      rm -f "$DROPIN"
      echo '{"ok":false,"error":"sudoers check failed after enable"}' >&2
      exit 1
    fi
    emit_status
    ;;
  off)
    rm -f "$DROPIN"
    stash_foreign_nopasswd
    ensure_switch_rule
    if ! visudo -c >/dev/null 2>&1; then
      restore_stashed
      echo '{"ok":false,"error":"sudoers check failed after disable"}' >&2
      exit 1
    fi
    emit_status
    ;;
  *)
    echo '{"ok":false,"error":"usage: status|on|off"}' >&2
    exit 2
    ;;
esac
