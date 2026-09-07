# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests del logger de sesión."""

from __future__ import annotations

import asyncio

import pytest

from ebridge.core.config import LogConfig
from ebridge.core.logger import SessionLogger
from ebridge.core.message_bus import Message, MessageBus, MessageSource


async def run_briefly(logger: SessionLogger, queue: asyncio.Queue) -> None:
    """Arranca el logger, le deja vaciar la cola y lo cancela."""
    task = asyncio.create_task(logger.run(queue))
    # Un par de vueltas al loop bastan para que vacíe la cola.
    for _ in range(5):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_no_log_section_does_not_crash(tmp_path):
    """Regresión del TypeError: antes, sin `log:` en el YAML, esto reventaba
    en el constructor y tumbaba todo el arranque."""
    logger = SessionLogger(str(tmp_path / "sesion.log"))
    assert logger.filepath.name == "sesion.log"


async def test_writes_messages_to_the_file(tmp_path):
    bus = MessageBus()
    logger = SessionLogger(str(tmp_path / "sesion.log"), LogConfig())
    await bus.dispatch_rx(Message(source=MessageSource.SERIAL_RX, data="hola"))
    await run_briefly(logger, bus.log_queue)

    content = logger.filepath.read_text(encoding="utf-8")
    assert "Session started" in content
    assert "Session ended" in content
    assert "<<< SERIAL" in content and "hola" in content


async def test_timestamp_disabled_by_default(tmp_path):
    bus = MessageBus()
    logger = SessionLogger(str(tmp_path / "s.log"), LogConfig())
    await bus.dispatch_rx(Message(source=MessageSource.SERIAL_RX, data="hola"))
    await run_briefly(logger, bus.log_queue)
    line = [l for l in logger.filepath.read_text(encoding="utf-8").splitlines()
            if "hola" in l][0]
    assert not line.startswith("[")


async def test_timestamp_enabled_by_config(tmp_path):
    bus = MessageBus()
    logger = SessionLogger(str(tmp_path / "s.log"), LogConfig(timestamp=True))
    await bus.dispatch_rx(Message(source=MessageSource.SERIAL_RX, data="hola"))
    await run_briefly(logger, bus.log_queue)
    line = [l for l in logger.filepath.read_text(encoding="utf-8").splitlines()
            if "hola" in l][0]
    assert line.startswith("[") and "/" in line and ":" in line


async def test_ansi_is_stripped_from_the_file(tmp_path):
    bus = MessageBus()
    logger = SessionLogger(str(tmp_path / "s.log"), LogConfig())
    await bus.dispatch_rx(Message(source=MessageSource.AUTOMATION,
                                  data="\x1b[91mrojo\x1b[0m"))
    await run_briefly(logger, bus.log_queue)
    content = logger.filepath.read_text(encoding="utf-8")
    assert "rojo" in content and "\x1b[" not in content


async def test_missing_parent_directory_is_created(tmp_path):
    bus = MessageBus()
    target = tmp_path / "sub" / "carpeta" / "s.log"
    logger = SessionLogger("s.log", LogConfig(directory=str(target.parent)))
    await run_briefly(logger, bus.log_queue)
    assert target.exists()
