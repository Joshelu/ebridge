# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests del resaltador por expresiones regulares."""

from __future__ import annotations

from ebridge import ui
from ebridge.core.config import HighlightRule
from ebridge.core.highlighter import Highlighter


def rules(*pairs) -> list[HighlightRule]:
    return [HighlightRule(pattern=p, color=c) for p, c in pairs]


def test_highlight_wraps_the_match(color):
    h = Highlighter(rules(("ERROR", "red")))
    out = h.highlight("respuesta: ERROR al ejecutar")
    assert ui.ANSI_COLORS["red"] + "ERROR" + ui.RESET in out
    assert ui.strip_ansi(out) == "respuesta: ERROR al ejecutar"


def test_no_color_mode_returns_plain_text():
    h = Highlighter(rules(("ERROR", "red")))
    assert h.highlight("hay un ERROR") == "hay un ERROR"


def test_a_later_rule_does_not_colour_the_ansi_of_an_earlier_one(color):
    """Regresión: las reglas numéricas coloreaban el '91' de \\x1b[91m.

    Al aplicarse las sustituciones en cascada sobre el texto ya coloreado,
    una regla sobre dígitos casaba dentro de los propios códigos de escape y
    rompía la línea. Ahora las coincidencias se calculan sobre el original.
    """
    h = Highlighter(rules(("ERROR", "red"), (r"\d+", "green")))
    out = h.highlight("ERROR 42")
    # El texto visible se conserva intacto…
    assert ui.strip_ansi(out) == "ERROR 42"
    # …y no aparece ningún código de escape malformado por anidamiento.
    assert "\x1b[91m\x1b[92m" not in out
    assert out.count("\x1b[92m") == 1       # solo el 42 va en verde


def test_overlapping_matches_first_rule_wins(color):
    h = Highlighter(rules(("OK DONE", "green"), ("DONE", "red")))
    out = h.highlight("estado: OK DONE")
    assert ui.ANSI_COLORS["green"] + "OK DONE" + ui.RESET in out
    assert ui.ANSI_COLORS["red"] not in out


def test_invalid_regex_is_skipped_not_fatal(capsys):
    h = Highlighter(rules(("[sin cerrar", "red"), ("OK", "green")))
    assert len(h) == 1                       # la mala se descarta
    assert "HIGHLIGHT" in capsys.readouterr().out
    assert h.highlight("todo OK") == "todo OK"


def test_unknown_colour_degrades_to_plain_text(color):
    h = Highlighter(rules(("OK", "fucsia")))
    assert h.highlight("todo OK") == "todo OK"


def test_empty_matches_are_ignored(color):
    h = Highlighter(rules((r"x*", "red")))
    assert h.highlight("abc") == "abc"


def test_strip_removes_colours_and_osc8_links():
    text = "\x1b[91mrojo\x1b[0m y \x1b]8;;http://x\x1b\\enlace\x1b]8;;\x1b\\"
    assert Highlighter.strip(text) == "rojo y enlace"
