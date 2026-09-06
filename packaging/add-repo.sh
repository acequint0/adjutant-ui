#!/usr/bin/env bash
# Add GitHub Releases as an apt source and install adjutant-ui.
# Run as root on Kali / Debian / Ubuntu / Mint:
#   curl -fsSL https://raw.githubusercontent.com/acequint0/adjutant-ui/v0.2.1/packaging/add-repo.sh | sudo bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root:  sudo $0" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get not found. This installer is for Debian-based systems (Kali, Ubuntu, Mint)." >&2
  exit 1
fi

LIST=/etc/apt/sources.list.d/adjutant.list
# Latest GitHub Release directory is an apt repo (Packages + .deb as assets).
cat > "$LIST" <<'EOF'
deb [trusted=yes] https://github.com/acequint0/adjutant-ui/releases/latest/download/ ./
EOF

apt-get update -o Dir::Etc::sourcelist="$LIST" -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0
DEBIAN_FRONTEND=noninteractive apt-get install -y adjutant-ui

echo
echo "Adjutant UI installed from GitHub."
echo "apt source: $LIST"
echo "launch:     adjutant"
echo
echo "Update later with:  sudo apt-get update && sudo apt-get install --only-upgrade adjutant-ui"
