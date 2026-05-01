# dkvm

`dkvm` switches a Dell monitor's active input from the command line using DDC/CI.
On Dell monitors with an integrated KVM, the USB keyboard/mouse upstream normally
follows the active video input once the monitor's USB assignment is configured in
the on-screen display.

The first target is a Dell UltraSharp-style setup:

- personal machine on USB-C
- work laptop or dock on DisplayPort/HDMI plus the matching USB upstream cable
- DDC/CI enabled in the monitor OSD
- Dell software not installed

## Install

For now this is a Python CLI wrapper around proven open-source DDC tools. The
main runtime dependency is the `ddcutil` system package on Linux. It cannot be
declared as a Python package dependency because it is an external binary with
kernel/I2C access requirements.

Linux:

```sh
./scripts/install-ddcutil.sh
python -m pip install git+ssh://git@github.com/Someblueman/dkvm.git
dkvm doctor
```

Or install manually with your distribution package manager, for example
`sudo apt install ddcutil`.

macOS:

```sh
brew install m1ddc
python -m pip install git+ssh://git@github.com/Someblueman/dkvm.git
dkvm doctor
```

`ddcutil` is the primary backend for Linux. macOS support uses `m1ddc` on Apple
Silicon, or `ddcctl` as a fallback on Intel Macs, because DDC access differs
from Linux.

For isolated installs, use `pipx`:

```sh
pipx install git+ssh://git@github.com/Someblueman/dkvm.git
```

For local development:

```sh
git clone git@github.com:Someblueman/dkvm.git
cd dkvm
python -m pip install -e .
python -m pytest
```

## Quick Start

List the command that would be run:

```sh
dkvm switch usb-c --dry-run
dkvm switch dp1 --display 1 --dry-run
```

Switch input:

```sh
dkvm switch usb-c
dkvm switch dp1
dkvm switch hdmi1
```

Show backend and display discovery information:

```sh
dkvm doctor
dkvm probe
```

Create a starter config:

```sh
dkvm init
```

Then edit `~/.config/dkvm/config.toml`:

```toml
backend = "auto"
display = "1"

[inputs]
work = "0x0f"
personal = "0x1b"
```

Use named targets:

```sh
dkvm switch work
dkvm switch personal
```

## Input Codes

Most Dell monitors expose input selection as VCP feature `0x60`.

Common values:

| Name | Value |
| --- | --- |
| `dp1` | `0x0f` |
| `dp2` | `0x10` |
| `hdmi1` | `0x11` |
| `hdmi2` | `0x12` |
| `usb-c` | `0x1b` |

Some tools display the same values in decimal: DisplayPort 1 is `15`, HDMI 1 is
`17`, and USB-C is `27`.

To confirm your monitor's supported values on Linux:

```sh
ddcutil capabilities | grep -A 8 "Input Source"
```

## Monitor Setup Notes

In the Dell OSD, enable DDC/CI and set the USB upstream assignment for each input.
For example, assign DisplayPort to the USB-C upstream port connected to the work
laptop or dock, and USB-C video to the USB-C upstream used by the personal laptop.

If switching the video input works but the keyboard/mouse do not move, the issue
is likely the monitor's USB assignment rather than `dkvm`.

## Current Scope

This project currently shells out to:

- `ddcutil` on Linux
- `m1ddc` on Apple Silicon macOS
- `ddcctl` as a macOS fallback

Native DDC implementations can be added later once the command behavior is proven
against real monitors.
