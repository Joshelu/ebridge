# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Interfaz de línea de comandos de eBridge.

Registrada como script en pyproject.toml:
    ebridge = "ebridge.cli:main"

Tres formas equivalentes de invocarla:
    ebridge example_device --port /dev/ttyUSB0   ← comando instalado
    python -m ebridge example_device --port ...  ← módulo Python
    python -c "from ebridge.cli import main; main()"

Esta capa es la única que traduce errores en códigos de salida: el núcleo
lanza excepciones de :mod:`ebridge.errors` y aquí se convierten en un mensaje
legible y un exit code.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional, Sequence

from ebridge import __version__, ui
from ebridge._runner import run_terminal
from ebridge.errors import EBridgeError

__all__ = ["main", "build_parser"]

_EPILOG = """
Ejemplos:
  ebridge example_device --port /dev/ttyUSB0
  ebridge example_device --port COM3 --log sesion.log
  ebridge gps_module --port /dev/ttyACM0 --socket-port 5001
  ebridge mi_dispositivo --port COM3 --no-socket --verbose

  # Equivalente usando el módulo directamente:
  python -m ebridge example_device --port /dev/ttyUSB0

Orden de búsqueda de la configuración del dispositivo:
  1. devices/<nombre>.yaml  (directorio de trabajo actual)
  2. Configuraciones incluidas en el paquete  (ebridge/devices/)

eBridge es software libre bajo GPL-3.0-or-later y viene SIN NINGUNA GARANTÍA.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebridge",
        description="Terminal serie con bridge TCP y sistema de automatizaciones.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument(
        "device",
        help="Nombre del dispositivo. Se busca como devices/<nombre>.yaml en el "
             "directorio actual o entre las configuraciones del paquete.",
    )
    parser.add_argument(
        "--port", "-p", required=True, metavar="PUERTO",
        help="Puerto serie (p.ej. /dev/ttyUSB0, COM3)",
    )
    parser.add_argument(
        "--socket-port", "-s", type=int, default=5000, metavar="PUERTO",
        dest="socket_port",
        help="Puerto TCP del servidor socket (default: 5000)",
    )
    parser.add_argument(
        "--socket-host", default="0.0.0.0", metavar="HOST", dest="socket_host",
        help="Dirección de escucha del socket (default: 0.0.0.0). Usa 127.0.0.1 "
             "para aceptar solo conexiones locales.",
    )
    parser.add_argument(
        "--no-socket", action="store_true", dest="no_socket",
        help="Deshabilita el servidor socket",
    )
    parser.add_argument(
        "--log", "-l", default=None, metavar="FICHERO",
        help="Fichero de log de sesión. Si es un nombre suelto, se guarda en "
             "el directorio indicado por 'log.directory' en el YAML.",
    )
    parser.add_argument(
        "--no-color", action="store_true", dest="no_color",
        help="Desactiva los colores ANSI (también se respeta la variable NO_COLOR)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Activa el logging interno detallado",
    )
    parser.add_argument(
        "--version", action="version", version=f"eBridge {__version__}",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto de entrada principal. Devuelve el código de salida del proceso."""
    args = build_parser().parse_args(argv)

    if args.no_color:
        ui.set_color_enabled(False)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    try:
        asyncio.run(run_terminal(
            device      = args.device,
            port        = args.port,
            socket_port = args.socket_port,
            socket_host = args.socket_host,
            no_socket   = args.no_socket,
            log_file    = args.log,
            verbose     = args.verbose,
        ))
    except EBridgeError as e:
        # Errores esperados (configuración ausente o inválida): mensaje claro,
        # sin traceback, y código de salida != 0 para los scripts que llamen.
        ui.error("ERROR", str(e))
        return 1
    except KeyboardInterrupt:
        ui.warn("SYS", "Interrumpido por el usuario.")
        return 130            # convención: 128 + SIGINT
    finally:
        ui.note("SYS", "Terminal cerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
