# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Clase base para todas las interfaces del sistema."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["BaseInterface"]


class BaseInterface(ABC):
    """Contrato mínimo de cualquier interfaz conectada al bus.

    Ciclo de vida, gestionado por :func:`ebridge._runner.run_terminal`:

      1. La factoría registrada crea la instancia (ver
         :mod:`ebridge.core.registry`).
      2. ``run()`` se lanza como tarea asyncio y vive hasta que se cancela
         o hasta que termina la interfaz primaria.
      3. ``stop()`` se llama siempre al cerrar, incluso si ``run()`` ha
         fallado, para liberar recursos (puertos, hilos, sockets).

    Para añadir una interfaz nueva (Bluetooth, MQTT, HTTP…):
      1. Hereda de ``BaseInterface`` e implementa ``run()``.
      2. Registra una factoría con ``@register("nombre")``.
      3. Importa el módulo en ``ebridge/core/interfaces/__init__.py``.

    No hace falta tocar el runner ni la CLI.
    """

    @abstractmethod
    async def run(self) -> None:
        """Bucle principal de la interfaz. Se ejecuta como tarea asyncio."""
        ...

    async def stop(self) -> None:
        """Limpieza al cerrar. Debe ser idempotente y no lanzar excepciones."""
        return None
