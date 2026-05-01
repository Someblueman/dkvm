from __future__ import annotations

from pathlib import Path

import pytest

from dkvm.cli import load_config, main, resolve_input


def test_resolve_default_aliases() -> None:
    assert resolve_input("dp1", {}) == 0x0F
    assert resolve_input("hdmi1", {}) == 0x11
    assert resolve_input("usb-c", {}) == 0x1B


def test_resolve_config_alias() -> None:
    config = {"inputs": {"work": "0x12", "personal": 27}}
    assert resolve_input("work", config) == 0x12
    assert resolve_input("personal", config) == 0x1B


def test_resolve_numeric_values() -> None:
    assert resolve_input("0x0f", {}) == 15
    assert resolve_input("17", {}) == 17


def test_load_config_missing_file(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.toml") == {}


def test_init_writes_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "config.toml"
    assert main(["init", "--config", str(path)]) == 0
    assert "personal" in path.read_text()
    assert str(path) in capsys.readouterr().out


def test_init_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("backend = 'auto'\n")
    assert main(["init", "--config", str(path)]) == 2


def test_switch_dry_run_with_explicit_backend(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["switch", "usb-c", "--backend", "ddcutil", "--display", "1", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == "ddcutil --display 1 setvcp 60 0x1b"


def test_missing_backend_error_has_install_hint(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["switch", "usb-c", "--backend", "ddcutil"]) == 2
    assert "sudo apt install ddcutil" in capsys.readouterr().err
