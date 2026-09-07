# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests de la resolución de configuraciones de dispositivo."""

from __future__ import annotations

import pytest

from ebridge._loader import load_device_config
from ebridge.errors import DeviceConfigError

YAML = """
serial:
  baudrate: 115200
  eol: "\\r\\n"
highlights:
  - pattern: "OK"
    color: green
"""


def test_missing_device_raises_instead_of_exiting(tmp_path, monkeypatch):
    """Regresión: antes hacía sys.exit(1), lo que impedía usar eBridge como
    librería (un SystemExit no es capturable de forma razonable)."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(DeviceConfigError) as excinfo:
        load_device_config("no_existe")
    assert not isinstance(excinfo.value, SystemExit)
    assert "no_existe" in str(excinfo.value)
    assert "Rutas buscadas" in str(excinfo.value)


def test_loads_from_devices_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "mio.yaml").write_text(YAML, encoding="utf-8")

    cfg = load_device_config("mio")
    assert cfg.name == "mio"
    assert cfg.serial.baudrate == 115200
    assert cfg.serial.eol == "\r\n"
    assert cfg.highlights[0].pattern == "OK"


def test_extension_in_the_name_is_accepted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "mio.yaml").write_text(YAML, encoding="utf-8")
    assert load_device_config("mio.yaml").serial.baudrate == 115200


def test_source_path_is_recorded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "devices").mkdir()
    path = tmp_path / "devices" / "mio.yaml"
    path.write_text(YAML, encoding="utf-8")
    assert load_device_config("mio").source_path == path.resolve()


def test_malformed_yaml_gives_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "roto.yaml").write_text("serial: [\n", encoding="utf-8")
    with pytest.raises(DeviceConfigError, match="YAML inválido"):
        load_device_config("roto")


def test_packaged_devices_are_found_from_anywhere(tmp_path, monkeypatch):
    """Los YAML incluidos en el paquete deben cargarse sin importar el CWD."""
    monkeypatch.chdir(tmp_path)
    cfg = load_device_config("example_device")
    assert cfg.name == "example_device"


def test_local_device_overrides_the_packaged_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "example_device.yaml").write_text(
        "serial:\n  baudrate: 4800\n", encoding="utf-8")
    assert load_device_config("example_device").serial.baudrate == 4800
