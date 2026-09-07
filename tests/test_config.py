# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests de la configuración tipada."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebridge.core.config import DeviceConfig, LogConfig, SerialConfig
from ebridge.errors import ConfigError


# ---------------------------------------------------------------------------
# Valores por defecto y validación
# ---------------------------------------------------------------------------

def test_defaults_when_yaml_is_empty():
    cfg = DeviceConfig.from_dict("vacio", {})
    assert cfg.serial.baudrate == 9600
    assert cfg.serial.eol == "\n"
    assert cfg.highlights == ()
    assert cfg.automations == {}
    assert cfg.register_links.enabled is False


@pytest.mark.parametrize("section, key, value", [
    ("serial", "baudrate", 0),
    ("serial", "bytesize", 9),
    ("serial", "parity", "X"),
    ("serial", "stopbits", 3),
    ("serial", "tx_chunk_size", -1),
])
def test_invalid_serial_values_raise(section, key, value):
    with pytest.raises(ConfigError):
        DeviceConfig.from_dict("dev", {section: {key: value}})


def test_non_numeric_baudrate_gives_readable_error():
    with pytest.raises(ConfigError, match="numérico"):
        DeviceConfig.from_dict("dev", {"serial": {"baudrate": "muchos"}})


def test_bool_field_rejects_non_bool():
    with pytest.raises(ConfigError, match="true o false"):
        DeviceConfig.from_dict("dev", {"log": {"timestamp": "sí"}})


def test_unknown_key_is_reported_but_not_fatal(capsys):
    cfg = DeviceConfig.from_dict("dev", {"serial": {"baudrat": 115200}})
    out = capsys.readouterr().out
    assert "baudrat" in out                 # avisa de la errata
    assert cfg.serial.baudrate == 9600      # y sigue con el valor por defecto


def test_unknown_top_level_section_is_reported(capsys):
    DeviceConfig.from_dict("dev", {"higlights": []})
    assert "higlights" in capsys.readouterr().out


def test_highlights_need_a_pattern():
    with pytest.raises(ConfigError, match="pattern"):
        DeviceConfig.from_dict("dev", {"highlights": [{"color": "red"}]})


def test_highlights_are_parsed_in_order():
    cfg = DeviceConfig.from_dict("dev", {"highlights": [
        {"pattern": "OK", "color": "green"},
        {"pattern": "ERROR", "color": "red"},
    ]})
    assert [r.pattern for r in cfg.highlights] == ["OK", "ERROR"]
    assert cfg.highlights[1].color == "red"


# ---------------------------------------------------------------------------
# LogConfig.resolve_path — regresión del TypeError que tumbaba el arranque
# ---------------------------------------------------------------------------

def test_log_path_without_log_section_does_not_crash():
    """Antes esto lanzaba TypeError: None + 'sesion.log'.

    Cualquier dispositivo sin sección `log:` en el YAML (example_device,
    gps_module) reventaba al usar --log.
    """
    cfg = DeviceConfig.from_dict("dev", {})
    assert cfg.log.resolve_path("sesion.log") == Path("sesion.log")


def test_log_path_joins_directory():
    log = LogConfig(directory="logs")
    assert log.resolve_path("sesion.log") == Path("logs") / "sesion.log"


def test_log_path_joins_directory_without_trailing_separator():
    """El separador lo pone Path, no hace falta escribirlo en el YAML."""
    log = LogConfig(directory="C:/Logs")
    assert log.resolve_path("sesion.log").as_posix() == "C:/Logs/sesion.log"


def test_absolute_log_path_ignores_directory():
    log = LogConfig(directory="C:/Logs")
    absolute = Path("D:/otro/sitio/sesion.log")
    assert log.resolve_path(str(absolute)) == absolute


# ---------------------------------------------------------------------------
# Rutas de los scripts de automatización
# ---------------------------------------------------------------------------

def test_automation_script_resolves_relative_to_the_yaml(tmp_path):
    """Una configuración debe funcionar desde cualquier directorio de trabajo."""
    yaml_path = tmp_path / "devices" / "dev.yaml"
    yaml_path.parent.mkdir()
    yaml_path.touch()
    script = tmp_path / "devices" / "automations" / "hola.py"
    script.parent.mkdir()
    script.write_text("async def run(ctx): ...", encoding="utf-8")

    cfg = DeviceConfig.from_dict(
        "dev",
        {"automations": {"hola": {"script": "automations/hola.py"}}},
        source_path=yaml_path,
    )
    assert cfg.automations["hola"].script == script


def test_automation_needs_a_script_key():
    with pytest.raises(ConfigError, match="script"):
        DeviceConfig.from_dict("dev", {"automations": {"hola": {"description": "x"}}})


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_script_is_rejected(value):
    """Un `script:` presente pero vacío se lee como None y acababa convertido
    en la ruta literal 'None', fallando solo al invocar la automatización."""
    with pytest.raises(ConfigError, match="vacío"):
        DeviceConfig.from_dict("dev", {"automations": {"hola": {"script": value}}})


def test_automation_description_is_kept():
    cfg = DeviceConfig.from_dict("dev", {"automations": {
        "hola": {"script": "a.py", "description": "Saluda"},
    }})
    assert cfg.automations["hola"].description == "Saluda"


# ---------------------------------------------------------------------------
# Inmutabilidad
# ---------------------------------------------------------------------------

def test_config_is_frozen():
    cfg = SerialConfig()
    with pytest.raises(Exception):
        cfg.baudrate = 115200  # type: ignore[misc]
