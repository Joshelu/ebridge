# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Interfaz de puerto serie.

pyserial es bloqueante, así que la E/S vive en dos hilos conectados al event
loop de asyncio mediante colas thread-safe:

  hilo lector   → lee bytes del serie → bus.dispatch_rx()  (vía run_coroutine_threadsafe)
  run() (async) → consume bus.tx_queue → cola thread-safe → hilo escritor → serie

Configuración: sección ``serial:`` del YAML, ya validada en
:class:`ebridge.core.config.SerialConfig`.

Reconexión
----------
Con ``serial.reconnect: true``, ``run()`` actúa de supervisor: cuando el hilo
lector detecta que el puerto ha desaparecido (desenchufar el USB, reinicio del
dispositivo), cierra el enlace y reintenta abrirlo cada
``serial.reconnect_delay`` segundos hasta conseguirlo o hasta que se cierre la
sesión.  Mientras está caído, lo que se escriba en el terminal se queda en la
cola de TX y se envía en cuanto vuelve el puerto.

Está desactivado por defecto para no cambiar el comportamiento histórico.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Optional

import serial

from ebridge import ui
from ebridge.core.config import SerialConfig
from ebridge.core.interfaces.base import BaseInterface
from ebridge.core.message_bus import Message, MessageBus, MessageSource
from ebridge.core.registry import BuildContext, register

__all__ = ["SerialInterface"]

log = logging.getLogger(__name__)

# Mapas de los valores del YAML a las constantes de pyserial. La validación de
# que el valor está en el conjunto permitido ya la ha hecho SerialConfig.
_PARITY = {
    "N": serial.PARITY_NONE,
    "E": serial.PARITY_EVEN,
    "O": serial.PARITY_ODD,
    "M": serial.PARITY_MARK,
    "S": serial.PARITY_SPACE,
}
_BYTESIZE = {
    5: serial.FIVEBITS,
    6: serial.SIXBITS,
    7: serial.SEVENBITS,
    8: serial.EIGHTBITS,
}
_STOPBITS = {
    1:   serial.STOPBITS_ONE,
    1.5: serial.STOPBITS_ONE_POINT_FIVE,
    2:   serial.STOPBITS_TWO,
}

# Señal de parada para el hilo escritor.
_SENTINEL = object()


class SerialInterface(BaseInterface):
    """Gestiona la comunicación con el puerto serie."""

    def __init__(self, bus: MessageBus, port: str, config: SerialConfig):
        self._bus = bus
        self._port = port
        self._cfg = config
        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._write_q: "queue.Queue[object]" = queue.Queue()
        self._threads: list[threading.Thread] = []
        # Se activa cuando el hilo lector detecta que el puerto ha caído; la
        # pone el hilo con loop.call_soon_threadsafe().
        self._link_lost: Optional[asyncio.Event] = None
        # True en cuanto alguien pide cerrar: corta el bucle de reconexión.
        self._closing = False
        # Mensaje sacado de la cola de TX pero todavía no escrito, porque el
        # enlace cayó justo entonces. Se envía al reconectar.
        self._pending_tx: Optional[Message] = None

    # ------------------------------------------------------------------
    # Apertura del puerto
    # ------------------------------------------------------------------

    @property
    def _eol(self) -> bytes:
        """Fin de línea que se añade a cada envío, ya codificado."""
        return self._cfg.eol.encode(self._cfg.encoding)

    def _open_serial(self) -> serial.Serial:
        cfg = self._cfg
        return serial.Serial(
            port=self._port,
            baudrate=cfg.baudrate,
            bytesize=_BYTESIZE[cfg.bytesize],
            parity=_PARITY[cfg.parity.upper()],
            stopbits=_STOPBITS[cfg.stopbits],
            timeout=cfg.timeout,
            xonxoff=cfg.xonxoff,
            rtscts=cfg.rtscts,
            dsrdtr=cfg.dsrdtr,
        )

    # ------------------------------------------------------------------
    # Hilo lector: serie → asyncio
    # ------------------------------------------------------------------

    def _reader_thread(self, loop: asyncio.AbstractEventLoop) -> None:
        """Lee bytes del serie, los parte en líneas y los despacha al bus."""
        buffer = b""
        while self._running:
            try:
                waiting = self._ser.in_waiting
                chunk = self._ser.read(waiting if waiting > 0 else 1)
                if not chunk:
                    continue
                buffer += chunk

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode(self._cfg.encoding, errors="replace").strip()
                    if text:
                        self._dispatch(loop, MessageSource.SERIAL_RX, text)
            except (serial.SerialException, OSError) as e:
                if self._running:
                    log.error("Error de lectura serie: %s", e)
                    self._dispatch(loop, MessageSource.SYSTEM,
                                   f"[ERROR] Puerto serie: {e}")
                    self._signal_link_lost(loop)
                break
            except Exception:
                if self._running:
                    log.exception("Error inesperado en el hilo lector")
                    self._signal_link_lost(loop)
                break

    def _signal_link_lost(self, loop: asyncio.AbstractEventLoop) -> None:
        """Avisa al supervisor, desde el hilo lector, de que el enlace ha caído."""
        event = self._link_lost
        if event is None:
            return
        try:
            loop.call_soon_threadsafe(event.set)
        except RuntimeError:
            # El event loop ya está cerrado: estamos apagando, no es un error.
            pass

    def _dispatch(self, loop: asyncio.AbstractEventLoop,
                  source: MessageSource, text: str) -> None:
        """Publica en el bus desde un hilo que no es el del event loop."""
        try:
            asyncio.run_coroutine_threadsafe(
                self._bus.dispatch_rx(Message(source=source, data=text)), loop
            )
        except RuntimeError:
            # El event loop ya se ha cerrado: estamos apagando, no es un error.
            pass

    # ------------------------------------------------------------------
    # Hilo escritor: cola thread-safe → serie
    # ------------------------------------------------------------------

    def _writer_thread(self) -> None:
        """Toma datos de la cola thread-safe y los escribe al serie.

        El troceado (``tx_chunk_size``) existe para dispositivos con un buffer
        de recepción pequeño, que pierden bytes si se les manda una ráfaga
        larga de golpe.
        """
        chunk_size = self._cfg.tx_chunk_size
        chunk_delay = self._cfg.tx_chunk_delay

        while self._running:
            try:
                data = self._write_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if data is _SENTINEL:
                break

            try:
                if chunk_size > 0:
                    for i in range(0, len(data), chunk_size):
                        self._ser.write(data[i:i + chunk_size])
                        self._ser.flush()
                        if i + chunk_size < len(data):
                            time.sleep(chunk_delay)
                else:
                    self._ser.write(data)
                    self._ser.flush()
            except serial.SerialException as e:
                if self._running:
                    log.error("Error de escritura serie: %s", e)
            except Exception:
                if self._running:
                    log.exception("Error inesperado en el hilo escritor")

    # ------------------------------------------------------------------
    # Tarea asyncio principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Supervisa el enlace: lo abre, lo bombea y, si procede, lo reabre."""
        loop = asyncio.get_running_loop()
        first = True
        try:
            while not self._closing:
                if not await self._open_link(loop, reconnecting=not first):
                    return                      # sin puerto y sin reconexión
                first = False
                try:
                    await self._pump_tx()       # vuelve cuando cae el enlace
                finally:
                    await self._close_link()

                if self._closing or not self._cfg.reconnect:
                    return
                ui.warn("SERIAL", f"Enlace perdido. Reintentando en "
                                  f"{self._cfg.reconnect_delay}s…")
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()

    # -- apertura ---------------------------------------------------------

    async def _open_link(self, loop: asyncio.AbstractEventLoop, *,
                         reconnecting: bool = False) -> bool:
        """Abre el puerto y arranca los hilos. Reintenta si hay reconexión.

        Args:
            reconnecting: True si se está recuperando un enlace perdido, en
                cuyo caso el aviso se publica en el bus para que llegue también
                al log de sesión y a los clientes del bridge TCP.

        Returns:
            True si el enlace está en marcha; False si no se pudo abrir y no
            hay que reintentar.
        """
        announced = False
        while not self._closing:
            try:
                self._ser = self._open_serial()
            except (serial.SerialException, OSError) as e:
                if not self._cfg.reconnect:
                    ui.error("SERIAL", f"No se pudo abrir '{self._port}': {e}")
                    return False
                if not announced:
                    # Solo se avisa del primer fallo: con reintentos cada pocos
                    # segundos, repetirlo llenaría el terminal de ruido.
                    ui.warn("SERIAL", f"No se pudo abrir '{self._port}': {e}. "
                                      f"Reintentando cada {self._cfg.reconnect_delay}s…")
                    announced = True
                await asyncio.sleep(self._cfg.reconnect_delay)
                continue

            self._running = True
            self._link_lost = asyncio.Event()
            self._threads = [
                threading.Thread(target=self._reader_thread, args=(loop,),
                                 daemon=True, name="serial-reader"),
                threading.Thread(target=self._writer_thread,
                                 daemon=True, name="serial-writer"),
            ]
            for t in self._threads:
                t.start()

            verb = "reabierto" if reconnecting else "abierto"
            message = f"Puerto {verb}: {self._port} @ {self._cfg.baudrate} baudios"
            if reconnecting:
                # Publicar en el bus en vez de imprimir: así la recuperación
                # llega al terminal, al log de sesión y a los clientes del
                # bridge TCP, igual que la caída (que publica el hilo lector).
                await self._bus.dispatch_rx(
                    Message(source=MessageSource.SYSTEM, data=f"[SERIAL] {message}")
                )
            else:
                ui.ok("SERIAL", message)
            return True
        return False

    # -- bombeo de TX -----------------------------------------------------

    async def _pump_tx(self) -> None:
        """Pasa la cola de TX al hilo escritor hasta que caiga el enlace.

        Se espera a la vez por un mensaje nuevo y por la señal de enlace caído.
        Los mensajes encolados mientras el puerto está caído no se pierden: se
        quedan en ``bus.tx_queue`` y salen al reconectar.
        """
        assert self._link_lost is not None
        lost = asyncio.ensure_future(self._link_lost.wait())
        try:
            while True:
                if self._pending_tx is None:
                    get = asyncio.ensure_future(self._bus.tx_queue.get())
                    try:
                        await asyncio.wait({get, lost},
                                           return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        # El mensaje puede haber llegado en el mismo instante en
                        # que caía el enlace. Si ya lo tenemos, se guarda para
                        # enviarlo al reconectar en lugar de descartarlo al
                        # cancelar la espera.
                        if get.done() and not get.cancelled() and get.exception() is None:
                            self._pending_tx = get.result()
                        else:
                            get.cancel()

                if self._link_lost.is_set():
                    return          # _pending_tx sobrevive a la reconexión

                msg: Message = self._pending_tx
                self._pending_tx = None
                payload = msg.data.encode(self._cfg.encoding) + self._eol
                log.debug("[TX-QUEUE] Encolando %d bytes: %r", len(payload), payload)
                self._write_q.put(payload)
        finally:
            lost.cancel()

    # -- cierre -----------------------------------------------------------

    async def _close_link(self) -> None:
        """Para los hilos y cierra el puerto, dejándolo listo para reabrirse."""
        if not self._running and self._ser is None:
            return
        self._running = False
        self._write_q.put(_SENTINEL)
        for t in self._threads:
            t.join(timeout=1)
        self._threads = []
        self._link_lost = None
        if self._ser is not None:
            try:
                if self._ser.is_open:
                    self._ser.close()
            except (serial.SerialException, OSError):
                # El puerto ya no existe (USB desenchufado): cerrarlo puede
                # fallar y no hay nada que hacer al respecto.
                pass
            self._ser = None
            ui.note("SERIAL", "Puerto cerrado.")

    async def stop(self) -> None:
        """Cierra el enlace y corta la reconexión. Idempotente."""
        self._closing = True
        await self._close_link()


@register("serial")
def _build(ctx: BuildContext) -> SerialInterface:
    return SerialInterface(bus=ctx.bus, port=ctx.options.port, config=ctx.config.serial)
