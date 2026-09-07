#!/usr/bin/env bash
# Remove only the standalone NOPASSWD desktop utility.
set -euo pipefail
PREFIX="${PREFIX:-${HOME}/.local}"
DESKTOP="${XDG_DESKTOP_DIR:-$HOME/Desktop}"

if [[ -x "${PREFIX}/bin/adjutant-sudo" ]]; then
  "${PREFIX}/bin/adjutant-sudo" --stop >/dev/null 2>&1 || true
fi

rm -rf "${PREFIX}/share/adjutant-sudo"
rm -f "${PREFIX}/bin/adjutant-sudo"
rm -f "${PREFIX}/share/applications/adjutant-sudo.desktop"
rm -f "${PREFIX}/share/icons/hicolor/scalable/apps/adjutant-sudo.svg"
rm -f "${DESKTOP}/adjutant-sudo.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${PREFIX}/share/applications" >/dev/null 2>&1 || true
fi

STATE="${XDG_STATE_HOME:-$HOME/.local/state}/adjutant-ui/sudo-app.json"
mkdir -p "$(dirname "$STATE")"
printf '{"installed":false,"declined":false}\n' > "$STATE"

echo "Adjutant NOPASSWD utility removed."
