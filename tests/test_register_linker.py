# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests de los enlaces OSC 8 a registros."""

from __future__ import annotations

from ebridge import ui
from ebridge.core.config import RegisterLinkConfig
from ebridge.core.register_linker import RegisterLinker

LINE = "[DEBUG] Global Bus: th_01_th_TH_ECO = 0x4848 (18504)"


def linker(**kw) -> RegisterLinker:
    return RegisterLinker(RegisterLinkConfig(enabled=True, **kw))


def test_disabled_returns_text_untouched():
    out, found = RegisterLinker(RegisterLinkConfig(enabled=False)).linkify(LINE)
    assert (out, found) == (LINE, False)


def test_linkify_wraps_the_register_name():
    out, found = linker().linkify(LINE)
    assert found is True
    assert "\x1b]8;;http://localhost:8000/th_eco?value=4848\x1b\\" in out
    # El texto visible no cambia: solo se añaden las secuencias de escape.
    assert ui.strip_ansi(out) == LINE


def test_value_is_kept_outside_the_link():
    """La parte '= 0xVALOR' queda fuera del enlace para que el resaltador
    pueda colorear después el hexadecimal."""
    out, _ = linker().linkify(LINE)
    link_close = "\x1b]8;;\x1b\\"
    assert out.split(link_close)[1].startswith(" = 0x4848")


def test_prefix_stripping_produces_the_web_slug():
    out, _ = linker().linkify("ct_CB_CONFIG = 0x2101")
    assert "/cb_config?value=2101" in out


def test_name_without_known_prefix_is_only_lowercased():
    out, _ = linker().linkify("FOO_BAR = 0x01")
    assert "/foo_bar?value=01" in out


def test_base_url_trailing_slash_is_normalised():
    out, _ = linker(base_url="http://host:8000/").linkify("ct_X = 0x1")
    assert "http://host:8000/x?value=1" in out
    assert "8000//" not in out


def test_line_without_registers_is_not_marked():
    out, found = linker().linkify("[INFO] arrancando")
    assert (out, found) == ("[INFO] arrancando", False)


def test_invalid_pattern_disables_the_feature(capsys):
    lk = RegisterLinker(RegisterLinkConfig(enabled=True, pattern="(?P<name>[sin cerrar"))
    assert lk.enabled is False
    assert "LINK" in capsys.readouterr().out
    assert lk.linkify(LINE) == (LINE, False)


def test_several_registers_in_one_line():
    out, found = linker().linkify("a_X = 0x01 y ct_Y = 0x02")
    assert found is True
    assert out.count("\x1b]8;;http") == 2
