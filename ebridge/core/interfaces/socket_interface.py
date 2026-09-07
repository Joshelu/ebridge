# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Interfaz de socket TCP.

Acepta conexiones de clientes TCP (telnet, netcat, scripts externos…) y hace
de puente bidireccional con el puerto serie:

  Cliente → socket → bus.send_to_serial()   (el cliente envía comandos)
  bus.dispatch_rx() → socket → Cliente      (el serie responde)

Uso::

  nc 127.0.0.1 5000
  telnet 127.0.0.1 5000

Aislamiento entre clientes
--------------------------
Cada cliente tiene su propia cola de salida y su propia tarea de escritura.
Antes, el bucle de difusión escribía a todos los clientes en serie y mantenía
el lock durante el ``await writer.drain()``, así que un cliente lento o colgado
bloqueaba la difusión entera y con ella a todos los demás.  Ahora un cliente
lento solo llena su propia cola; cuando se pasa de ``_CLIENT_QUEUE_SIZE``
mensajes pendientes se le descartan los más antiguos y se le avisa.

Aviso de seguridad
------------------
El bridge no tiene autenticación: cualquiera que alcance el puerto puede
escribir en el serie.  Por eso conviene escuchar en ``127.0.0.1`` salvo que se
esté en una red de confianza; el valor por defecto (``0.0.0.0``) se mantiene
por compatibilidad y se avisa por pantalla al arrancar.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from ebridge import ui
from ebridge.core.interfaces.base import BaseInterface
from ebridge.core.message_bus import Message, MessageBus, MessageSource
from ebridge.core.registry import BuildContext, register

__all__ = ["SocketInterface"]

log = logging.getLogger(__name__)

# Mensajes pendientes que se le toleran a un cliente antes de descartarle los
# más antiguos. Con líneas de log de un puerto serie, unos pocos miles de
# mensajes son segundos de retraso: más que suficiente para un cliente sano.
_CLIENT_QUEUE_SIZE = 2000

# Prefijo que se antepone a los datos del serie al mandarlos al cliente.
RX_PREFIX = ""


class _Client:
    """Un cliente conectado, con su cola de salida y su tarea de escritura."""

    def __init__(self, writer: asyncio.StreamWriter, addr: str):
        self.writer = writer
        self.addr = addr
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_CLIENT_QUEUE_SIZE)
        self.dropped = 0

    def offer(self, data: bytes) -> None:
        """Encola sin bloquear nunca al que difunde.

        Si la cola está llena, se descarta el mensaje más antiguo: para un
        terminal serie, los datos recientes valen más que los viejos.
        """
        while True:
            try:
                self.queue.put_nowait(data)
                return
            except asyncio.QueueFull:
                try:
                    self.queue.get_nowait()
                    self.dropped += 1
                except asyncio.QueueEmpty:  # pragma: no cover - carrera improbable
                    return

    async def drain_loop(self) -> None:
        """Vuelca la cola del cliente en su socket hasta que se cierra."""
        while True:
            data = await self.queue.get()
            self.writer.write(data)
            await self.writer.drain()


class SocketInterface(BaseInterface):
    """Servidor TCP que hace de puente bidireccional con el puerto serie."""

    def __init__(self, bus: MessageBus, host: str = "0.0.0.0", port: int = 5000):
        self._bus = bus
        self._host = host
        self._port = port
        self._clients: Dict[asyncio.StreamWriter, _Client] = {}
        self._rx_queue: asyncio.Queue[Message] = bus.create_rx_subscriber()
        self._server: Optional[asyncio.AbstractServer] = None

    # ------------------------------------------------------------------
    # Gestión de clientes
    # ------------------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        """Manejador de cada conexión entrante."""
        peer = writer.get_extra_info("peername") or ("?", "?")
        addr = f"{peer[0]}:{peer[1]}"
        client = _Client(writer, addr)
        # El dict es la única estructura compartida y solo se toca desde el
        # event loop, sin await por medio: no hace falta lock.
        self._clients[writer] = client
        ui.info("SOCKET", f"Cliente conectado: {addr}")

        drain_task = asyncio.create_task(client.drain_loop(), name=f"socket-tx-{addr}")
        try:
            client.offer(b"[eBridge] Conectado.\r\n")
            while True:
                line = await reader.readline()
                if not line:
                    break  # conexión cerrada por el cliente
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    await self._bus.send_to_serial(Message(
                        source=MessageSource.SOCKET_RX,
                        data=text,
                        metadata={"client": addr},
                    ))
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("Error con el cliente %s: %s", addr, e)
        finally:
            self._clients.pop(writer, None)
            drain_task.cancel()
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            suffix = f" ({client.dropped} mensajes descartados)" if client.dropped else ""
            ui.info("SOCKET", f"Cliente desconectado: {addr}{suffix}")

    # ------------------------------------------------------------------
    # Difusión de mensajes RX a todos los clientes
    # ------------------------------------------------------------------

    async def _broadcast_loop(self) -> None:
        """Reparte los mensajes del serie por las colas de los clientes.

        No hace E/S: solo encola. Así el ritmo de la difusión no depende de la
        velocidad del cliente más lento.
        """
        while True:
            msg: Message = await self._rx_queue.get()
            data = (RX_PREFIX + msg.data + "\r\n").encode("utf-8")
            for client in tuple(self._clients.values()):
                client.offer(data)

    # ------------------------------------------------------------------
    # Tarea asyncio principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)
        ui.info("SOCKET", f"Escuchando en {self._host}:{self._port}")
        if self._host in ("0.0.0.0", "::"):
            ui.warn("SOCKET", "El bridge acepta conexiones de cualquier equipo "
                              "y no pide autenticación. Usa --socket-host 127.0.0.1 "
                              "si no estás en una red de confianza.")
        try:
            async with self._server:
                await asyncio.gather(
                    self._server.serve_forever(),
                    self._broadcast_loop(),
                )
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Cierra el servidor y desconecta a los clientes. Idempotente."""
        if self._server is None:
            return
        self._server = None
        for writer in tuple(self._clients):
            self._clients.pop(writer, None)
            try:
                writer.close()
            except Exception:
                pass
        self._bus.remove_rx_subscriber(self._rx_queue)
        ui.note("SOCKET", "Servidor cerrado.")


@register("socket")
def _build(ctx: BuildContext) -> Optional[SocketInterface]:
    if ctx.options.no_socket:
        return None
    return SocketInterface(bus=ctx.bus,
                           host=ctx.options.socket_host,
                           port=ctx.options.socket_port)
