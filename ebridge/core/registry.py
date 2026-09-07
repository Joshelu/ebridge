# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Registro de interfaces.

El README prometía "añadir interfaces nuevas (MQTT, Bluetooth, HTTP…) sin
modificar el código existente", pero en la práctica hacía falta tocar el
runner, el parser de la CLI y la lista de tareas.  Este registro cierra ese
hueco: una interfaz nueva es **un módulo con un decorador**.

Cómo añadir una interfaz
------------------------
1. Crea ``ebridge/core/interfaces/mqtt_interface.py``::

       from ebridge.core.interfaces.base import BaseInterface
       from ebridge.core.registry import BuildContext, register

       @register("mqtt")
       def _build(ctx: BuildContext):
           # Devolver None desactiva la interfaz para esta sesión.
           if not ctx.config.mqtt.enabled:
               return None
           return MqttInterface(bus=ctx.bus, config=ctx.config.mqtt)

2. Añade la línea de import en ``ebridge/core/interfaces/__init__.py``.

No hay que tocar ni el runner ni la CLI.  Se importa explícitamente en lugar
de auto-descubrir el directorio para que el orden de arranque sea
determinista y los errores de importación salgan a la cara en vez de
convertirse en una interfaz que "no aparece".

Interfaz primaria
-----------------
Una interfaz marcada con ``primary=True`` gobierna la vida del programa:
cuando termina, el runner cancela todo lo demás.  El terminal es la primaria
por defecto (cuando el usuario sale, se cierra la sesión entera).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # evita un ciclo de importación con el paquete interfaces
    from ebridge.core.automation_engine import AutomationEngine
    from ebridge.core.config import DeviceConfig
    from ebridge.core.highlighter import Highlighter
    from ebridge.core.interfaces.base import BaseInterface
    from ebridge.core.message_bus import MessageBus
    from ebridge.core.register_linker import RegisterLinker

__all__ = ["RuntimeOptions", "BuildContext", "register", "build_all", "available"]


@dataclass(frozen=True)
class RuntimeOptions:
    """Opciones que vienen de la línea de comandos, no del YAML."""

    port: str
    socket_host: str = "0.0.0.0"
    socket_port: int = 5000
    no_socket: bool = False
    log_file: Optional[str] = None
    verbose: bool = False


@dataclass(frozen=True)
class BuildContext:
    """Todo lo que una factoría de interfaz puede necesitar para construirse."""

    bus: "MessageBus"
    config: "DeviceConfig"
    options: RuntimeOptions
    highlighter: "Highlighter"
    register_linker: "RegisterLinker"
    automation_engine: "AutomationEngine"


InterfaceFactory = Callable[[BuildContext], Optional["BaseInterface"]]


@dataclass(frozen=True)
class _Entry:
    name: str
    factory: InterfaceFactory
    primary: bool
    order: int


_REGISTRY: Dict[str, _Entry] = {}
_counter = 0


def register(name: str, *, primary: bool = False) -> Callable[[InterfaceFactory], InterfaceFactory]:
    """Decorador que registra la factoría de una interfaz bajo `name`.

    La factoría recibe un :class:`BuildContext` y devuelve una instancia de
    ``BaseInterface``, o ``None`` si la interfaz no aplica en esta sesión
    (por ejemplo, el socket con ``--no-socket``).
    """
    def decorator(factory: InterfaceFactory) -> InterfaceFactory:
        global _counter
        if name in _REGISTRY:
            raise ValueError(f"Ya hay una interfaz registrada como '{name}'.")
        _REGISTRY[name] = _Entry(name=name, factory=factory, primary=primary, order=_counter)
        _counter += 1
        return factory
    return decorator


def available() -> List[str]:
    """Nombres de las interfaces registradas, en orden de registro."""
    return [e.name for e in sorted(_REGISTRY.values(), key=lambda e: e.order)]


def build_all(ctx: BuildContext) -> List[Tuple[str, "BaseInterface", bool]]:
    """Construye todas las interfaces aplicables.

    Returns:
        Lista de ``(nombre, instancia, es_primaria)``.  Las factorías que
        devuelven ``None`` no aparecen.
    """
    built: List[Tuple[str, "BaseInterface", bool]] = []
    for entry in sorted(_REGISTRY.values(), key=lambda e: e.order):
        instance = entry.factory(ctx)
        if instance is not None:
            built.append((entry.name, instance, entry.primary))
    return built


def _reset_for_tests() -> None:
    """Vacía el registro. Solo para los tests."""
    global _counter
    _REGISTRY.clear()
    _counter = 0
