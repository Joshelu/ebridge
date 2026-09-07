# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Capa de salida por terminal de eBridge.

Este módulo es el **único sitio** del proyecto donde deben aparecer códigos
de escape ANSI escritos a mano.  El resto del código llama a funciones con
nombre semántico:

    from ebridge import ui

    ui.ok("SERIAL",  f"Puerto abierto: {port}")
    ui.error("AUTO", f"Script no encontrado: {path}")
    ui.note("SYS",   "Configuración cargada")

Ventajas de tenerlo centralizado:

  - Cambiar la paleta o el formato de las etiquetas se hace en un archivo.
  - ``--no-color`` / ``NO_COLOR`` funcionan en todo el programa sin tocar
    ningún otro módulo (ver :func:`set_color_enabled`).
  - Los tests pueden desactivar el color y comparar texto plano.

Notas de portabilidad
---------------------
En Windows, ``print()`` escribe bytes crudos en stdout y, dentro del contexto
``patch_stdout`` de prompt_toolkit (o en consolas con políticas restrictivas),
los códigos ``\\x1b[Xm`` se muestran literalmente en lugar de aplicar color.
Por eso se usa ``print_formatted_text(ANSI(...))``, que delega en el sistema
de salida de prompt_toolkit y elige Win32 Console API o modo VT según lo que
soporte la consola.

La excepción son los hipervínculos OSC 8: el parser ANSI de prompt_toolkit los
elimina, así que hay que emitirlos con :func:`print_raw`.
"""

from __future__ import annotations

import os
import re

from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.application.current import get_app_session
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text

__all__ = [
    "ANSI_COLORS", "RESET",
    "set_color_enabled", "color_enabled", "colorize", "strip_ansi",
    "cprint", "print_raw",
    "note", "info", "ok", "warn", "error", "tag",
]


# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------
# Nombres usables desde los YAML de dispositivo (sección `highlights` y
# `register_links.color`). Añadir un color aquí lo hace disponible en el YAML
# automáticamente, sin tocar nada más.
ANSI_COLORS: dict[str, str] = {
    "red":        "\x1b[91m",
    "green":      "\x1b[92m",
    "yellow":     "\x1b[93m",
    "blue":       "\x1b[94m",
    "magenta":    "\x1b[95m",
    "cyan":       "\x1b[96m",
    "white":      "\x1b[97m",
    "grey":       "\x1b[90m",
    "gray":       "\x1b[90m",
    "orange":     "\x1b[33m",
    "bold_red":   "\x1b[1;91m",
    "bold_green": "\x1b[1;92m",
    "bold_cyan":  "\x1b[1;96m",
    "bold":       "\x1b[1m",
    "dim":        "\x1b[2m",
    "reset":      "\x1b[0m",
}

RESET = ANSI_COLORS["reset"]
UNDERLINE = "\x1b[4m"

# Coincide con cualquier secuencia SGR (colores/estilos) y con los
# hipervínculos OSC 8, que usan terminador ST (ESC \) o BEL.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m|\x1b\]8;[^\x1b\a]*(?:\x1b\\|\a)")


# ---------------------------------------------------------------------------
# Interruptor global de color
# ---------------------------------------------------------------------------
# Se respeta la convención NO_COLOR (https://no-color.org/): si la variable
# existe con cualquier valor, se arranca sin color.
_color_enabled: bool = os.environ.get("NO_COLOR") is None


def set_color_enabled(enabled: bool) -> None:
    """Activa o desactiva el color en todo el programa.

    Lo llama la CLI al procesar ``--no-color``.  Afecta a :func:`colorize`,
    que es el único punto por el que se inyectan códigos ANSI, de modo que
    también desactiva el resaltado de los mensajes del dispositivo.
    """
    global _color_enabled
    _color_enabled = enabled


def color_enabled() -> bool:
    """True si la salida debe llevar códigos ANSI."""
    return _color_enabled


def colorize(text: str, color: str = "", *, underline: bool = False) -> str:
    """Envuelve `text` en el color indicado (nombre de :data:`ANSI_COLORS`).

    Devuelve el texto sin tocar si el color está desactivado o si el nombre
    no existe en la paleta, de forma que un color mal escrito en el YAML
    degrada a texto plano en lugar de romper la línea.
    """
    if not _color_enabled:
        return text
    code = ANSI_COLORS.get(color, "")
    prefix = (UNDERLINE if underline else "") + code
    return f"{prefix}{text}{RESET}" if prefix else text


def strip_ansi(text: str) -> str:
    """Elimina códigos SGR e hipervínculos OSC 8 (para volcar a fichero)."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Primitivas de impresión
# ---------------------------------------------------------------------------

# prompt_toolkit necesita una consola de verdad. Cuando no la hay (salida
# redirigida a un fichero o a otro proceso, ejecución en CI, suite de tests…)
# lanza NoConsoleScreenBufferError. En ese caso se degrada a print() y se
# recuerda la decisión, para no reintentar en cada línea.
_plain_output: bool = False


def cprint(text: str, end: str = "\n") -> None:
    """Imprime texto que puede contener ANSI, de forma portable.

    Reemplazo directo de ``print()`` para mensajes con color.  Compatible con
    Windows Terminal y con el contexto ``patch_stdout`` de prompt_toolkit, y
    con salida redirigida (donde cae a ``print()`` en texto plano).
    """
    global _plain_output

    if not _plain_output:
        try:
            print_formatted_text(ANSI(text), end=end)
            return
        except Exception:
            _plain_output = True

    print(text if _color_enabled else strip_ansi(text), end=end)


async def print_raw(text: str) -> None:
    """Imprime una línea preservando las secuencias de escape crudas (OSC 8).

    La ruta normal (:func:`cprint`) analiza el ANSI con prompt_toolkit, que
    elimina los hipervínculos OSC 8.  Aquí se escribe con ``output.write_raw()``
    dentro de ``run_in_terminal()``, que es la forma correcta de emitir
    secuencias crudas por encima del prompt sin corromperlo.

    Requiere un terminal con soporte VT (terminal integrado de VS Code,
    Windows Terminal…).  Si falla por cualquier motivo, degrada a
    :func:`cprint`: se pierde el enlace, pero no la línea.
    """
    output = get_app_session().output

    def _do() -> None:
        # En Windows, Windows10_Output reactiva el modo VT en cada flush y
        # resetea el autowrap; lo reactivamos antes de escribir.
        output.enable_autowrap()
        output.write_raw(text + "\n")
        output.flush()

    try:
        await run_in_terminal(_do, in_executor=False)
    except Exception:
        cprint(text)


# ---------------------------------------------------------------------------
# Mensajes con etiqueta
# ---------------------------------------------------------------------------
# Formato: "[TAG] mensaje", con la etiqueta coloreada según la severidad.
# El ancho fijo de la etiqueta mantiene los mensajes alineados en columna.
_TAG_WIDTH = 6

_LEVEL_COLOR = {
    "note":  "grey",
    "info":  "blue",
    "ok":    "green",
    "warn":  "yellow",
    "error": "red",
}


def tag(name: str, level: str = "info") -> str:
    """Devuelve la etiqueta ``[NAME]`` coloreada según el nivel."""
    label = f"[{name.upper():<{_TAG_WIDTH - 2}}]"
    return colorize(label, _LEVEL_COLOR.get(level, ""))


def _emit(level: str, name: str, message: str) -> None:
    cprint(f"{tag(name, level)} {message}")


def note(name: str, message: str) -> None:
    """Detalle de baja importancia (gris): rutas cargadas, cierres limpios…"""
    _emit("note", name, message)


def info(name: str, message: str) -> None:
    """Información normal de funcionamiento."""
    _emit("info", name, message)


def ok(name: str, message: str) -> None:
    """Algo ha salido bien: puerto abierto, automatización completada…"""
    _emit("ok", name, message)


def warn(name: str, message: str) -> None:
    """Aviso: no impide seguir, pero el usuario debería enterarse."""
    _emit("warn", name, message)


def error(name: str, message: str) -> None:
    """Error: la operación en curso no se ha podido completar."""
    _emit("error", name, message)
