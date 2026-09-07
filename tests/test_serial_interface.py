# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests de la interfaz de puerto serie, sobre todo de la reconexión."""

from __future__ import annotations

import asyncio
import threading

import pytest
import serial

from ebridge.core.config import SerialConfig
from ebridge.core.interfaces.serial_interface import SerialInterface
from ebridge.core.message_bus import Message, MessageBus, MessageSource


class FakeSerial:
    """Puerto serie de mentira, con un interruptor para 'desenchufarlo'."""

    def __init__(self) -> None:
        self.is_open = True
        self.written = bytearray()
        self.close_calls = 0
        self._dropped = threading.Event()
        self._lock = threading.Lock()

    # -- API que usa SerialInterface --------------------------------------

    @property
    def in_waiting(self) -> int:
        return 0

    def read(self, size: int) -> bytes:
        # Espera un poco en vez de girar en vacío; si el puerto se ha
        # "desenchufado", falla igual que lo haría pyserial.
        if self._dropped.wait(0.01):
            raise serial.SerialException("El dispositivo no está conectado")
        return b""

    def write(self, data: bytes) -> int:
        if self._dropped.is_set():
            # Un puerto desenchufado falla también al escribir. Así el test
            # detecta si algo intenta escribir por el enlace muerto.
            raise serial.SerialException("El dispositivo no está conectado")
        with self._lock:
            self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False

    # -- control desde el test --------------------------------------------

    def drop(self) -> None:
        """Simula que se desenchufa el USB."""
        self._dropped.set()

    def sent(self) -> bytes:
        with self._lock:
            return bytes(self.written)


class PortFactory:
    """Sustituye a ``_open_serial``: entrega puertos falsos, o falla.

    Se instala con ``monkeypatch.setattr(SerialInterface, "_open_serial", factory)``.
    Como la instancia no es un descriptor, ``self._open_serial()`` la invoca sin
    pasar el `self` de la interfaz: por eso ``__call__`` no toma argumentos.
    """

    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.opened: list[FakeSerial] = []
        self.attempts = 0
        # Mientras esté cerrada, cualquier intento de abrir falla. Permite al
        # test mantener el enlace caído el tiempo que necesite.
        self.gate = threading.Event()
        self.gate.set()

    def __call__(self) -> FakeSerial:
        self.attempts += 1
        if self.attempts <= self.failures or not self.gate.is_set():
            raise serial.SerialException("No se encuentra el puerto")
        port = FakeSerial()
        self.opened.append(port)
        return port


async def wait_until(condition, timeout: float = 3.0) -> None:
    """Espera a que `condition()` sea cierta, o falla el test."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condición no cumplida a tiempo")
        await asyncio.sleep(0.01)


async def start(iface: SerialInterface) -> asyncio.Task:
    return asyncio.create_task(iface.run(), name="serial-test")


async def shutdown(iface: SerialInterface, task: asyncio.Task) -> None:
    await iface.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Sin reconexión: comportamiento histórico
# ---------------------------------------------------------------------------

async def test_open_failure_without_reconnect_reports_and_gives_up(monkeypatch, capsys):
    factory = PortFactory(failures=99)
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    iface = SerialInterface(MessageBus(), "COM_TEST", SerialConfig())

    await asyncio.wait_for(iface.run(), timeout=2)

    assert factory.attempts == 1
    assert "No se pudo abrir" in capsys.readouterr().out


async def test_link_loss_without_reconnect_ends_the_interface(monkeypatch):
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    iface = SerialInterface(MessageBus(), "COM_TEST", SerialConfig())
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    factory.opened[0].drop()

    await asyncio.wait_for(task, timeout=3)
    assert factory.attempts == 1        # no reintenta


# ---------------------------------------------------------------------------
# Con reconexión
# ---------------------------------------------------------------------------

async def test_retries_until_the_port_appears(monkeypatch, capsys):
    factory = PortFactory(failures=3)
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    iface = SerialInterface(MessageBus(), "COM_TEST",
                            SerialConfig(reconnect=True, reconnect_delay=0.01))
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    out = capsys.readouterr().out
    assert "Reintentando" in out
    # El aviso de fallo sale una sola vez, no en cada reintento.
    assert out.count("No se pudo abrir") == 1

    await shutdown(iface, task)


async def test_reopens_the_port_after_a_link_loss(monkeypatch, capsys):
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    iface = SerialInterface(MessageBus(), "COM_TEST",
                            SerialConfig(reconnect=True, reconnect_delay=0.01))
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    factory.opened[0].drop()
    await wait_until(lambda: len(factory.opened) == 2)

    assert "Enlace perdido" in capsys.readouterr().out
    await shutdown(iface, task)


async def test_link_events_reach_the_bus(monkeypatch):
    """La caída y la recuperación son mensajes de sistema, no solo texto en
    pantalla: así acaban en el log de sesión y en los clientes del socket."""
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    bus = MessageBus()
    seen = bus.create_rx_subscriber()
    iface = SerialInterface(bus, "COM_TEST",
                            SerialConfig(reconnect=True, reconnect_delay=0.01))
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    factory.opened[0].drop()
    await wait_until(lambda: len(factory.opened) == 2)

    messages = []
    while not seen.empty():
        messages.append(seen.get_nowait())
    assert all(m.source is MessageSource.SYSTEM for m in messages)
    texts = " | ".join(m.data for m in messages)
    assert "Puerto serie" in texts        # la caída
    assert "reabierto" in texts           # la recuperación

    await shutdown(iface, task)


async def test_messages_queued_while_down_are_sent_on_reconnect(monkeypatch):
    """Lo que se escriba con el puerto caído no se pierde: espera en la cola.

    La compuerta de la factoría mantiene el enlace caído mientras se envía el
    mensaje, de modo que el test no depende de ninguna carrera. Como el puerto
    desenchufado también falla al escribir, si algo intentase mandarlo por el
    enlace muerto el mensaje no aparecería en el puerto nuevo.
    """
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    bus = MessageBus()
    iface = SerialInterface(bus, "COM_TEST",
                            SerialConfig(reconnect=True, reconnect_delay=0.01,
                                         eol="\n"))
    task = await start(iface)
    await wait_until(lambda: len(factory.opened) == 1)

    # Enlace caído y sin posibilidad de reabrir.
    factory.gate.clear()
    factory.opened[0].drop()
    await wait_until(lambda: factory.attempts >= 2)   # ya ha fallado un reintento

    await bus.send_to_serial(Message(source=MessageSource.TERMINAL, data="hola"))
    await asyncio.sleep(0.05)                        # nadie debe consumirlo aún
    assert len(factory.opened) == 1

    factory.gate.set()                               # vuelve el dispositivo
    await wait_until(lambda: len(factory.opened) == 2)
    await wait_until(lambda: factory.opened[1].sent() == b"hola\n")

    await shutdown(iface, task)


async def test_stop_breaks_the_reconnect_loop(monkeypatch):
    factory = PortFactory(failures=99)
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    iface = SerialInterface(MessageBus(), "COM_TEST",
                            SerialConfig(reconnect=True, reconnect_delay=0.01))
    task = await start(iface)

    await wait_until(lambda: factory.attempts >= 2)
    await iface.stop()
    await asyncio.wait_for(task, timeout=2)


async def test_the_old_port_is_closed_before_reopening(monkeypatch):
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    iface = SerialInterface(MessageBus(), "COM_TEST",
                            SerialConfig(reconnect=True, reconnect_delay=0.01))
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    first = factory.opened[0]
    first.drop()
    await wait_until(lambda: len(factory.opened) == 2)

    assert first.close_calls >= 1
    await shutdown(iface, task)


# ---------------------------------------------------------------------------
# Envío normal
# ---------------------------------------------------------------------------

async def test_eol_is_appended_to_every_message(monkeypatch):
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    bus = MessageBus()
    iface = SerialInterface(bus, "COM_TEST", SerialConfig(eol="\r\n"))
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    await bus.send_to_serial(Message(source=MessageSource.TERMINAL, data="reset"))
    await wait_until(lambda: factory.opened[0].sent() == b"reset\r\n")

    await shutdown(iface, task)


async def test_chunked_writing_splits_the_payload(monkeypatch):
    factory = PortFactory()
    monkeypatch.setattr(SerialInterface, "_open_serial", factory)
    bus = MessageBus()
    iface = SerialInterface(bus, "COM_TEST",
                            SerialConfig(eol="", tx_chunk_size=2, tx_chunk_delay=0.0))
    task = await start(iface)

    await wait_until(lambda: len(factory.opened) == 1)
    await bus.send_to_serial(Message(source=MessageSource.TERMINAL, data="abcde"))
    await wait_until(lambda: factory.opened[0].sent() == b"abcde")

    await shutdown(iface, task)


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def test_reconnect_is_disabled_by_default():
    assert SerialConfig().reconnect is False


def test_reconnect_delay_must_be_positive():
    from ebridge.errors import ConfigError
    with pytest.raises(ConfigError, match="reconnect_delay"):
        SerialConfig(reconnect_delay=0)
