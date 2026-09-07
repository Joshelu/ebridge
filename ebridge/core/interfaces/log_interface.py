# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Adaptador que engancha el logger de sesión al registro de interfaces.

:class:`~ebridge.core.logger.SessionLogger` sabe escribir mensajes en un
fichero, pero recibe la cola como argumento de ``run()``.  Esta capa fina le
da la misma forma que a las demás interfaces, de modo que el runner trate a
todas por igual y no tenga casos especiales.
"""

from __future__ import annotations

from typing import Optional

from ebridge import ui
from ebridge.core.interfaces.base import BaseInterface
from ebridge.core.logger import SessionLogger
from ebridge.core.message_bus import MessageBus
from ebridge.core.registry import BuildContext, register

__all__ = ["LogInterface"]


class LogInterface(BaseInterface):
    """Vuelca ``bus.log_queue`` en el fichero de log de la sesión."""

    def __init__(self, bus: MessageBus, logger: SessionLogger):
        self._bus = bus
        self._logger = logger

    async def run(self) -> None:
        ui.note("LOG", f"Registrando la sesión en {self._logger.filepath}")
        await self._logger.run(self._bus.log_queue)


@register("log")
def _build(ctx: BuildContext) -> Optional[LogInterface]:
    if not ctx.options.log_file:
        return None
    return LogInterface(ctx.bus, SessionLogger(ctx.options.log_file, ctx.config.log))
