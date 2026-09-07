# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Punto de entrada para la invocación como módulo.

    python -m ebridge example_device --port /dev/ttyUSB0

Es equivalente a usar el comando instalado:

    ebridge example_device --port /dev/ttyUSB0
"""

import sys

from ebridge.cli import main

if __name__ == "__main__":
    sys.exit(main())
