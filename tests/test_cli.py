from __future__ import annotations

from pathlib import Path

import pytest

from dkvm.cli import load_config, main, resolve_input, resolve_split


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


def test_resolve_default_split_alias() -> None:
    writes = resolve_split("pbp-50-50", {})
    assert [(write.feature, write.value) for write in writes] == [(0xE9, 36)]


def test_resolve_config_split_with_sub_input_alias() -> None:
    config = {
        "inputs": {"work": "0x11"},
        "splits": {"meeting": {"mode": "0x24", "sub_input": "work"}},
    }
    writes = resolve_split("meeting", config)
    assert [(write.feature, write.value) for write in writes] == [(0xE9, 36), (0xE8, 17)]


def test_resolve_config_split_writes() -> None:
    config = {
        "splits": {
            "quad": {
                "writes": [
                    {"feature": "0xe9", "value": "0x41"},
                    {"feature": "0xe8", "value": "0x3e51"},
                ]
            }
        }
    }
    writes = resolve_split("quad", config)
    assert [(write.feature, write.value) for write in writes] == [(0xE9, 65), (0xE8, 15953)]


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


def test_split_dry_run_with_ddcutil(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "split",
                "pbp-50-50",
                "--sub-input",
                "hdmi1",
                "--backend",
                "ddcutil",
                "--display",
                "1",
                "--dry-run",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.splitlines() == [
        "ddcutil --display 1 setvcp e9 0x24",
        "ddcutil --display 1 setvcp e8 0x11",
    ]


def test_split_dry_run_with_m1ddc(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["split", "pbp-2x2", "--backend", "m1ddc", "--display", "1", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == "m1ddc display 1 set pbp 65"


def test_split_unsupported_backend(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["split", "pbp-50-50", "--backend", "ddcctl", "--dry-run"]) == 2
    assert "does not support arbitrary VCP writes" in capsys.readouterr().err


def test_missing_backend_error_has_install_hint(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["switch", "usb-c", "--backend", "ddcutil"]) == 2
    assert "sudo apt install ddcutil" in capsys.readouterr().err
