# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Compatibilidad hacia atrás: ``cprint`` vive ahora en :mod:`ebridge.ui`.

Este módulo se mantiene para no romper código externo que hiciera
``from ebridge._ansi import cprint``.  El código nuevo debe usar las funciones
semánticas de :mod:`ebridge.ui` (``ui.ok``, ``ui.warn``, ``ui.error``…) en
lugar de escribir códigos ANSI a mano: así ``--no-color`` y los cambios de
paleta siguen funcionando en todo el programa.
"""

from ebridge.ui import cprint  # noqa: F401

__all__ = ["cprint"]
