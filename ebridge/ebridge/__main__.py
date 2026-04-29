"""
Punto de entrada para la invocación como módulo.

    python -m ebridge example_device --port /dev/ttyUSB0

Es equivalente a usar el comando instalado:

    ebridge example_device --port /dev/ttyUSB0
"""

from ebridge.cli import main

if __name__ == "__main__":
    main()
