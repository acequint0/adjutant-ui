#!/usr/bin/env bash
# Build a tiny unsigned apt repo next to the .deb (for GitHub Releases).
# Kali/Debian:
#   echo 'deb [trusted=yes] https://github.com/acequint0/adjutant-ui/releases/latest/download/ ./' \
#     | sudo tee /etc/apt/sources.list.d/adjutant.list
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(cat VERSION)"
DEB="$(pwd)/dist/adjutant-ui_${VERSION}_all.deb"
if [[ ! -f "$DEB" ]]; then
  echo "missing $DEB — run packaging/build-deb.sh first" >&2
  exit 1
fi

APT="$(pwd)/dist/apt"
rm -rf "$APT"
mkdir -p "$APT"
cp "$DEB" "$APT/"

# Filename must be relative to the repo root (the release download directory).
(
  cd "$APT"
  dpkg-scanpackages -m . /dev/null > Packages
  gzip -9c Packages > Packages.gz
  apt-ftparchive release . > Release
)

echo "apt repo in $APT"
echo "  Packages  Packages.gz  Release  $(basename "$DEB")"
