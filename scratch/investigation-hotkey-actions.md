# Hotkey Action Investigation

## Goal

Add command targets and a native listener for locked-down machines where external
hotkey tools are not installable:

- cycle between configured PIP/PBP layouts
- trigger the Dell KVM-next toggle

## Decision

- Keep the scriptable command targets, but also add a repo-owned foreground
  macOS listener with no LaunchAgent installer.
- Add hotkey-friendly commands:
  - `dkvm cycle <name>` reads `[cycles.<name>] targets = [...]`, persists the last selected target under the user state directory, then applies the next split target.
  - `dkvm kvm-toggle` sends VCP feature `0xe7` with default value `0xff00`, matching the Dell KVM-next value exposed by `m1ddc`.
- Support `--dry-run` on both so users can validate a hotkey command before binding it.
- Store cycle state under `XDG_STATE_HOME/dkvm` or `~/.local/state/dkvm` so repeated hotkey invocations know which layout comes next.
- Add `dkvm hotkeys run` using Carbon `RegisterEventHotKey` through `ctypes`.
- Do not add LaunchAgent installation because the work laptop may block it; the
  listener can still be started manually from an allowed shell/session.

## Verification

- `python -m pytest`
- `python -m compileall -q src`
- `git diff --check`
- Manual dry-run with temp config:
  - `dkvm cycle layouts --config <temp> --dry-run`
  - `dkvm cycle layouts --target two-way --config <temp> --dry-run`
- Manual dry-run:
  - `dkvm kvm-toggle --backend macos-native --display 1 --dry-run`
- `dkvm hotkeys run --config <temp> --dry-run`
