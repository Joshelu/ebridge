"""
Interfaz de línea de comandos de ebridge.

Registrado como script en pyproject.toml:
    ebridge = "ebridge.cli:main"

Se puede invocar de tres formas equivalentes:
    ebridge example_device --port /dev/ttyUSB0   ← comando instalado
    python -m ebridge example_device --port ...  ← módulo Python
    python -c "from ebridge.cli import main; main()"
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ebridge._runner import run_terminal


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebridge",
        description="Terminal serie con bridge TCP y sistema de automatizaciones.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
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
        """,
    )
    parser.add_argument(
        "device",
        help=(
            "Nombre del dispositivo. Se busca como devices/<nombre>.yaml "
            "en el directorio actual o en las configuraciones del paquete."
        ),
    )
    parser.add_argument(
        "--port", "-p",
        required=True,
        metavar="PUERTO",
        help="Puerto serie (p.ej. /dev/ttyUSB0, COM3)",
    )
    parser.add_argument(
        "--socket-port", "-s",
        type=int,
        default=5000,
        metavar="PUERTO",
        dest="socket_port",
        help="Puerto TCP del servidor socket (default: 5000)",
    )
    parser.add_argument(
        "--socket-host",
        default="0.0.0.0",
        metavar="HOST",
        dest="socket_host",
        help="Dirección de escucha del socket (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--no-socket",
        action="store_true",
        dest="no_socket",
        help="Deshabilita el servidor socket",
    )
    parser.add_argument(
        "--log", "-l",
        default=None,
        metavar="FICHERO",
        help="Ruta del fichero de log de sesión",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Activa el logging interno detallado",
    )
    return parser


def main() -> None:
    """
    Punto de entrada principal.  Registrado en pyproject.toml como:
        ebridge = "ebridge.cli:main"
    """
    args = _build_parser().parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG,
                            format="[%(levelname)s] %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING,
                            format="[%(levelname)s] %(name)s: %(message)s")

    try:
        asyncio.run(
            run_terminal(
                device      = args.device,
                port        = args.port,
                socket_port = args.socket_port,
                socket_host = args.socket_host,
                no_socket   = args.no_socket,
                log_file    = args.log,
                verbose     = args.verbose,
            )
        )
    except KeyboardInterrupt:
        print("\n\033[93m[SYS] Interrumpido por el usuario.\033[0m")
    finally:
        print("\033[90m[SYS] Terminal cerrado.\033[0m")


if __name__ == "__main__":
    main()
