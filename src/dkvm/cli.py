from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import tomllib

from . import __version__
from .backends import BACKENDS, BackendError, select_backend

BACKEND_CHOICES = ["auto", *BACKENDS]


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

DEFAULT_SPLITS: dict[str, int] = {
    "off": 0,
    "pip-small": 33,
    "pip-large": 34,
    "pbp": 36,
    "pbp-50-50": 36,
    "pbp-26-74": 43,
    "pbp-74-26": 44,
    "pbp-2x2": 65,
}

PBP_MODE_FEATURE = 0xE9
PBP_INPUT_FEATURE = 0xE8
KVM_FEATURE = 0xE7

DEFAULT_CONFIG = """backend = "auto"
display = "1"

[inputs]
work = "0x0f"
personal = "0x1b"

[splits]
off = { mode = "0x00" }
two-way = { mode = "0x24", sub_input = "work" }
four-way = { mode = "0x41" }
"""


@dataclass(frozen=True)
class VcpWrite:
    feature: int
    value: int


def config_path() -> Path:
    xdg = Path.home() / ".config"
    return xdg / "dkvm" / "config.toml"


def load_config(path: Path | None = None) -> dict[str, object]:
    path = path or config_path()
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_int_value(raw: object, *, value_name: str) -> int:
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError(f"{value_name} must be non-negative")
        return raw
    if not isinstance(raw, str):
        raise ValueError(f"{value_name} must be a string or integer")
    value = raw.strip().lower()
    if value.startswith("0x"):
        return int(value, 16)
    return int(value, 10)


def parse_input_value(raw: object) -> int:
    return parse_int_value(raw, value_name="input value")


def parse_vcp_value(raw: object, *, value_name: str = "VCP value") -> int:
    return parse_int_value(raw, value_name=value_name)


def resolve_input(target: str, config: dict[str, object]) -> int:
    key = target.strip().lower()
    config_inputs = config.get("inputs", {})
    if isinstance(config_inputs, dict) and key in config_inputs:
        return parse_input_value(config_inputs[key])
    if key in DEFAULT_INPUTS:
        return DEFAULT_INPUTS[key]
    return parse_input_value(key)


def resolve_feature(raw: object) -> int:
    feature = parse_vcp_value(raw, value_name="VCP feature")
    if feature > 0xFF:
        raise ValueError("VCP feature must fit in one byte")
    return feature


def split_write_from_config(raw: object, config: dict[str, object]) -> list[VcpWrite]:
    if isinstance(raw, list):
        writes: list[VcpWrite] = []
        for item in raw:
            writes.extend(split_write_from_config(item, config))
        return writes

    if isinstance(raw, (str, int)):
        return [VcpWrite(PBP_MODE_FEATURE, parse_vcp_value(raw))]

    if not isinstance(raw, dict):
        raise ValueError("split config must be a table, array, string, or integer")

    writes = []
    if "mode" in raw:
        writes.append(VcpWrite(PBP_MODE_FEATURE, parse_vcp_value(raw["mode"])))

    for input_key in ("sub_input", "subinput", "pbp_input"):
        if input_key in raw:
            writes.append(
                VcpWrite(PBP_INPUT_FEATURE, resolve_input(str(raw[input_key]), config))
            )

    if "kvm" in raw:
        writes.append(VcpWrite(KVM_FEATURE, parse_vcp_value(raw["kvm"])))

    if "feature" in raw and "value" in raw:
        writes.append(
            VcpWrite(resolve_feature(raw["feature"]), parse_vcp_value(raw["value"]))
        )

    raw_writes = raw.get("writes")
    if raw_writes is not None:
        if not isinstance(raw_writes, list):
            raise ValueError("split writes must be an array")
        for item in raw_writes:
            writes.extend(split_write_from_config(item, config))

    if not writes:
        raise ValueError(
            "split config must include mode, sub_input, kvm, feature/value, or writes"
        )
    return writes


def resolve_split(
    target: str,
    config: dict[str, object],
    *,
    sub_input: str | None = None,
) -> list[VcpWrite]:
    key = target.strip().lower()
    config_splits = config.get("splits", {})
    if isinstance(config_splits, dict) and key in config_splits:
        writes = split_write_from_config(config_splits[key], config)
    elif key in DEFAULT_SPLITS:
        writes = [VcpWrite(PBP_MODE_FEATURE, DEFAULT_SPLITS[key])]
    else:
        writes = [VcpWrite(PBP_MODE_FEATURE, parse_vcp_value(key))]

    if sub_input is not None:
        writes.append(VcpWrite(PBP_INPUT_FEATURE, resolve_input(sub_input, config)))
    return writes


def configured_display(args: argparse.Namespace, config: dict[str, object]) -> str | None:
    display = args.display
    if display is None:
        config_display = config.get("display")
        display = str(config_display) if config_display is not None else None
    return display


def command_switch(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    backend_name = args.backend or str(config.get("backend", "auto"))
    display = configured_display(args, config)

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


def command_split(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    backend_name = args.backend or str(config.get("backend", "auto"))
    display = configured_display(args, config)

    try:
        backend = select_backend(backend_name, require_available=not args.dry_run)
        writes = resolve_split(args.target, config, sub_input=args.sub_input)
        commands = [
            backend.set_vcp_command(display, write.feature, write.value) for write in writes
        ]
    except (BackendError, ValueError) as exc:
        print(f"dkvm: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        for command in commands:
            print(command.display())
        return 0

    for command in commands:
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
    switch.add_argument("--backend", choices=BACKEND_CHOICES)
    switch.add_argument("--display", help="backend display identifier, such as 1 or a UUID")
    switch.add_argument("--config", type=Path, help="config file path")
    switch.add_argument("--dry-run", action="store_true", help="print the backend command")
    switch.set_defaults(func=command_switch)

    split = subparsers.add_parser("split", help="set a PIP/PBP split layout")
    split.add_argument("target", help="split alias, config name, decimal value, or hex value")
    split.add_argument("--sub-input", help="input alias, config name, decimal value, or hex value")
    split.add_argument("--backend", choices=BACKEND_CHOICES)
    split.add_argument("--display", help="backend display identifier, such as 1 or a UUID")
    split.add_argument("--config", type=Path, help="config file path")
    split.add_argument("--dry-run", action="store_true", help="print the backend command")
    split.set_defaults(func=command_split)

    probe = subparsers.add_parser("probe", help="show backend discovery information")
    probe.add_argument("--backend", default="auto", choices=BACKEND_CHOICES)
    probe.add_argument("--dry-run", action="store_true", help="print the probe command only")
    probe.set_defaults(func=command_probe)

    doctor = subparsers.add_parser("doctor", help="check installed DDC backends")
    doctor.add_argument("--backend", default="auto", choices=BACKEND_CHOICES)
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
