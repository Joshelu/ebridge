# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Message Bus — núcleo del patrón productor/consumidor.

Todos los componentes (serie, terminal, socket, automatizaciones) se comunican
exclusivamente a través de este bus, lo que permite añadir interfaces nuevas
sin tocar el resto del sistema.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List

__all__ = ["MessageSource", "Message", "MessageBus"]


class MessageSource(Enum):
    SERIAL_RX  = "serial_rx"   # Datos recibidos del puerto serie
    SERIAL_TX  = "serial_tx"   # Datos escritos en el puerto serie (ver nota)
    TERMINAL   = "terminal"    # Entrada del usuario en el terminal
    SOCKET_RX  = "socket_rx"   # Datos recibidos de un cliente socket
    AUTOMATION = "automation"  # Generado por una automatización
    SYSTEM     = "system"      # Mensajes internos del sistema

    # Nota sobre SERIAL_TX: el bus registra los envíos con la fuente que los
    # originó (TERMINAL, SOCKET_RX o AUTOMATION), que es más informativo que
    # marcarlos todos como SERIAL_TX. El miembro se mantiene para que una
    # interfaz externa pueda usarlo si le conviene, y porque quitarlo
    # rompería el log de sesiones antiguas.


@dataclass
class Message:
    source: MessageSource
    data: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class MessageBus:
    """Bus central de mensajes.

    Flujos de datos:
      - ``dispatch_rx()``    → terminal + clientes socket + logger
      - ``send_to_serial()`` → escritor del puerto serie + logger
      - ``log_queue``        → logger (copia de todos los mensajes)

    Para añadir una interfaz que RECIBA datos del serie::

        q = bus.create_rx_subscriber()
        msg = await q.get()

    Para añadir una interfaz que ENVÍE datos al serie::

        await bus.send_to_serial(Message(...))
    """

    def __init__(self) -> None:
        # Cola de datos de salida hacia el puerto serie
        self.tx_queue: asyncio.Queue[Message] = asyncio.Queue()
        # Cola unificada de log (recibe copia de todos los mensajes)
        self.log_queue: asyncio.Queue[Message] = asyncio.Queue()
        # Colas suscritas a los mensajes entrantes (RX)
        self._rx_subscribers: List[asyncio.Queue[Message]] = []

    # ------------------------------------------------------------------
    # Suscripción
    # ------------------------------------------------------------------

    def create_rx_subscriber(self) -> asyncio.Queue:
        """Crea y registra una cola de suscripción a los mensajes RX.

        Cada llamada devuelve una cola independiente; todos los suscriptores
        reciben una copia de cada mensaje.
        """
        q: asyncio.Queue[Message] = asyncio.Queue()
        self._rx_subscribers.append(q)
        return q

    def remove_rx_subscriber(self, q: asyncio.Queue) -> None:
        """Elimina un suscriptor (p.ej. al terminar una automatización)."""
        try:
            self._rx_subscribers.remove(q)
        except ValueError:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._rx_subscribers)

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------

    async def dispatch_rx(self, message: Message) -> None:
        """Distribuye un mensaje recibido a todos los suscriptores y al log."""
        # Se itera sobre una copia: `await q.put()` cede el control, y una
        # automatización que termine en ese hueco llamaría a
        # remove_rx_subscriber() y mutaría la lista mientras se recorre.
        for q in tuple(self._rx_subscribers):
            await q.put(message)
        await self.log_queue.put(message)

    async def send_to_serial(self, message: Message) -> None:
        """Encola un mensaje hacia el puerto serie y lo registra en el log."""
        await self.tx_queue.put(message)
        await self.log_queue.put(message)
