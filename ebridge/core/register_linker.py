# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Register linker: convierte los volcados de registros del log en enlaces
pinchables desde el terminal.

El firmware del Smatrix 5 imprime valores de registro en el log de debug:

    [DEBUG] Global Bus: th_01_th_TH_ECO = 0x4848 (18504)
    [DEBUG] Local Bus:  ct_CB_CONFIG    = 0x2101 (8449)

Este componente detecta esas líneas y envuelve el nombre del registro en un
hipervínculo OSC 8 que apunta al explorador de registros web, con el valor ya
relleno:

    http://localhost:8000/th_eco?value=4848

Ctrl+Click (terminal integrado de VS Code, Windows Terminal) abre el navegador
en el registro decodificado.

Por qué OSC 8 y no una URL en texto plano
-----------------------------------------
OSC 8 mantiene el texto visible compacto: solo se ve el nombre del registro y
la URL larga queda detrás del enlace.  La pega es que el parser ANSI de
prompt_toolkit elimina las secuencias OSC 8, así que estas líneas hay que
imprimirlas con :func:`ebridge.ui.print_raw` y no por la ruta normal.

Configuración (YAML del dispositivo, p.ej. sm5.yaml)
----------------------------------------------------
    register_links:
      enabled:   true
      base_url:  "http://localhost:8000"
      color:     blue          # cualquier color de ebridge.ui.ANSI_COLORS, o ""
      underline: true
      # Regex con grupos con nombre 'name', 'sep' y 'value'.
      pattern: '(?P<name>[A-Za-z_]\\w*)(?P<sep>\\s*=\\s*0x)(?P<value>[0-9A-Fa-f]+)'
      # Prefijos que se quitan del nombre para obtener el slug del registro.
      # Se elimina el primero que case con el principio del nombre.
      strip_prefixes:
        - 'th_\\d+_th_'
        - 'th_\\d+_'
        - 'ct_'
        - 'cm_'
        - 'sys_'
"""

from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import quote

from ebridge import ui
from ebridge.core.config import RegisterLinkConfig

__all__ = ["RegisterLinker"]


# Delimitadores del hipervínculo OSC 8 (forma terminada en ST):
#   ESC ] 8 ;; <url> ESC \    …texto…    ESC ] 8 ;; ESC \
_OSC8_OPEN = "\x1b]8;;{url}\x1b\\"
_OSC8_CLOSE = "\x1b]8;;\x1b\\"


class RegisterLinker:
    """Envuelve nombres de registro en hipervínculos OSC 8."""

    def __init__(self, config: RegisterLinkConfig):
        """
        Args:
            config: sección ``register_links`` ya validada.  Un regex inválido
                    desactiva la función con un aviso, en lugar de romper el
                    arranque.
        """
        self.enabled: bool = config.enabled
        self.base_url: str = config.base_url.rstrip("/")
        self._color: str = config.color
        self._underline: bool = config.underline

        try:
            self._pattern = re.compile(config.pattern)
        except re.error as e:
            ui.warn("LINK", f"Patrón regex inválido, se desactivan los enlaces: {e}")
            self.enabled = False
            self._pattern = re.compile(r"(?!x)x")  # nunca casa

        # Prefijos a eliminar, anclados al principio y sin distinguir mayúsculas.
        self._strip: List[re.Pattern] = []
        for prefix in config.strip_prefixes:
            try:
                self._strip.append(re.compile("^" + prefix, re.IGNORECASE))
            except re.error as e:
                ui.warn("LINK", f"Prefijo regex inválido '{prefix}', ignorado: {e}")

    def _slug(self, name: str) -> str:
        """Deriva el slug de la web a partir del nombre que aparece en el log.

        Quita el primer prefijo de propietario/instancia que case (p.ej.
        ``th_01_th_``), de forma que ``th_01_th_TH_ECO`` se convierte en
        ``th_eco``, que es el nombre de Element que usa la web.
        """
        for rx in self._strip:
            m = rx.match(name)
            if m:
                name = name[m.end():]
                break
        return name.lower()

    def linkify(self, text: str) -> Tuple[str, bool]:
        """Devuelve ``(texto_con_enlaces, hubo_enlace)``.

        ``hubo_enlace`` en True le indica al llamante que debe imprimir la línea
        por la ruta cruda, la única que conserva el OSC 8.
        """
        if not self.enabled:
            return text, False

        found = False

        def repl(m: re.Match) -> str:
            nonlocal found
            found = True
            name = m.group("name")
            value = m.group("value")
            url = f"{self.base_url}/{quote(self._slug(name))}?value={quote(value)}"

            # Se estiliza el nombre visible y luego se envuelve en el OSC 8. La
            # parte "= 0x...." (sep + value) se deja intacta para que el
            # resaltador pueda colorear después el valor hexadecimal.
            styled = ui.colorize(name, self._color, underline=self._underline)
            return _OSC8_OPEN.format(url=url) + styled + _OSC8_CLOSE + m.group("sep") + value

        return self._pattern.sub(repl, text), found
