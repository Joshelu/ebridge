# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests del registro de interfaces y de la capa de línea de comandos."""

from __future__ import annotations

import pytest

from ebridge import ui
from ebridge.cli import build_parser, main
from ebridge.core import interfaces  # noqa: F401  (registra las interfaces)
from ebridge.core.automation_engine import AutomationEngine
from ebridge.core.config import DeviceConfig
from ebridge.core.highlighter import Highlighter
from ebridge.core.interfaces.base import BaseInterface
from ebridge.core.message_bus import MessageBus
from ebridge.core.register_linker import RegisterLinker
from ebridge.core.registry import BuildContext, RuntimeOptions, available, build_all


def make_context(**options) -> BuildContext:
    bus = MessageBus()
    config = DeviceConfig.from_dict("dev", {})
    opts = RuntimeOptions(port="COM_TEST", **options)
    return BuildContext(
        bus=bus,
        config=config,
        options=opts,
        highlighter=Highlighter(config.highlights),
        register_linker=RegisterLinker(config.register_links),
        automation_engine=AutomationEngine(bus, config.automations),
    )


# ---------------------------------------------------------------------------
# Registro de interfaces
# ---------------------------------------------------------------------------

def test_builtin_interfaces_are_registered():
    assert set(available()) == {"serial", "socket", "log", "terminal"}


def test_all_built_instances_are_interfaces():
    built = build_all(make_context())
    assert built, "debería construirse al menos una interfaz"
    for name, instance, _ in built:
        assert isinstance(instance, BaseInterface), name


def test_terminal_is_the_primary_interface():
    primaries = [name for name, _, is_primary in build_all(make_context()) if is_primary]
    assert primaries == ["terminal"]


def test_no_socket_option_skips_the_socket_interface():
    names = [n for n, _, _ in build_all(make_context(no_socket=True))]
    assert "socket" not in names
    assert "serial" in names and "terminal" in names


def test_log_interface_only_appears_with_a_log_file(tmp_path):
    assert "log" not in [n for n, _, _ in build_all(make_context())]
    with_log = make_context(log_file=str(tmp_path / "s.log"))
    assert "log" in [n for n, _, _ in build_all(with_log)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_parser_requires_a_port():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["mi_dispositivo"])


def test_parser_defaults():
    args = build_parser().parse_args(["dev", "--port", "COM3"])
    assert args.socket_port == 5000
    assert args.socket_host == "0.0.0.0"
    assert args.no_socket is False
    assert args.log is None
    assert args.no_color is False


def test_missing_device_exits_with_code_1(tmp_path, monkeypatch, capsys):
    """La CLI traduce DeviceConfigError en mensaje + código de salida,
    en lugar de escupir un traceback."""
    monkeypatch.chdir(tmp_path)
    code = main(["dispositivo_que_no_existe", "--port", "COM_TEST"])
    assert code == 1
    out = capsys.readouterr().out
    assert "dispositivo_que_no_existe" in out
    assert "Traceback" not in out


def test_no_color_flag_disables_colour(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ui.set_color_enabled(True)
    main(["no_existe", "--port", "COM_TEST", "--no-color"])
    assert ui.color_enabled() is False


def test_version_flag():
    from ebridge import __version__
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--version"])
    assert excinfo.value.code == 0
    assert __version__


# ---------------------------------------------------------------------------
# Capa de salida
# ---------------------------------------------------------------------------

def test_colorize_is_a_no_op_without_colour():
    assert ui.colorize("texto", "red") == "texto"


def test_colorize_wraps_with_colour(color):
    assert ui.colorize("texto", "red") == "\x1b[91mtexto\x1b[0m"


def test_colorize_ignores_unknown_colour(color):
    assert ui.colorize("texto", "fucsia") == "texto"


def test_tagged_messages_are_printed(capsys):
    """La etiqueta es el emisor; el nivel solo decide el color."""
    ui.error("SERIAL", "no se pudo abrir")
    assert capsys.readouterr().out.strip() == "[SERIAL] no se pudo abrir"


def test_strip_ansi_handles_osc8_with_bel_terminator():
    assert ui.strip_ansi("\x1b]8;;http://x\aenlace\x1b]8;;\a") == "enlace"
