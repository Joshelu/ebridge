"""
Logger de sesión.

Consume el log_queue del MessageBus y escribe cada mensaje en un
fichero de texto, sin colores ANSI, con timestamp y fuente.
"""

import asyncio
from datetime import datetime
from pathlib import Path

from .message_bus import MessageBus, Message, MessageSource


# Etiquetas legibles para cada fuente
SOURCE_LABELS: dict = {
    MessageSource.SERIAL_RX:  "<<< SERIAL",
    MessageSource.SERIAL_TX:  ">>> SERIAL",
    MessageSource.TERMINAL:   ">>> TERMINAL",
    MessageSource.SOCKET_RX:  ">>> SOCKET",
    MessageSource.AUTOMATION: "    AUTO",
    MessageSource.SYSTEM:     "    SYSTEM",
}


class SessionLogger:
    """
    Escribe todos los mensajes del bus en un fichero de log.

    Uso:
        logger = SessionLogger("sesion.log")
        await logger.run(bus.log_queue)   # bloquea hasta cancelación
    """

    def __init__(self, filepath: str, config: dict):
        directory = config.get("directory", None)
        if directory != "":
            self.filepath = Path(directory + filepath)
        else:
            self.filepath = Path(filepath)
        self.config = config

    async def run(self, log_queue: asyncio.Queue) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(self.filepath, "a", encoding="utf-8") as f:
            header = (
                f"\n{'=' * 70}\n"
                f"Session started: {datetime.now().isoformat()}\n"
                f"{'=' * 70}\n"
            )
            f.write(header)
            f.flush()

            try:
                while True:
                    msg: Message = await log_queue.get()
                    label = SOURCE_LABELS.get(msg.source, msg.source.value)
                    if self.config.get("timestamp", False) == True:
                        ts = datetime.fromtimestamp(msg.timestamp).strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
                        line = f"[{ts}] {label:14s}  {msg.data}\n"
                    else:
                        line = f"{label:14s}  {msg.data}\n"
                    f.write(line)
                    f.flush()
            except asyncio.CancelledError:
                header = (
                    f"\n{'=' * 70}\n"
                    f"\nSession ended: {datetime.now().isoformat()}\n"
                    f"{'=' * 70}\n"
                )
                f.write(header)
                f.flush()
