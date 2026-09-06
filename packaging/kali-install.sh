#!/usr/bin/env bash
# Install Adjutant UI 0.2.2 from GitHub on Kali / Debian / Ubuntu / Mint.
#
# User install (no root):
#   curl -fsSL https://raw.githubusercontent.com/acequint0/adjutant-ui/v0.2.2/packaging/kali-install.sh | bash
#
# System-wide:
#   curl -fsSL https://raw.githubusercontent.com/acequint0/adjutant-ui/v0.2.2/packaging/kali-install.sh | sudo bash -s -- --system
set -euo pipefail

REPO="${ADJUTANT_REPO:-https://github.com/acequint0/adjutant-ui.git}"
REF="${ADJUTANT_REF:-v0.2.2}"
SRC="${ADJUTANT_SRC:-${HOME}/src/adjutant-ui}"
SYSTEM=0
PREFIX=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --system) SYSTEM=1; shift ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --src) SRC="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

need_pkg() {
  command -v "$1" >/dev/null 2>&1
}

if ! need_pkg python3 || ! need_pkg git; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing git and python3..."
    if [[ "$(id -u)" -eq 0 ]]; then
      apt-get update -qq
      DEBIAN_FRONTEND=noninteractive apt-get install -y git python3
    else
      echo "Need git and python3. On Kali:" >&2
      echo "  sudo apt-get update && sudo apt-get install -y git python3" >&2
      exit 1
    fi
  else
    echo "git and python3 are required." >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "$SRC")"
if [[ -d "$SRC/.git" ]]; then
  git -C "$SRC" fetch --tags origin
  git -C "$SRC" checkout --force "$REF"
  git -C "$SRC" pull --ff-only origin "$REF" 2>/dev/null || true
else
  git clone --branch "$REF" --depth 1 "$REPO" "$SRC"
fi

args=()
if [[ "$SYSTEM" -eq 1 ]]; then
  args+=(--system)
fi
if [[ -n "$PREFIX" ]]; then
  args+=(--prefix "$PREFIX")
fi

chmod +x "$SRC/install.sh"
"$SRC/install.sh" "${args[@]}"

echo
echo "Adjutant UI 0.2.2 is installed from $REPO ($REF)."
echo "On this machine later, pick up GitHub updates with:"
echo "  ADJUTANT_REF=main $0"
echo "or:"
echo "  git -C $SRC pull && $SRC/install.sh"
