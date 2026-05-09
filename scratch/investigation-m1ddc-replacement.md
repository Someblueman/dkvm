# m1ddc Replacement Investigation

## Question

Can dkvm reimplement the macOS capabilities currently provided by m1ddc so a locked-down work laptop does not need a Homebrew/system install?

## Starting repo state

- `src/dkvm/backends.py` shells out to external DDC tools.
- macOS auto-selection currently prefers `m1ddc`, then `ddcctl`, then `ddcutil`.
- `dkvm switch` needs VCP `0x60`; `dkvm split` needs Dell-specific VCP writes `0xe9`, `0xe8`, and optionally `0xe7`.

## External source checks

- Checking m1ddc and AppleSiliconDDC source to identify the transport API and vendoring feasibility.
- `m1ddc` HEAD checked at `054888f Add Raycast extension mention to README (#56)`; latest remote tag observed was `v1.2.0`.
- `AppleSiliconDDC` HEAD checked at `97af381 Merge pull request #2 from danielskowronski/package-and-cli`.
- `m1ddc` is small Objective-C/C source using CoreDisplay, CoreGraphics, Foundation, IOKit, and libobjc.
- `m1ddc` write path:
  - Build DDC write packet with bytes `[0x84, 0x03, feature, value_hi, value_lo, checksum]`.
  - Use DDC chip address `0x37` and data/input address `0x51` for normal VCP writes.
  - Repeat writes twice with a short sleep.
  - Call private macOS symbols `IOAVServiceWriteI2C` and `IOAVServiceReadI2C`.
- `AppleSiliconDDC` implements the same core packet shape and exposes a generic `setvcp` CLI/library surface.
- The current OS exposes the required symbols via system frameworks; a Python `ctypes` probe found `IOAVServiceCreate`, `IOAVServiceWriteI2C`, `IOAVServiceReadI2C`, `CGGetOnlineDisplayList`, and `CoreDisplay_DisplayCreateInfoDictionary`.
- A local source build of `m1ddc` succeeded with Xcode clang and produced a 69K arm64 executable; `display list` saw `DELL U4323QE`.

## Current dkvm fit

- `src/dkvm/backends.py` only needs two backend primitives for this repo's current features:
  - `set_input_command(display, value)` -> VCP `0x60`.
  - `set_vcp_command(display, feature, value)` -> arbitrary 1-byte VCP feature with 16-bit value.
- The direct macOS implementation does not need all `m1ddc` features; it only needs display discovery/selection plus write-only VCP support.
- `dkvm split` already models Dell split support as raw VCP writes, which maps cleanly onto a generic native macOS `setvcp` implementation.

## Feasibility decision

- Feasible: yes, for Apple Silicon macOS external displays supported by `IOAVService*` DDC access.
- Best first implementation path: add a `macos-native` backend that uses Python `ctypes` for direct system-framework calls, avoiding a separate compiled/brew-installed binary.
- Packaging a bundled Objective-C helper is also feasible, but less attractive because source installs still need clang or binary wheel publishing, and a locked-down laptop may dislike unsigned helper binaries.
- Limits remain the same as upstream: built-in HDMI on some M1 / entry-level M2 Macs is not supported by this open transport; Intel macOS still needs `ddcctl` or another path.

## Verification plan for implementation

- Unit-test command/backend selection without touching real DDC.
- Add a dry-run equivalent for native backend that prints `macos-native setvcp <display> <feature> <value>`.
- On real Apple Silicon hardware, verify:
  - native display listing selects the Dell monitor.
  - `dkvm switch personal --backend macos-native`.
  - `dkvm switch work --backend macos-native`.
  - `dkvm split ... --backend macos-native` for the supported Dell codes.

## Implementation pass

- Added `src/dkvm/macos_native.py` as a Python `ctypes` transport over macOS CoreDisplay/CoreFoundation symbols.
- Added `macos-native` to `src/dkvm/backends.py`; auto backend selection now prefers native macOS DDC before shelling out to `m1ddc`.
- Kept the first native display scope to the default IOAVService / `--display 1`, matching the one-external-monitor config already used in this repo.
- Added dry-run tests for native input switching and native PIP/PBP writes.
- Updated README install/backend docs so Apple Silicon macOS no longer requires `brew install m1ddc` for the common path.
- Follow-up marker left in `src/dkvm/macos_native.py` for native multi-display IORegistry matching beyond the default service.
