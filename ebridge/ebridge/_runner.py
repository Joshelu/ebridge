"""
API programática de ebridge.

Permite integrar el terminal en otro proyecto Python sin pasar por
la línea de comandos.

Ejemplo:
    import asyncio
    from ebridge import run_terminal

    asyncio.run(run_terminal(
        device    = "mi_dispositivo",
        port      = "/dev/ttyUSB0",
        socket_port = 5000,
        log_file  = "sesion.log",
    ))
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ebridge._loader import load_device_config
from ebridge.core.message_bus import MessageBus
from ebridge.core.highlighter import Highlighter
from ebridge.core.logger import SessionLogger
from ebridge.core.automation_engine import AutomationEngine
from ebridge.core.interfaces.serial_interface import SerialInterface
from ebridge.core.interfaces.socket_interface import SocketInterface
from ebridge.core.interfaces.terminal_interface import TerminalInterface


async def run_terminal(
    device:      str,
    port:        str,
    socket_port: int            = 5000,
    socket_host: str            = "0.0.0.0",
    no_socket:   bool           = False,
    log_file:    Optional[str]  = None,
    verbose:     bool           = False,
) -> None:
    """
    Ejecuta el terminal serie de forma asíncrona.

    Args:
        device:      Nombre del dispositivo. Se busca en este orden:
                     1. ``devices/<device>.yaml`` en el directorio de trabajo
                     2. Configuraciones incluidas en el paquete
        port:        Puerto serie (``/dev/ttyUSB0``, ``COM3``…)
        socket_port: Puerto TCP del bridge (default 5000)
        socket_host: Dirección de escucha del bridge (default ``0.0.0.0``)
        no_socket:   Si es True, deshabilita el servidor TCP
        log_file:    Ruta del fichero de log de sesión (None = desactivado)
        verbose:     Activa el logging interno detallado
    """
    if verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_device_config(device)

    bus              = MessageBus()
    highlighter      = Highlighter(config.get("highlights", []))
    automation_engine = AutomationEngine(bus, config.get("automations", {}))

    serial_iface   = SerialInterface(bus=bus, port=port,
                                     config=config.get("serial", {}))
    terminal_iface = TerminalInterface(bus=bus, highlighter=highlighter,
                                       automation_engine=automation_engine,
                                       device_name=device)
    socket_iface: Optional[SocketInterface] = None
    if not no_socket:
        socket_iface = SocketInterface(bus=bus, host=socket_host,
                                       port=socket_port)

    logger: Optional[SessionLogger] = None
    if log_file:
        logger = SessionLogger(log_file)

    tasks = [
        asyncio.create_task(terminal_iface.run(), name="terminal"),
        asyncio.create_task(serial_iface.run(),   name="serial"),
    ]
    if socket_iface:
        tasks.append(asyncio.create_task(socket_iface.run(), name="socket"))
    if logger:
        tasks.append(asyncio.create_task(logger.run(bus.log_queue), name="logger"))

    # El terminal rige la vida del programa: cuando el usuario sale se cancela todo
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
