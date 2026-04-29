"""
Interfaz de terminal interactivo.

Usa prompt_toolkit para proporcionar:
  - Entrada de usuario sin bloquear la visualización de datos recibidos
  - Historial de comandos persistente
  - Autocompletado de nombres de automatizaciones
  - Resaltado de sintaxis en los mensajes recibidos del serie

NOTA SOBRE COLORES EN WINDOWS:
  Se usa print_formatted_text(ANSI(...)) de prompt_toolkit en lugar de
  print() plano. Esto garantiza que los códigos ANSI se rendericen
  correctamente en Windows Terminal (y en cualquier terminal Unix),
  incluso dentro del contexto patch_stdout.

Comandos especiales del terminal:
  /automation [args...]  → ejecuta una automatización
  /list                  → lista automatizaciones disponibles
  /help                  → muestra ayuda
  /quit o Ctrl+D         → sale del programa

Todo lo demás se envía directamente al puerto serie.
"""

import asyncio
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

from .base import BaseInterface
from ..message_bus import MessageBus, Message, MessageSource
from ..highlighter import Highlighter
from ..automation_engine import AutomationEngine


# ---------------------------------------------------------------------------
# Prefijos de color para cada tipo de mensaje
# Expresados como ANSI strings — print_formatted_text(ANSI(...)) los renderiza
# correctamente tanto en Windows Terminal como en terminales Unix.
# ---------------------------------------------------------------------------
SOURCE_PREFIX = {
    MessageSource.SERIAL_RX:  "\x1b[36m[RX ]\x1b[0m",
    MessageSource.SYSTEM:     "\x1b[33m[SYS]\x1b[0m",
    MessageSource.AUTOMATION: "\x1b[35m[AUT]\x1b[0m",
}


def _ansi(text: str) -> None:
    """
    Imprime texto con códigos ANSI de forma compatible con Windows Terminal.

    prompt_toolkit.print_formatted_text + ANSI() traduce los escape codes
    al mecanismo nativo de cada plataforma, por lo que funciona dentro y
    fuera del contexto patch_stdout sin mostrar '?' en Windows.
    """
    print_formatted_text(ANSI(text), end="\n")


class TerminalInterface(BaseInterface):
    """
    Terminal interactivo: visualiza la salida del serie y acepta comandos
    del usuario de forma concurrente y sin bloqueos.
    """

    def __init__(
        self,
        bus: MessageBus,
        highlighter: Highlighter,
        automation_engine: AutomationEngine,
        device_name: str = "",
    ):
        self._bus = bus
        self._highlighter = highlighter
        self._automation_engine = automation_engine
        self._device_name = device_name
        self._rx_queue: asyncio.Queue[Message] = bus.create_rx_subscriber()
        self._stop_event = asyncio.Event()

        # Historial persistente entre sesiones
        history_file = Path(f".history_{device_name or 'terminal'}")
        self._session: PromptSession = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
        )

    # ------------------------------------------------------------------
    # Utilidades de impresión
    # Todas usan _ansi() → print_formatted_text(ANSI(...))
    # para garantizar compatibilidad con Windows Terminal.
    # ------------------------------------------------------------------

    def _print(self, text: str) -> None:
        """Punto de entrada de impresión para automatizaciones y mensajes internos."""
        _ansi(text)

    def _print_separator(self) -> None:
        _ansi("\x1b[90m" + "─" * 60 + "\x1b[0m")

    def _print_banner(self) -> None:
        name = self._device_name
        _ansi(
            f"\x1b[1;96m"
            f"╔══════════════════════════════════════════╗\n"
            f"║      eBridge  ·  {name:<16s}  ║\n"
            f"╚══════════════════════════════════════════╝"
            f"\x1b[0m"
        )
        _ansi("  /help para ayuda  ·  Ctrl+D para salir")
        self._print_separator()

    def _print_help(self) -> None:
        autos = self._automation_engine.list_automations()
        _ansi(
            "\n\x1b[1mAyuda del terminal\x1b[0m\n"
            "  <texto>                → envía al puerto serie\n"
            "  /<auto> [args...]      → ejecuta una automatización\n"
            "  /list                  → lista automatizaciones disponibles\n"
            "  /help                  → muestra esta ayuda\n"
            "  /quit  o  Ctrl+D       → sale del programa\n"
        )
        if autos:
            _ansi(f"  Automatizaciones disponibles: \x1b[96m{', '.join(autos)}\x1b[0m\n")
        else:
            _ansi("  No hay automatizaciones configuradas.\n")

    # ------------------------------------------------------------------
    # Bucle de visualización (consumidor de RX)
    # ------------------------------------------------------------------

    async def _display_loop(self) -> None:
        """
        Consume la cola de mensajes entrantes y los imprime con colores.
        Corre concurrentemente con el bucle de entrada gracias a asyncio.
        """
        while not self._stop_event.is_set():
            try:
                msg: Message = await asyncio.wait_for(
                    self._rx_queue.get(), timeout=0.2
                )
            except asyncio.TimeoutError:
                continue

            prefix = SOURCE_PREFIX.get(msg.source, "")
            highlighted = self._highlighter.highlight(msg.data)
            # Usamos \x1b en lugar de \033 — son equivalentes pero
            # más explícitos en strings que manejan prompt_toolkit.
            _ansi(f"{prefix} {highlighted}")

    # ------------------------------------------------------------------
    # Bucle de entrada de usuario
    # ------------------------------------------------------------------

    async def _input_loop(self) -> None:
        """Lee comandos del usuario y los despacha al serial o al motor de automatizaciones."""
        auto_names = ["/" + n for n in self._automation_engine.list_automations()]
        completer = WordCompleter(
            auto_names + ["/list", "/help", "/quit"],
            sentence=True,
        )

        # El prompt usa FormattedText en vez de ANSI raw para que
        # prompt_toolkit lo gestione correctamente en la línea de entrada.
        prompt_tokens = FormattedText([
            ("ansibrightgreen bold", self._device_name or "serial"),
            ("", " $ "),
        ])

        while not self._stop_event.is_set():
            try:
                line: str = await self._session.prompt_async(
                    prompt_tokens,
                    completer=completer,
                )
            except KeyboardInterrupt:
                # Ctrl+C limpia la línea actual, no sale
                continue
            except EOFError:
                # Ctrl+D → salida limpia
                _ansi("\n\x1b[93m[SYS] Saliendo…\x1b[0m")
                self._stop_event.set()
                break

            line = line.strip()
            if not line:
                continue

            # ---- Comandos especiales del terminal ----
            if line.startswith("/"):
                parts = line[1:].split()
                if not parts:
                    continue
                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("quit", "exit", "q"):
                    _ansi("\x1b[93m[SYS] Saliendo…\x1b[0m")
                    self._stop_event.set()
                    break
                elif cmd == "help":
                    self._print_help()
                elif cmd == "list":
                    autos = self._automation_engine.list_automations()
                    if autos:
                        _ansi(f"Automatizaciones: \x1b[96m{', '.join(autos)}\x1b[0m")
                    else:
                        _ansi("No hay automatizaciones configuradas.")
                elif self._automation_engine.has_automation(cmd):
                    # Lanza la automatización como tarea independiente
                    asyncio.create_task(
                        self._automation_engine.run_automation(cmd, args, self._print),
                        name=f"auto-{cmd}",
                    )
                else:
                    _ansi(
                        f"\x1b[91m[ERROR] Comando desconocido: '/{cmd}'. "
                        f"Escribe /help para ayuda.\x1b[0m"
                    )
            else:
                # Texto normal → enviar al serie
                msg = Message(source=MessageSource.TERMINAL, data=line)
                await self._bus.send_to_serial(msg)

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        # patch_stdout redirige print() estándar para que no interfiera
        # con el prompt. Nosotros usamos print_formatted_text internamente,
        # que ya es compatible con patch_stdout en todas las plataformas.
        with patch_stdout():
            self._print_banner()
            try:
                await asyncio.gather(
                    self._display_loop(),
                    self._input_loop(),
                )
            except asyncio.CancelledError:
                pass
            finally:
                self._stop_event.set()
