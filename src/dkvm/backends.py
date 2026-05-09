from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import platform
import shutil
import subprocess

from .macos_native import MacOSNativeDdc, MacOSNativeDdcError


class BackendError(RuntimeError):
    """Raised when no usable DDC backend can be selected."""


@dataclass(frozen=True)
class Command:
    argv: list[str]
    action: Callable[[], None] | None = None

    def display(self) -> str:
        return " ".join(self.argv)


class Backend:
    name = "backend"
    install_hint = "install the backend and make sure it is on PATH"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def probe_command(self) -> Command:
        raise NotImplementedError

    def set_input_command(self, display: str | None, value: int) -> Command:
        raise NotImplementedError

    def set_vcp_command(self, display: str | None, feature: int, value: int) -> Command:
        raise BackendError(f"backend '{self.name}' does not support arbitrary VCP writes")

    def run(self, command: Command) -> subprocess.CompletedProcess[str]:
        if command.action is not None:
            command.action()
            return subprocess.CompletedProcess(command.argv, 0)
        return subprocess.run(command.argv, check=True, text=True)


class DdcutilBackend(Backend):
    name = "ddcutil"
    executable = "ddcutil"
    install_hint = (
        "install ddcutil with your system package manager, for example: "
        "sudo apt install ddcutil, sudo dnf install ddcutil, or sudo pacman -S ddcutil"
    )

    def probe_command(self) -> Command:
        return Command(["ddcutil", "detect"])

    def set_input_command(self, display: str | None, value: int) -> Command:
        argv = ["ddcutil"]
        if display:
            argv.extend(["--display", display])
        argv.extend(["setvcp", "60", f"0x{value:02x}"])
        return Command(argv)

    def set_vcp_command(self, display: str | None, feature: int, value: int) -> Command:
        argv = ["ddcutil"]
        if display:
            argv.extend(["--display", display])
        argv.extend(["setvcp", f"{feature:02x}", f"0x{value:02x}"])
        return Command(argv)


class M1DdcBackend(Backend):
    name = "m1ddc"
    executable = "m1ddc"
    install_hint = "install m1ddc with Homebrew: brew install m1ddc"

    def probe_command(self) -> Command:
        return Command(["m1ddc", "display", "list"])

    def set_input_command(self, display: str | None, value: int) -> Command:
        argv = ["m1ddc"]
        if display:
            argv.extend(["display", display])
        argv.extend(["set", "input", str(value)])
        return Command(argv)

    def set_vcp_command(self, display: str | None, feature: int, value: int) -> Command:
        command_names = {
            0x60: "input",
            0xE7: "kvm",
            0xE8: "pbp-input",
            0xE9: "pbp",
        }
        try:
            command_name = command_names[feature]
        except KeyError as exc:
            raise BackendError(
                f"backend '{self.name}' does not support VCP feature 0x{feature:02x}"
            ) from exc

        argv = ["m1ddc"]
        if display:
            argv.extend(["display", display])
        argv.extend(["set", command_name, str(value)])
        return Command(argv)


class DdcctlBackend(Backend):
    name = "ddcctl"
    executable = "ddcctl"
    install_hint = "install ddcctl with Homebrew: brew install ddcctl"

    def probe_command(self) -> Command:
        return Command(["ddcctl", "-h"])

    def set_input_command(self, display: str | None, value: int) -> Command:
        argv = ["ddcctl"]
        if display:
            argv.extend(["-d", display])
        argv.extend(["-i", str(value)])
        return Command(argv)


class MacOSNativeBackend(Backend):
    name = "macos-native"
    executable = ""
    install_hint = (
        "native macOS DDC requires Apple Silicon and a display reachable through "
        "macOS IOAVService DDC access"
    )

    def available(self) -> bool:
        return MacOSNativeDdc.available()

    def probe_command(self) -> Command:
        return Command(["macos-native", "probe"], action=MacOSNativeDdc().probe)

    def set_input_command(self, display: str | None, value: int) -> Command:
        return self.set_vcp_command(display, 0x60, value)

    def set_vcp_command(self, display: str | None, feature: int, value: int) -> Command:
        argv = ["macos-native"]
        if display:
            argv.extend(["--display", display])
        argv.extend(["setvcp", f"{feature:02x}", f"0x{value:02x}"])
        return Command(
            argv,
            action=lambda: self._write_vcp(display, feature, value),
        )

    def _write_vcp(self, display: str | None, feature: int, value: int) -> None:
        try:
            MacOSNativeDdc().write_vcp(display, feature, value)
        except MacOSNativeDdcError as exc:
            raise BackendError(str(exc)) from exc


BACKENDS: dict[str, Backend] = {
    "macos-native": MacOSNativeBackend(),
    "ddcutil": DdcutilBackend(),
    "m1ddc": M1DdcBackend(),
    "ddcctl": DdcctlBackend(),
}


def select_backend(name: str = "auto", *, require_available: bool = True) -> Backend:
    if name != "auto":
        try:
            backend = BACKENDS[name]
        except KeyError as exc:
            choices = ", ".join(["auto", *BACKENDS])
            raise BackendError(f"unknown backend '{name}', expected one of: {choices}") from exc
        if require_available and not backend.available():
            raise BackendError(
                f"backend '{name}' is not installed or not on PATH; {backend.install_hint}"
            )
        return backend

    preferred = ["ddcutil"]
    if platform.system() == "Darwin":
        preferred = ["macos-native", "m1ddc", "ddcctl", "ddcutil"]

    for candidate in preferred:
        backend = BACKENDS[candidate]
        if backend.available():
            return backend

    raise BackendError(
        "no DDC backend found; use native Apple Silicon macOS support, install "
        "ddcutil on Linux, or install m1ddc/ddcctl on macOS"
    )
