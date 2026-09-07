# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Logger de sesión.

Consume el ``log_queue`` del MessageBus y escribe cada mensaje en un fichero de
texto, sin colores ANSI, con la fuente y (opcionalmente) marca de tiempo.

La ruta del fichero sale de combinar lo que se pide en la CLI (``--log``) con
``log.directory`` del YAML del dispositivo; ver
:meth:`ebridge.core.config.LogConfig.resolve_path`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from ebridge import ui
from ebridge.core.config import LogConfig
from ebridge.core.message_bus import Message, MessageSource

__all__ = ["SessionLogger", "SOURCE_LABELS"]


# Etiquetas legibles para cada fuente. El ancho fijo mantiene el fichero
# alineado en columnas y fácil de filtrar con grep.
SOURCE_LABELS: dict = {
    MessageSource.SERIAL_RX:  "<<< SERIAL",
    MessageSource.SERIAL_TX:  ">>> SERIAL",
    MessageSource.TERMINAL:   ">>> TERMINAL",
    MessageSource.SOCKET_RX:  ">>> SOCKET",
    MessageSource.AUTOMATION: "    AUTO",
    MessageSource.SYSTEM:     "    SYSTEM",
}

_LABEL_WIDTH = 14
_RULE = "=" * 70


class SessionLogger:
    """Escribe todos los mensajes del bus en un fichero de log.

    Uso:
        logger = SessionLogger("sesion.log", LogConfig(directory="C:/Logs"))
        await logger.run(bus.log_queue)   # bloquea hasta la cancelación
    """

    def __init__(self, log_file: str, config: LogConfig | None = None):
        self.config = config or LogConfig()
        self.filepath: Path = self.config.resolve_path(log_file)

    def _format(self, msg: Message) -> str:
        label = SOURCE_LABELS.get(msg.source, msg.source.value)
        # El texto llega sin colorear (el resaltado se aplica solo al pintar en
        # el terminal), pero una automatización podría enviar ANSI: se limpia
        # para que el fichero quede en texto plano.
        data = ui.strip_ansi(msg.data)
        if self.config.timestamp:
            ts = datetime.fromtimestamp(msg.timestamp).strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
            return f"[{ts}] {label:{_LABEL_WIDTH}s}  {data}\n"
        return f"{label:{_LABEL_WIDTH}s}  {data}\n"

    async def run(self, log_queue: asyncio.Queue) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"\n{_RULE}\nSession started: {datetime.now().isoformat()}\n{_RULE}\n")
            f.flush()
            try:
                while True:
                    msg: Message = await log_queue.get()
                    f.write(self._format(msg))
                    f.flush()
            except asyncio.CancelledError:
                f.write(f"\n{_RULE}\nSession ended: {datetime.now().isoformat()}\n{_RULE}\n")
                f.flush()
                raise
