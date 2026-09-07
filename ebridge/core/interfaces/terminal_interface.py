# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Interfaz de terminal interactivo.

Usa prompt_toolkit para:
  - leer comandos sin bloquear la visualización de los datos recibidos
  - historial de comandos persistente entre sesiones
  - autocompletado de nombres de automatizaciones
  - resaltado de los mensajes recibidos del serie

Comandos especiales:
  /<automatizacion> [args...]  → ejecuta una automatización
  /list                        → lista automatizaciones disponibles
  /help                        → muestra ayuda
  /quit  o  Ctrl+D             → sale del programa

Cualquier otra cosa se envía tal cual al puerto serie.

Esta es la interfaz **primaria**: cuando termina, el runner cierra la sesión
entera.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from ebridge import ui
from ebridge.core.automation_engine import AutomationEngine
from ebridge.core.highlighter import Highlighter
from ebridge.core.interfaces.base import BaseInterface
from ebridge.core.message_bus import Message, MessageBus, MessageSource
from ebridge.core.register_linker import RegisterLinker
from ebridge.core.registry import BuildContext, register

__all__ = ["TerminalInterface"]


# Prefijo de color para cada tipo de mensaje mostrado en el terminal.
# Las fuentes que no aparecen aquí (TERMINAL, SOCKET_RX) son entradas: no se
# reimprimen, porque el usuario ya las ha visto al escribirlas.
_SOURCE_TAG = {
    MessageSource.SERIAL_RX:  ("RX", "info"),
    MessageSource.SYSTEM:     ("SYS", "warn"),
    MessageSource.AUTOMATION: ("AUT", "info"),
}

_QUIT_COMMANDS = ("quit", "exit", "q")


class TerminalInterface(BaseInterface):
    """Terminal interactivo: muestra la salida del serie y acepta comandos."""

    def __init__(
        self,
        bus: MessageBus,
        highlighter: Highlighter,
        automation_engine: AutomationEngine,
        device_name: str = "",
        register_linker: Optional[RegisterLinker] = None,
        history_dir: Optional[Path] = None,
    ):
        self._bus = bus
        self._highlighter = highlighter
        self._register_linker = register_linker
        self._automation_engine = automation_engine
        self._device_name = device_name
        self._rx_queue: asyncio.Queue[Message] = bus.create_rx_subscriber()
        self._stop_event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._session: Optional[PromptSession] = None

        # Historial persistente, un fichero por dispositivo, en el directorio
        # de trabajo (está contemplado en el .gitignore del proyecto).
        self._history_file = (history_dir or Path.cwd()) / f".history_{device_name or 'terminal'}"

    def _make_session(self) -> PromptSession:
        """Crea la sesión de prompt_toolkit.

        Se hace al arrancar y no en el constructor porque prompt_toolkit
        necesita una consola real: construirla antes obligaría a tener un
        terminal solo para *instanciar* la interfaz (y rompía los tests y
        cualquier uso con la salida redirigida).
        """
        return PromptSession(
            history=FileHistory(str(self._history_file)),
            auto_suggest=AutoSuggestFromHistory(),
        )

    # ------------------------------------------------------------------
    # Presentación
    # ------------------------------------------------------------------

    def _print_separator(self) -> None:
        ui.cprint(ui.colorize("─" * 60, "grey"))

    def _print_banner(self) -> None:
        title = f"  eBridge  ·  {self._device_name}  "
        border = "═" * len(title)
        ui.cprint(ui.colorize(f"╔{border}╗\n║{title}║\n╚{border}╝", "bold_cyan"))
        # Aviso corto que pide la GPL-3.0 para programas interactivos
        # (sección "How to Apply These Terms to Your New Programs").
        ui.cprint(ui.colorize(
            "  eBridge  Copyright (C) 2026  Jose Luis Alcoba Huertas\n"
            "  Software libre sin NINGUNA GARANTÍA; ver LICENSE (GPL-3.0-or-later).",
            "grey"))
        ui.cprint("  /help para ayuda  ·  Ctrl+D para salir")
        self._print_separator()

    def _print_help(self) -> None:
        ui.cprint(
            f"\n{ui.colorize('Ayuda del terminal', 'bold')}\n"
            "  <texto>                → envía al puerto serie\n"
            "  /<auto> [args...]      → ejecuta una automatización\n"
            "  /list                  → lista automatizaciones disponibles\n"
            "  /help                  → muestra esta ayuda\n"
            "  /quit  o  Ctrl+D       → sale del programa\n"
        )
        self._print_automations()

    def _print_automations(self) -> None:
        names = self._automation_engine.list_automations()
        if not names:
            ui.cprint("  No hay automatizaciones configuradas.\n")
            return
        ui.cprint("  Automatizaciones disponibles:")
        width = max(len(n) for n in names)
        for name in names:
            desc = self._automation_engine.describe(name)
            label = ui.colorize(f"/{name}".ljust(width + 1), "cyan")
            ui.cprint(f"    {label}  {desc}" if desc else f"    {label}")
        ui.cprint("")

    # ------------------------------------------------------------------
    # Bucle de visualización (consumidor de RX)
    # ------------------------------------------------------------------

    async def _display_loop(self) -> None:
        """Consume la cola de mensajes entrantes y los pinta con colores."""
        while True:
            msg: Message = await self._rx_queue.get()

            tag_name, level = _SOURCE_TAG.get(msg.source, ("", "info"))
            prefix = ui.tag(tag_name, level) if tag_name else ""

            # 1) Insertar hipervínculos OSC 8 en las referencias a registros.
            #    Se hace ANTES de colorear para que la parte "= 0xVALOR" quede
            #    intacta y el resaltador pueda colorear el valor hexadecimal.
            if self._register_linker is not None:
                body, has_link = self._register_linker.linkify(msg.data)
            else:
                body, has_link = msg.data, False

            # 2) Resaltado normal por regex.
            line = f"{prefix} {self._highlighter.highlight(body)}".lstrip()

            # 3) Las líneas con enlace van por la ruta cruda: es la única que
            #    conserva el OSC 8 (el parser ANSI de prompt_toolkit lo borra).
            if has_link:
                await ui.print_raw(line)
            else:
                ui.cprint(line)

    # ------------------------------------------------------------------
    # Bucle de entrada de usuario
    # ------------------------------------------------------------------

    def _completer(self) -> WordCompleter:
        names = ["/" + n for n in self._automation_engine.list_automations()]
        return WordCompleter(names + ["/list", "/help", "/quit"], sentence=True)

    async def _input_loop(self) -> None:
        """Lee comandos y los reparte entre el serie y el motor de automatizaciones."""
        if self._session is None:
            self._session = self._make_session()
        completer = self._completer()
        prompt_tokens = FormattedText([
            ("ansibrightgreen bold", self._device_name or "serial"),
            ("", " $ "),
        ])

        while not self._stop_event.is_set():
            try:
                line = (await self._session.prompt_async(prompt_tokens, completer=completer)).strip()
            except KeyboardInterrupt:
                continue          # Ctrl+C limpia la línea, no sale
            except EOFError:
                ui.warn("SYS", "Saliendo…")
                break             # Ctrl+D → salida limpia

            if not line:
                continue
            if line.startswith("/"):
                if self._handle_command(line[1:]):
                    break
            else:
                await self._bus.send_to_serial(
                    Message(source=MessageSource.TERMINAL, data=line)
                )

    def _handle_command(self, body: str) -> bool:
        """Procesa un comando ``/…``. Devuelve True si hay que salir."""
        parts = body.split()
        if not parts:
            return False
        cmd, args = parts[0].lower(), parts[1:]

        if cmd in _QUIT_COMMANDS:
            ui.warn("SYS", "Saliendo…")
            return True
        if cmd == "help":
            self._print_help()
        elif cmd == "list":
            self._print_automations()
        elif self._automation_engine.has_automation(cmd):
            # Se lanza como tarea independiente para no bloquear el prompt.
            # Se guarda la referencia porque asyncio solo mantiene una
            # referencia débil a las tareas y podrían recolectarse a medias.
            task = asyncio.create_task(
                self._automation_engine.run_automation(cmd, args), name=f"auto-{cmd}"
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        else:
            ui.error("SYS", f"Comando desconocido: '/{cmd}'. Escribe /help para ayuda.")
        return False

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        # patch_stdout redirige el print() estándar para que no interfiera con
        # el prompt. ui.cprint() usa print_formatted_text, que ya es compatible.
        with patch_stdout():
            self._print_banner()
            display = asyncio.create_task(self._display_loop(), name="terminal-display")
            try:
                await self._input_loop()
            finally:
                display.cancel()
                await asyncio.gather(display, return_exceptions=True)
                await self.stop()

    async def stop(self) -> None:
        """Cancela las automatizaciones en curso y suelta la suscripción."""
        self._stop_event.set()
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        self._bus.remove_rx_subscriber(self._rx_queue)


@register("terminal", primary=True)
def _build(ctx: BuildContext) -> TerminalInterface:
    return TerminalInterface(
        bus=ctx.bus,
        highlighter=ctx.highlighter,
        automation_engine=ctx.automation_engine,
        device_name=ctx.config.name,
        register_linker=ctx.register_linker,
    )
