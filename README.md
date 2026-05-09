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

This is a Python CLI around DDC/CI monitor control. On Linux, the main runtime
dependency is the `ddcutil` system package. It cannot be declared as a Python
package dependency because it is an external binary with kernel/I2C access
requirements.

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
python -m pip install git+ssh://git@github.com/Someblueman/dkvm.git
dkvm doctor
```

`ddcutil` is the primary backend for Linux. On Apple Silicon macOS, `dkvm` can
write DDC/VCP values directly with its `macos-native` backend, so `m1ddc` is no
longer required for the common Dell input and PIP/PBP flows. `m1ddc` and `ddcctl`
remain fallbacks because DDC access differs by Mac model, port, adapter, and
display.

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
dkvm switch usb-c --backend macos-native --dry-run
```

Switch input:

```sh
dkvm switch usb-c
dkvm switch dp1
dkvm switch hdmi1
```

Set a PIP/PBP split:

```sh
dkvm split off
dkvm split pbp-50-50 --sub-input hdmi1
dkvm split pbp-2x2
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

[splits]
off = { mode = "0x00" }
two-way = { mode = "0x24", sub_input = "work" }
four-way = { mode = "0x41" }
```

Use named targets:

```sh
dkvm switch work
dkvm switch personal
dkvm split two-way
dkvm split four-way
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

## PIP/PBP Split Codes

PIP/PBP support is more model-specific than input switching. On many Dell
UltraSharp models, the split mode is VCP feature `0xe9` and the secondary input
is VCP feature `0xe8`. `dkvm split` has built-in mode aliases matching the values
exposed by `m1ddc` for some Dell displays:

| Name | Value |
| --- | --- |
| `off` | `0x00` |
| `pip-small` | `0x21` |
| `pip-large` | `0x22` |
| `pbp` / `pbp-50-50` | `0x24` |
| `pbp-26-74` | `0x2b` |
| `pbp-74-26` | `0x2c` |
| `pbp-2x2` | `0x41` |

Config entries under `[splits]` can be a mode value or a table:

```toml
[splits]
solo = "0x00"
work-personal = { mode = "0x24", sub_input = "work" }
quad = { mode = "0x41" }
```

For monitor-specific layouts, use raw writes:

```toml
[splits]
quad-custom = { writes = [
  { feature = "0xe9", value = "0x41" },
  { feature = "0xe8", value = "0x3e51" },
] }
```

`ddcutil` can send any configured VCP write. `m1ddc` supports the known Dell
PIP/PBP features `0xe9`, `0xe8`, and `0xe7`. The `ddcctl` fallback only supports
input switching, so `dkvm split` is not available through that backend.

On Apple Silicon macOS, `macos-native` also sends generic VCP writes directly,
so `dkvm split` works through the native backend for the same monitor-supported
PIP/PBP features and raw `[splits]` writes. The first native implementation uses
macOS' default DDC display service and supports the usual one-external-monitor
configuration; omit `--display` or use `--display 1`.

## Monitor Setup Notes

In the Dell OSD, enable DDC/CI and set the USB upstream assignment for each input.
For example, assign DisplayPort to the USB-C upstream port connected to the work
laptop or dock, and USB-C video to the USB-C upstream used by the personal laptop.

If switching the video input works but the keyboard/mouse do not move, the issue
is likely the monitor's USB assignment rather than `dkvm`.

## Current Scope

This project currently supports:

- `ddcutil` on Linux
- native macOS DDC access on Apple Silicon
- `m1ddc` as an Apple Silicon macOS fallback
- `ddcctl` as a macOS fallback

The native Apple Silicon backend uses macOS system frameworks directly rather
than requiring a Homebrew-installed helper. It has the same practical port
limits as the open Apple Silicon DDC tools it replaces; some built-in HDMI paths
on M1 and entry-level M2 Macs are not supported by this transport.
