# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Jerarquía de excepciones de eBridge.

Motivo: eBridge se usa de dos formas y las dos necesitan tratamiento distinto
de los errores:

  - Como comando (``ebridge ...``): el error se imprime bonito y el proceso
    sale con código != 0.  De eso se encarga ``cli.main()``.
  - Como librería (``from ebridge import run_terminal``): el llamante tiene
    que poder capturar el fallo.  Por eso el núcleo **nunca** llama a
    ``sys.exit()`` ni imprime errores fatales: lanza una de estas
    excepciones y deja que la capa de arriba decida.

Todas heredan de :class:`EBridgeError`, así que un llamante puede capturar
solo esa si no le interesa el detalle.
"""

from __future__ import annotations

__all__ = [
    "EBridgeError",
    "ConfigError",
    "DeviceConfigError",
    "AutomationError",
    "InterfaceError",
]


class EBridgeError(Exception):
    """Raíz de todos los errores propios de eBridge."""


class ConfigError(EBridgeError):
    """Configuración inválida (YAML mal formado, valores fuera de rango…)."""


class DeviceConfigError(ConfigError):
    """No se encontró el YAML del dispositivo, o no se pudo interpretar."""

    def __init__(self, device: str, searched: list[str] | None = None,
                 reason: str = "") -> None:
        self.device = device
        self.searched = searched or []
        self.reason = reason

        if reason:
            msg = f"No se pudo cargar la configuración de '{device}': {reason}"
        else:
            msg = f"No se encontró la configuración del dispositivo '{device}'."
        if self.searched:
            msg += "\nRutas buscadas:\n" + "\n".join(
                f"  - {s}" for s in self.searched
            )
        super().__init__(msg)


class AutomationError(EBridgeError):
    """Fallo al resolver, cargar o ejecutar una automatización."""


class InterfaceError(EBridgeError):
    """Fallo al construir o arrancar una interfaz (serie, socket, terminal…)."""
