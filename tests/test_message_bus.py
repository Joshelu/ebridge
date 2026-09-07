# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests del bus de mensajes."""

from __future__ import annotations

import asyncio

from ebridge.core.message_bus import Message, MessageBus, MessageSource


def rx(data: str) -> Message:
    return Message(source=MessageSource.SERIAL_RX, data=data)


async def test_every_subscriber_gets_a_copy():
    bus = MessageBus()
    a, b = bus.create_rx_subscriber(), bus.create_rx_subscriber()
    await bus.dispatch_rx(rx("hola"))
    assert (await a.get()).data == "hola"
    assert (await b.get()).data == "hola"


async def test_dispatch_also_feeds_the_log():
    bus = MessageBus()
    await bus.dispatch_rx(rx("hola"))
    assert (await bus.log_queue.get()).data == "hola"


async def test_send_to_serial_feeds_tx_and_log():
    bus = MessageBus()
    await bus.send_to_serial(Message(source=MessageSource.TERMINAL, data="reset"))
    assert (await bus.tx_queue.get()).data == "reset"
    # El log conserva la fuente original, más informativa que SERIAL_TX.
    logged = await bus.log_queue.get()
    assert logged.source is MessageSource.TERMINAL


async def test_removed_subscriber_stops_receiving():
    bus = MessageBus()
    q = bus.create_rx_subscriber()
    bus.remove_rx_subscriber(q)
    await bus.dispatch_rx(rx("hola"))
    assert q.empty()


async def test_removing_a_subscriber_during_dispatch_is_safe():
    """Regresión: se recorría la lista de suscriptores mientras se hacía await.

    Una automatización que termina justo en ese hueco llama a
    remove_rx_subscriber() y mutaba la lista en plena iteración.
    """
    bus = MessageBus()
    victim = bus.create_rx_subscriber()
    other = bus.create_rx_subscriber()

    async def unsubscribe_soon():
        await asyncio.sleep(0)
        bus.remove_rx_subscriber(victim)

    await asyncio.gather(bus.dispatch_rx(rx("hola")), unsubscribe_soon())
    assert (await other.get()).data == "hola"
    assert bus.subscriber_count == 1


async def test_double_removal_is_harmless():
    bus = MessageBus()
    q = bus.create_rx_subscriber()
    bus.remove_rx_subscriber(q)
    bus.remove_rx_subscriber(q)     # no debe lanzar
    assert bus.subscriber_count == 0
