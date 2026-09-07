#!/bin/sh
# sudo -A helper: prompt the logged-in user to identify themselves.
# Prints the password to stdout; cancel/failure exits non-zero.
TITLE="${ADJUTANT_ASKPASS_TITLE:-ADJUTANT}"
TEXT="${ADJUTANT_ASKPASS_TEXT:-Enter your password to enable passwordless sudo.}"
if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  echo "adjutant-sudo: no display for password prompt" >&2
  exit 1
fi
if command -v zenity >/dev/null 2>&1; then
  exec zenity --password --title="$TITLE" --text="$TEXT"
fi
if command -v yad >/dev/null 2>&1; then
  exec yad --entry --hide-text --title="$TITLE" --text="$TEXT" --button=gtk-ok:0 --button=gtk-cancel:1
fi
echo "adjutant-sudo: zenity is required to identify the user" >&2
exit 1
