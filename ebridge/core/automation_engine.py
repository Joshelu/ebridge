# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Motor de automatizaciones.

Ejecuta scripts de Python como automatizaciones, con acceso controlado al bus
de mensajes.  Cada automatización recibe un :class:`AutomationContext` con:

    await ctx.send(comando)              → envía al puerto serie
    await ctx.wait_for(patron, timeout)  → espera respuesta del serie
    ctx.debug(mensaje)                   → muestra mensaje en terminal

Ejemplo de script (``automations/ponfecha.py``):

    async def run(ctx, *args):
        await ctx.send("set day 27")
        resp = await ctx.wait_for(r"OK|ERROR")
        ctx.debug(f"Respuesta día: {resp}")

Automatizaciones de varios ficheros
-----------------------------------
El directorio que contiene el script se añade a ``sys.path`` durante la carga
y el módulo se registra en ``sys.modules``.  Gracias a eso, un script puede
hacer ``import ayudante`` para traerse un módulo hermano sin tener que
parchear ``sys.path`` él mismo.

Aviso de seguridad
------------------
Una automatización es código Python que se ejecuta con los permisos del
usuario.  El YAML del dispositivo decide qué fichero se ejecuta, así que un
YAML de origen desconocido debe tratarse como código de origen desconocido.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from types import ModuleType
from typing import List, Mapping, Optional

from ebridge import ui
from ebridge.core.config import AutomationConfig
from ebridge.core.message_bus import Message, MessageBus, MessageSource
from ebridge.errors import AutomationError

__all__ = ["AutomationContext", "AutomationEngine"]

log = logging.getLogger(__name__)


class AutomationContext:
    """Contexto que se entrega a cada script de automatización.

    Interfaz de alto nivel para hablar con el puerto serie sin bloquear el
    terminal ni el socket.
    """

    def __init__(self, bus: MessageBus, args: Optional[List[str]] = None):
        self._bus = bus
        # Cola de suscripción propia: recibe copia de todos los mensajes RX.
        # Es importante crearla ANTES del primer send(), para no perder una
        # respuesta que llegue entre el envío y la suscripción.
        self._rx_queue: asyncio.Queue[Message] = bus.create_rx_subscriber()
        self.args: List[str] = list(args or [])

    # ------------------------------------------------------------------
    # API pública para los scripts de automatización
    # ------------------------------------------------------------------

    async def send(self, command: str) -> None:
        """Envía un comando al puerto serie y lo muestra en el terminal."""
        ui.info("AUTO", f"{ui.colorize('>>', 'magenta')} {command}")
        await self._bus.send_to_serial(
            Message(source=MessageSource.AUTOMATION, data=command)
        )

    async def wait_for(self, pattern: str, timeout: float = 5.0) -> str:
        """Espera un mensaje del serie que case con el regex dado.

        Args:
            pattern: expresión regular a buscar en la respuesta.
            timeout: segundos máximos de espera.

        Returns:
            El texto del mensaje que ha coincidido.

        Raises:
            TimeoutError: si no llega ninguna coincidencia a tiempo.
        """
        compiled = re.compile(pattern)

        async def _wait() -> str:
            while True:
                msg: Message = await self._rx_queue.get()
                if compiled.search(msg.data):
                    return msg.data

        try:
            return await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timeout ({timeout}s) esperando patrón '{pattern}'") from None

    def debug(self, message: str) -> None:
        """Imprime un mensaje de depuración en el terminal."""
        ui.info("AUTO", message)

    def cleanup(self) -> None:
        """Libera el suscriptor de RX al terminar la automatización."""
        self._bus.remove_rx_subscriber(self._rx_queue)


# ---------------------------------------------------------------------------


class AutomationEngine:
    """Gestor de automatizaciones.

    Recibe el mapa ``automations`` ya validado (ver
    :class:`~ebridge.core.config.AutomationConfig`) y carga cada script la
    primera vez que se invoca.

    Configuración YAML esperada:
        automations:
          ponfecha:
            script: automations/ponfecha.py
            description: "Establece la fecha en el dispositivo"
    """

    def __init__(self, bus: MessageBus, automations: Mapping[str, AutomationConfig]):
        self._bus = bus
        self._automations = dict(automations)

    # -- consulta ---------------------------------------------------------

    def list_automations(self) -> List[str]:
        return sorted(self._automations)

    def has_automation(self, name: str) -> bool:
        return name in self._automations

    def describe(self, name: str) -> str:
        cfg = self._automations.get(name)
        return cfg.description if cfg else ""

    # -- carga ------------------------------------------------------------

    @staticmethod
    def _load_module(cfg: AutomationConfig) -> ModuleType:
        """Carga el script como módulo Python.

        Se recompila en cada invocación a propósito: eBridge es una herramienta
        de desarrollo y lo esperable es que al editar el script y volver a
        lanzarlo se ejecute la versión nueva sin reiniciar el terminal.

        Se compila el fuente a mano en vez de usar ``SourceFileLoader`` porque
        este valida la caché ``__pycache__`` por (mtime, tamaño): una edición
        que no cambie el tamaño dentro del mismo segundo se quedaba con la
        versión antigua.  ``compile()`` recibe la ruta real, así que los
        tracebacks siguen apuntando al fichero correcto.
        """
        if not cfg.script.is_file():
            raise AutomationError(f"Script no encontrado: {cfg.script}")

        # Permite que el script importe módulos hermanos (ota_frames, etc.).
        parent = str(cfg.script.parent.resolve())
        if parent not in sys.path:
            sys.path.insert(0, parent)

        try:
            source = cfg.script.read_text(encoding="utf-8")
            code = compile(source, str(cfg.script), "exec")
        except (OSError, SyntaxError, ValueError) as e:
            raise AutomationError(f"Error al cargar '{cfg.script}': {e}") from e

        module_name = f"ebridge_automation_{cfg.name}"
        module = ModuleType(module_name)
        module.__file__ = str(cfg.script)
        # Registrar antes de ejecutar: dataclasses y algunos decoradores buscan
        # el módulo en sys.modules mientras se está definiendo.
        sys.modules[module_name] = module
        try:
            exec(code, module.__dict__)
        except Exception as e:
            sys.modules.pop(module_name, None)
            raise AutomationError(f"Error al cargar '{cfg.script}': {e}") from e

        if not hasattr(module, "run"):
            sys.modules.pop(module_name, None)
            raise AutomationError(
                f"El script '{cfg.script}' no define 'async def run(ctx, ...)'."
            )
        return module

    # -- ejecución --------------------------------------------------------

    async def run_automation(self, name: str, args: List[str]) -> bool:
        """Ejecuta una automatización por nombre en la tarea asyncio actual.

        Pensada para lanzarse con ``asyncio.create_task()`` y no bloquear el
        terminal.  Los errores se reportan por el terminal y **no** se
        propagan: una automatización que falla no debe tumbar la sesión.

        Returns:
            True si la automatización ha terminado correctamente.
        """
        cfg = self._automations.get(name)
        if cfg is None:
            ui.error("AUTO", f"Automatización desconocida: '{name}'")
            available = ", ".join(self.list_automations()) or "(ninguna)"
            ui.error("AUTO", f"Disponibles: {available}")
            return False

        try:
            module = self._load_module(cfg)
        except AutomationError as e:
            ui.error("AUTO", str(e))
            log.debug("Fallo cargando la automatización '%s'", name, exc_info=True)
            return False

        ctx = AutomationContext(bus=self._bus, args=args)
        ui.info("AUTO", f"Iniciando '{name}'" + (f" con args={args}" if args else ""))

        try:
            await module.run(ctx, *args)
            ui.ok("AUTO", f"'{name}' completada.")
            return True
        except TimeoutError as e:
            ui.error("AUTO", f"Timeout en '{name}': {e}")
        except asyncio.CancelledError:
            ui.warn("AUTO", f"'{name}' cancelada.")
            raise
        except Exception as e:
            ui.error("AUTO", f"Error en '{name}': {type(e).__name__}: {e}")
            # El traceback completo va al logging: visible con --verbose,
            # invisible en uso normal para no ensuciar el terminal.
            log.debug("Traceback de la automatización '%s'", name, exc_info=True)
        finally:
            ctx.cleanup()
        return False
