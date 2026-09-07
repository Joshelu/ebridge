# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Configuración común de los tests."""

from __future__ import annotations

import pytest

from ebridge import ui


@pytest.fixture(autouse=True)
def _no_color():
    """Los tests corren sin color salvo que pidan lo contrario.

    Evita que el resultado dependa de si la consola que ejecuta la suite
    soporta ANSI, y hace comparables las cadenas de texto.
    """
    previous = ui.color_enabled()
    ui.set_color_enabled(False)
    yield
    ui.set_color_enabled(previous)


@pytest.fixture
def color():
    """Activa el color dentro de un test concreto."""
    ui.set_color_enabled(True)
    yield
    ui.set_color_enabled(False)
