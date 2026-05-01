from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

from . import __version__
from .backends import BACKENDS, BackendError, select_backend


DEFAULT_INPUTS: dict[str, int] = {
    "dp": 0x0F,
    "dp1": 0x0F,
    "displayport": 0x0F,
    "displayport1": 0x0F,
    "dp2": 0x10,
    "displayport2": 0x10,
    "hdmi": 0x11,
    "hdmi1": 0x11,
    "hdmi2": 0x12,
    "usb-c": 0x1B,
    "usbc": 0x1B,
    "usb_c": 0x1B,
}

DEFAULT_CONFIG = """backend = "auto"
display = "1"

[inputs]
work = "0x0f"
personal = "0x1b"
"""


def config_path() -> Path:
    xdg = Path.home() / ".config"
    return xdg / "dkvm" / "config.toml"


def load_config(path: Path | None = None) -> dict[str, object]:
    path = path or config_path()
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_input_value(raw: object) -> int:
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError("input value must be non-negative")
        return raw
    if not isinstance(raw, str):
        raise ValueError("input value must be a string or integer")
    value = raw.strip().lower()
    if value.startswith("0x"):
        return int(value, 16)
    return int(value, 10)


def resolve_input(target: str, config: dict[str, object]) -> int:
    key = target.strip().lower()
    config_inputs = config.get("inputs", {})
    if isinstance(config_inputs, dict) and key in config_inputs:
        return parse_input_value(config_inputs[key])
    if key in DEFAULT_INPUTS:
        return DEFAULT_INPUTS[key]
    return parse_input_value(key)


def command_switch(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    backend_name = args.backend or str(config.get("backend", "auto"))
    display = args.display
    if display is None:
        configured_display = config.get("display")
        display = str(configured_display) if configured_display is not None else None

    try:
        backend = select_backend(backend_name, require_available=not args.dry_run)
        value = resolve_input(args.target, config)
    except (BackendError, ValueError) as exc:
        print(f"dkvm: {exc}", file=sys.stderr)
        return 2

    command = backend.set_input_command(display, value)
    if args.dry_run:
        print(command.display())
        return 0

    try:
        backend.run(command)
    except Exception as exc:
        print(f"dkvm: command failed: {command.display()}", file=sys.stderr)
        print(f"dkvm: {exc}", file=sys.stderr)
        return 1
    return 0


def command_probe(args: argparse.Namespace) -> int:
    try:
        backend = select_backend(args.backend)
    except BackendError as exc:
        print(f"dkvm: {exc}", file=sys.stderr)
        return 2
    command = backend.probe_command()
    print(f"backend: {backend.name}")
    print(f"command: {command.display()}")
    if args.dry_run:
        return 0
    try:
        backend.run(command)
    except Exception as exc:
        print(f"dkvm: command failed: {exc}", file=sys.stderr)
        return 1
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    missing = []
    for backend in BACKENDS.values():
        status = "found" if backend.available() else "missing"
        print(f"{backend.name}: {status}")
        if not backend.available():
            print(f"  {backend.install_hint}")
            missing.append(backend.name)

    try:
        selected = select_backend(args.backend)
    except BackendError as exc:
        print(f"dkvm: {exc}", file=sys.stderr)
        return 2

    print(f"selected backend: {selected.name}")
    return 0 if not missing or selected.name not in missing else 2


def command_init(args: argparse.Namespace) -> int:
    path = args.config or config_path()
    if path.exists() and not args.force:
        print(f"dkvm: config already exists: {path}", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG)
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dkvm",
        description="Switch Dell monitor KVM inputs using DDC/CI.",
    )
    parser.add_argument("--version", action="version", version=f"dkvm {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    switch = subparsers.add_parser("switch", help="switch to an input")
    switch.add_argument("target", help="input alias, config name, decimal value, or hex value")
    switch.add_argument("--backend", choices=["auto", "ddcutil", "m1ddc", "ddcctl"])
    switch.add_argument("--display", help="backend display identifier, such as 1 or a UUID")
    switch.add_argument("--config", type=Path, help="config file path")
    switch.add_argument("--dry-run", action="store_true", help="print the backend command")
    switch.set_defaults(func=command_switch)

    probe = subparsers.add_parser("probe", help="show backend discovery information")
    probe.add_argument("--backend", default="auto", choices=["auto", "ddcutil", "m1ddc", "ddcctl"])
    probe.add_argument("--dry-run", action="store_true", help="print the probe command only")
    probe.set_defaults(func=command_probe)

    doctor = subparsers.add_parser("doctor", help="check installed DDC backends")
    doctor.add_argument("--backend", default="auto", choices=["auto", "ddcutil", "m1ddc", "ddcctl"])
    doctor.set_defaults(func=command_doctor)

    init = subparsers.add_parser("init", help="write a starter config")
    init.add_argument("--config", type=Path, help="config file path")
    init.add_argument("--force", action="store_true", help="overwrite an existing config")
    init.set_defaults(func=command_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
