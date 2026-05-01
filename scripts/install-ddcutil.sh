#!/usr/bin/env sh
set -eu

if command -v ddcutil >/dev/null 2>&1; then
  echo "ddcutil is already installed: $(command -v ddcutil)"
  exit 0
fi

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y ddcutil
  exit 0
fi

if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y ddcutil
  exit 0
fi

if command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --needed ddcutil
  exit 0
fi

if command -v zypper >/dev/null 2>&1; then
  sudo zypper install -y ddcutil
  exit 0
fi

cat >&2 <<'EOF'
Could not find a supported package manager.
Install ddcutil manually with your system package manager, then run:

  dkvm doctor
EOF
exit 1
