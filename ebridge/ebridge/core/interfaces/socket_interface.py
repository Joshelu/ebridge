"""
Interfaz de socket TCP.

Acepta conexiones de clientes TCP (telnet, netcat, scripts externos…).

Flujo de datos:
  Cliente → socket → bus.send_to_serial()   (el cliente envía comandos)
  bus.dispatch_rx() → socket → Cliente       (el serie responde)

Cada cliente conectado recibe una copia de todos los datos que llegan
del puerto serie, y puede enviar datos que serán reenviados al serie.

Uso:
  nc 127.0.0.1 5000
  telnet 127.0.0.1 5000
"""

import asyncio
import logging
from typing import List, Tuple

from .base import BaseInterface
from ..message_bus import MessageBus, Message, MessageSource
from ebridge._ansi import cprint

log = logging.getLogger(__name__)

# Prefijo visible para el cliente socket (indica que vienen datos del serie)
RX_PREFIX = ""


class SocketInterface(BaseInterface):
    """
    Servidor TCP que hace de puente bidireccional con el puerto serie.
    """

    def __init__(self, bus: MessageBus, host: str = "0.0.0.0", port: int = 5000):
        self._bus = bus
        self._host = host
        self._port = port
        # Lista de writers de clientes conectados
        self._clients: List[asyncio.StreamWriter] = []
        self._clients_lock = asyncio.Lock()
        # Suscripción al canal RX para reenviar al socket
        self._rx_queue: asyncio.Queue[Message] = bus.create_rx_subscriber()

    # ------------------------------------------------------------------
    # Gestión de clientes
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Manejador de cada conexión entrante."""
        addr = writer.get_extra_info("peername", ("?", "?"))
        addr_str = f"{addr[0]}:{addr[1]}"
        cprint(f"\033[94m[SOCKET] Cliente conectado: {addr_str}\033[0m")

        async with self._clients_lock:
            self._clients.append(writer)

        # Mensaje de bienvenida
        try:
            writer.write(b"[eBridge] Conectado.\r\n")
            await writer.drain()
        except Exception:
            pass

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break  # Conexión cerrada por el cliente
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    msg = Message(
                        source=MessageSource.SOCKET_RX,
                        data=text,
                        metadata={"client": addr_str},
                    )
                    await self._bus.send_to_serial(msg)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as e:
            log.error("Error con cliente %s: %s", addr_str, e)
        finally:
            async with self._clients_lock:
                if writer in self._clients:
                    self._clients.remove(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            cprint(f"\033[94m[SOCKET] Cliente desconectado: {addr_str}\033[0m")

    # ------------------------------------------------------------------
    # Broadcast de mensajes RX a todos los clientes
    # ------------------------------------------------------------------

    async def _broadcast_loop(self) -> None:
        """Reenvía mensajes del serie a todos los clientes conectados."""
        while True:
            msg: Message = await self._rx_queue.get()
            data = (RX_PREFIX + msg.data + "\r\n").encode("utf-8")

            async with self._clients_lock:
                dead: List[asyncio.StreamWriter] = []
                for writer in self._clients:
                    try:
                        writer.write(data)
                        await writer.drain()
                    except Exception:
                        dead.append(writer)
                for w in dead:
                    self._clients.remove(w)

    # ------------------------------------------------------------------
    # Tarea asyncio principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        cprint(f"\033[94m[SOCKET] Escuchando en {self._host}:{self._port}\033[0m"
        )
        try:
            async with server:
                await asyncio.gather(
                    server.serve_forever(),
                    self._broadcast_loop(),
                )
        except asyncio.CancelledError:
            pass
        finally:
            cprint("\033[93m[SOCKET] Servidor cerrado.\033[0m")
