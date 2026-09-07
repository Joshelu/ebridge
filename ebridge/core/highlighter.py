# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Resaltador de texto mediante expresiones regulares.

Las reglas vienen del YAML del dispositivo:

  highlights:
    - pattern: "\\bOK\\b"
      color: green
    - pattern: "\\bERROR\\b"
      color: red

Los nombres de color válidos son las claves de :data:`ebridge.ui.ANSI_COLORS`.

Nota sobre el orden de aplicación
--------------------------------
Las coincidencias se calculan **todas sobre el texto original** y luego se
sustituyen en una única pasada.  Hacerlo así evita que una regla se aplique
sobre los códigos ANSI insertados por otra anterior (por ejemplo, una regla
sobre ``\\d+`` coloreando el "91" de ``\\x1b[91m``).  Cuando dos reglas se
solapan, gana la que aparece antes en el YAML.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

from ebridge import ui
from ebridge.core.config import HighlightRule

# Se re-exportan para no romper importaciones existentes; la paleta vive ahora
# en ebridge.ui, que es también quien decide si el color está activo.
from ebridge.ui import ANSI_COLORS, RESET  # noqa: F401

__all__ = ["Highlighter", "ANSI_COLORS", "RESET"]


class Highlighter:
    """Aplica colores ANSI a los fragmentos que coincidan con los patrones.

    Ejemplo:
        >>> from ebridge.core.config import HighlightRule
        >>> h = Highlighter([HighlightRule(pattern="ERROR", color="red")])
        >>> "ERROR" in h.highlight("respuesta: ERROR al ejecutar")
        True
    """

    def __init__(self, rules: Iterable[HighlightRule]):
        """
        Args:
            rules: reglas ya validadas (:class:`~ebridge.core.config.HighlightRule`).
                   Un patrón regex inválido se descarta con un aviso, en lugar
                   de tumbar el arranque por una errata en el YAML.
        """
        self._rules: List[Tuple[re.Pattern, str]] = []
        for rule in rules:
            try:
                self._rules.append((re.compile(rule.pattern), rule.color))
            except re.error as e:
                ui.warn("HIGHLIGHT",
                        f"Patrón regex inválido '{rule.pattern}', regla ignorada: {e}")

    def __len__(self) -> int:
        return len(self._rules)

    def highlight(self, text: str) -> str:
        """Devuelve el texto con códigos ANSI insertados en las coincidencias."""
        if not self._rules or not ui.color_enabled():
            return text

        spans = self._collect_spans(text)
        if not spans:
            return text

        out: List[str] = []
        cursor = 0
        for start, end, color in spans:
            out.append(text[cursor:start])
            out.append(ui.colorize(text[start:end], color))
            cursor = end
        out.append(text[cursor:])
        return "".join(out)

    def _collect_spans(self, text: str) -> Sequence[Tuple[int, int, str]]:
        """Coincidencias no solapadas, ordenadas por posición.

        Prioridad: el orden de las reglas en el YAML.  Una coincidencia se
        descarta si pisa a otra de una regla anterior.
        """
        taken: List[Tuple[int, int, str]] = []
        for pattern, color in self._rules:
            for m in pattern.finditer(text):
                start, end = m.span()
                if start == end:
                    continue  # coincidencia vacía: no hay nada que colorear
                if any(start < t_end and end > t_start for t_start, t_end, _ in taken):
                    continue
                taken.append((start, end, color))
        return sorted(taken)

    @staticmethod
    def strip(text: str) -> str:
        """Elimina los códigos ANSI de un texto (para volcarlo a fichero)."""
        return ui.strip_ansi(text)
