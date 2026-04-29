"""
Message Bus — núcleo del patrón productor/consumidor.

Todos los componentes (serial, terminal, socket, automatizaciones)
se comunican exclusivamente a través de este bus, lo que permite
añadir nuevas interfaces sin modificar el resto del sistema.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class MessageSource(Enum):
    SERIAL_RX  = "serial_rx"   # Datos recibidos del puerto serie
    SERIAL_TX  = "serial_tx"   # Datos enviados al puerto serie
    TERMINAL   = "terminal"    # Entrada del usuario en el terminal
    SOCKET_RX  = "socket_rx"   # Datos recibidos de un cliente socket
    AUTOMATION = "automation"  # Generado por una automatización
    SYSTEM     = "system"      # Mensajes internos del sistema


@dataclass
class Message:
    source: MessageSource
    data: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class MessageBus:
    """
    Bus central de mensajes.

    Flujos de datos:
      - dispatch_rx()      → terminal display + socket clients + logger
      - send_to_serial()   → serial writer + logger
      - log_queue          → logger (todos los mensajes)

    Para añadir una nueva interfaz que RECIBA datos del serie:
        q = bus.create_rx_subscriber()
        # luego: msg = await q.get()

    Para añadir una nueva interfaz que ENVÍE datos al serie:
        await bus.send_to_serial(Message(...))
    """

    def __init__(self):
        # Cola de datos de salida hacia el puerto serie
        self.tx_queue: asyncio.Queue[Message] = asyncio.Queue()
        # Cola unificada de log (recibe copias de todos los mensajes)
        self.log_queue: asyncio.Queue[Message] = asyncio.Queue()
        # Lista de colas suscritas a los mensajes entrantes (RX)
        self._rx_subscribers: List[asyncio.Queue[Message]] = []

    # ------------------------------------------------------------------
    # Suscripción
    # ------------------------------------------------------------------

    def create_rx_subscriber(self) -> asyncio.Queue:
        """
        Crea y registra una cola de suscripción a los mensajes RX.
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

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------

    async def dispatch_rx(self, message: Message) -> None:
        """
        Distribuye un mensaje recibido (del serie u otra fuente de entrada)
        a todos los suscriptores y al log.
        """
        for q in self._rx_subscribers:
            await q.put(message)
        await self.log_queue.put(message)

    async def send_to_serial(self, message: Message) -> None:
        """
        Encola un mensaje para ser enviado al puerto serie y lo registra en el log.
        """
        await self.tx_queue.put(message)
        await self.log_queue.put(message)
