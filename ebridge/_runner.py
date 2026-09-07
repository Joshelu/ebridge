# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
API programática de eBridge.

Permite integrar el terminal en otro proyecto Python sin pasar por la línea de
comandos::

    import asyncio
    from ebridge import run_terminal

    asyncio.run(run_terminal(
        device      = "mi_dispositivo",
        port        = "/dev/ttyUSB0",
        socket_port = 5000,
        log_file    = "sesion.log",
    ))

El runner no sabe qué interfaces existen: pide al registro que construya las
que apliquen y las arranca a todas por igual (ver
:mod:`ebridge.core.registry`).  Por eso añadir una interfaz nueva no obliga a
tocar este archivo.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ebridge import ui
from ebridge._loader import load_device_config
from ebridge.core import interfaces  # noqa: F401  (registra las interfaces)
from ebridge.core.automation_engine import AutomationEngine
from ebridge.core.config import DeviceConfig
from ebridge.core.highlighter import Highlighter
from ebridge.core.message_bus import MessageBus
from ebridge.core.register_linker import RegisterLinker
from ebridge.core.registry import BuildContext, RuntimeOptions, build_all

__all__ = ["run_terminal", "run_device"]


async def run_terminal(
    device:      str,
    port:        str,
    socket_port: int           = 5000,
    socket_host: str           = "0.0.0.0",
    no_socket:   bool          = False,
    log_file:    Optional[str] = None,
    verbose:     bool          = False,
) -> None:
    """Ejecuta el terminal serie de forma asíncrona.

    Args:
        device:      Nombre del dispositivo. Se busca, en este orden, como
                     ``devices/<device>.yaml`` en el directorio de trabajo y
                     entre las configuraciones incluidas en el paquete.
        port:        Puerto serie (``/dev/ttyUSB0``, ``COM3``…).
        socket_port: Puerto TCP del bridge.
        socket_host: Dirección de escucha del bridge.
        no_socket:   Si es True, no se levanta el servidor TCP.
        log_file:    Fichero de log de sesión (None = desactivado).
        verbose:     Activa el logging interno detallado.

    Raises:
        DeviceConfigError: si no se encuentra o no se puede leer el YAML.
        ConfigError: si la configuración tiene valores inválidos.
    """
    if verbose:
        import logging
        logging.getLogger("ebridge").setLevel(logging.DEBUG)

    config = load_device_config(device)
    options = RuntimeOptions(
        port=port,
        socket_host=socket_host,
        socket_port=socket_port,
        no_socket=no_socket,
        log_file=log_file,
        verbose=verbose,
    )
    await run_device(config, options)


async def run_device(config: DeviceConfig, options: RuntimeOptions) -> None:
    """Arranca una sesión con una configuración ya cargada.

    Separado de :func:`run_terminal` para poder construir la configuración a
    mano (tests, o un programa que la genere en lugar de leerla de un YAML).
    """
    bus = MessageBus()
    ctx = BuildContext(
        bus=bus,
        config=config,
        options=options,
        highlighter=Highlighter(config.highlights),
        register_linker=RegisterLinker(config.register_links),
        automation_engine=AutomationEngine(bus, config.automations),
    )

    built = build_all(ctx)
    if not built:
        ui.error("SYS", "No hay ninguna interfaz activa; no hay nada que ejecutar.")
        return

    tasks: dict[asyncio.Task, tuple[str, object]] = {}
    primary: Optional[asyncio.Task] = None
    for name, instance, is_primary in built:
        task = asyncio.create_task(instance.run(), name=name)
        tasks[task] = (name, instance)
        if is_primary:
            primary = task

    # La interfaz primaria (el terminal) gobierna la vida del programa. Si no
    # hay ninguna, cualquier interfaz que termine cierra la sesión, que es el
    # comportamiento razonable para un bridge sin terminal.
    try:
        await asyncio.wait(
            [primary] if primary else list(tasks),
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        await _shutdown(tasks)


async def _shutdown(tasks: dict) -> None:
    """Cancela las tareas pendientes y llama a ``stop()`` en cada interfaz."""
    for task in tasks:
        task.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for (task, (name, instance)), result in zip(tasks.items(), results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            ui.error(name.upper(), f"La interfaz ha fallado: {type(result).__name__}: {result}")
        try:
            await instance.stop()
        except Exception as e:                        # pragma: no cover
            ui.warn(name.upper(), f"Error al cerrar: {e}")
