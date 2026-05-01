from __future__ import annotations

from dataclasses import dataclass
import platform
import shutil
import subprocess


class BackendError(RuntimeError):
    """Raised when no usable DDC backend can be selected."""


@dataclass(frozen=True)
class Command:
    argv: list[str]

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

    def run(self, command: Command) -> subprocess.CompletedProcess[str]:
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


BACKENDS: dict[str, Backend] = {
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
        preferred = ["m1ddc", "ddcctl", "ddcutil"]

    for candidate in preferred:
        backend = BACKENDS[candidate]
        if backend.available():
            return backend

    raise BackendError(
        "no DDC backend found; install ddcutil on Linux or m1ddc/ddcctl on macOS"
    )
