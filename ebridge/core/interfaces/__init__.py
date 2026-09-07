# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Interfaces de eBridge.

Importar este paquete registra todas las interfaces incluidas: el import de
cada módulo ejecuta su decorador ``@register(...)`` (ver
:mod:`ebridge.core.registry`).

**Para añadir una interfaz nueva, añade aquí su línea de import.**  Es lo único
que hay que tocar fuera del módulo de la propia interfaz.

Se importan de forma explícita, y no auto-descubriendo el directorio, para que
el orden de arranque sea determinista y para que un fallo de importación se
vea como un error en vez de como una interfaz que "no aparece".
"""

from ebridge.core.interfaces.base import BaseInterface  # noqa: F401

# El orden de estos imports es el orden en que se arrancan las interfaces.
from ebridge.core.interfaces import serial_interface    # noqa: F401
from ebridge.core.interfaces import socket_interface    # noqa: F401
from ebridge.core.interfaces import log_interface       # noqa: F401
from ebridge.core.interfaces import terminal_interface  # noqa: F401

__all__ = ["BaseInterface"]
