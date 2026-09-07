# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
eBridge — Enhanced Bridge
=========================
Terminal serie interactivo con bridge TCP y sistema de automatizaciones.

Uso como módulo:
    python -m ebridge example_device --port /dev/ttyUSB0

Uso programático (integrar en otro proyecto):
    from ebridge import run_terminal
    import asyncio

    asyncio.run(run_terminal(
        device="mi_dispositivo",   # devices/mi_dispositivo.yaml
        port="/dev/ttyUSB0",
        socket_port=5000,
        log_file="sesion.log",
    ))

Clases principales disponibles para construir interfaces propias:
    from ebridge.core.message_bus       import MessageBus, Message, MessageSource
    from ebridge.core.highlighter       import Highlighter
    from ebridge.core.automation_engine import AutomationEngine, AutomationContext
    from ebridge.core.logger            import SessionLogger
    from ebridge.core.interfaces.base   import BaseInterface
"""

# Fuente única de verdad de la versión: pyproject.toml la lee de aquí
# mediante [tool.setuptools.dynamic].
__version__ = "2.0.0"
__author__  = "Jose Luis Alcoba Huertas"
__license__ = "GPL-3.0-or-later"
__all__     = ["run_terminal", "EBridgeError", "DeviceConfigError"]


# ---------------------------------------------------------------------------
# API de alto nivel: run_terminal()
# ---------------------------------------------------------------------------

from ebridge.errors import EBridgeError, DeviceConfigError  # noqa: E402
from ebridge._runner import run_terminal  # noqa: E402
