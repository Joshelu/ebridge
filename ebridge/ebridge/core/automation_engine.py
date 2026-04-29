"""
Motor de automatizaciones.

Permite ejecutar scripts de Python como automatizaciones, con acceso
controlado al bus de mensajes. Cada automatización recibe un objeto
AutomationContext que le proporciona:

    await ctx.send(comando)              → envía al puerto serie
    await ctx.wait_for(patron, timeout)  → espera respuesta del serie
    ctx.debug(mensaje)                   → muestra mensaje en terminal

Ejemplo de script de automatización (automations/ponfecha.py):

    async def run(ctx, *args):
        await ctx.send("set day 27")
        resp = await ctx.wait_for(r"OK|ERROR")
        ctx.debug(f"Respuesta día: {resp}")
        if "OK" in resp:
            await ctx.send("set mes 4")
            resp = await ctx.wait_for(r"OK|ERROR")
            ctx.debug(f"Respuesta mes: {resp}")
"""

import asyncio
import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, Dict, Any, List

from .message_bus import MessageBus, Message, MessageSource


class AutomationContext:
    """
    Contexto que se entrega a cada script de automatización.
    Proporciona una interfaz de alto nivel para interactuar con el
    puerto serie sin bloquear el terminal ni el socket.
    """

    def __init__(self, bus: MessageBus, print_fn: Callable[[str], None]):
        self._bus = bus
        self._print = print_fn
        # Cola de suscripción propia: recibe copias de todos los mensajes RX
        self._rx_queue: asyncio.Queue[Message] = bus.create_rx_subscriber()
        # Argumentos posicionales pasados a la automatización
        self.args: List[str] = []

    # ------------------------------------------------------------------
    # API pública para los scripts de automatización
    # ------------------------------------------------------------------

    async def send(self, command: str) -> None:
        """Envía un comando al puerto serie y lo muestra en el terminal."""
        self._print(f"\033[35m[AUTO >>]\033[0m {command}")
        msg = Message(source=MessageSource.AUTOMATION, data=command)
        await self._bus.send_to_serial(msg)

    async def wait_for(self, pattern: str, timeout: float = 5.0) -> str:
        """
        Espera hasta que llegue del serie un mensaje que coincida con
        el patrón regex dado. Lanza TimeoutError si se agota el tiempo.

        Args:
            pattern: Expresión regular a buscar en la respuesta.
            timeout: Segundos máximos de espera (default 5).

        Returns:
            El texto del mensaje que coincidió.

        Raises:
            TimeoutError: Si no llega ninguna coincidencia en `timeout` segundos.
        """
        compiled = re.compile(pattern)

        async def _wait() -> str:
            while True:
                msg: Message = await self._rx_queue.get()
                if compiled.search(msg.data):
                    return msg.data

        try:
            result = await asyncio.wait_for(_wait(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Timeout ({timeout}s) esperando patrón '{pattern}'"
            )

    def debug(self, message: str) -> None:
        """Imprime un mensaje de depuración en el terminal."""
        self._print(f"\033[35m[AUTO   ]\033[0m {message}")

    def cleanup(self) -> None:
        """Libera el suscriptor de RX al terminar la automatización."""
        self._bus.remove_rx_subscriber(self._rx_queue)


# ---------------------------------------------------------------------------


class AutomationEngine:
    """
    Gestor de automatizaciones.

    Lee la sección 'automations' del YAML del dispositivo y carga
    dinámicamente los scripts correspondientes cuando se invocan.

    Configuración YAML esperada:
        automations:
          ponfecha:
            script: automations/ponfecha.py
            description: "Establece la fecha en el dispositivo"
          otra:
            script: automations/otra.py
    """

    def __init__(self, bus: MessageBus, config: Dict[str, Any]):
        self._bus = bus
        self.config = config  # {nombre: {script, description, ...}}

    def list_automations(self) -> List[str]:
        return list(self.config.keys())

    def has_automation(self, name: str) -> bool:
        return name in self.config

    async def run_automation(
        self,
        name: str,
        args: List[str],
        print_fn: Callable[[str], None],
    ) -> None:
        """
        Ejecuta una automatización por nombre en la tarea asyncio actual.
        Debe llamarse con asyncio.create_task() para no bloquear el terminal.
        """
        if name not in self.config:
            print_fn(f"\033[91m[AUTO] Automatización desconocida: '{name}'\033[0m")
            print_fn(f"\033[91m[AUTO] Disponibles: {', '.join(self.list_automations())}\033[0m")
            return

        cfg = self.config[name]
        script_path = Path(cfg.get("script", ""))

        if not script_path.exists():
            print_fn(f"\033[91m[AUTO] Script no encontrado: {script_path}\033[0m")
            return

        # Carga dinámica del módulo
        try:
            spec = importlib.util.spec_from_file_location(f"automation_{name}", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print_fn(f"\033[91m[AUTO] Error al cargar '{script_path}': {e}\033[0m")
            return

        if not hasattr(module, "run"):
            print_fn(f"\033[91m[AUTO] El script '{script_path}' no define 'async def run(ctx, ...)'.\033[0m")
            return

        ctx = AutomationContext(bus=self._bus, print_fn=print_fn)
        ctx.args = args

        print_fn(f"\033[35m[AUTO] Iniciando '{name}' con args={args}\033[0m")

        try:
            await module.run(ctx, *args)
            print_fn(f"\033[35m[AUTO] '{name}' completada.\033[0m")
        except TimeoutError as e:
            print_fn(f"\033[91m[AUTO] Timeout en '{name}': {e}\033[0m")
        except asyncio.CancelledError:
            print_fn(f"\033[93m[AUTO] '{name}' cancelada.\033[0m")
        except Exception as e:
            print_fn(f"\033[91m[AUTO] Error en '{name}': {type(e).__name__}: {e}\033[0m")
        finally:
            ctx.cleanup()
