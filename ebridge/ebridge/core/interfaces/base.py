"""Clase base para todas las interfaces del sistema."""

from abc import ABC, abstractmethod


class BaseInterface(ABC):
    """
    Contrato mínimo que debe cumplir cualquier interfaz que se conecte al bus.

    Para añadir una nueva interfaz (p.ej. Bluetooth, MQTT, HTTP…):
      1. Subclasea BaseInterface.
      2. Implementa run() con la lógica productora/consumidora.
      3. Instánciala en main.py y añade su coroutine a asyncio.gather().
    """

    @abstractmethod
    async def run(self) -> None:
        """Bucle principal de la interfaz. Se ejecuta como tarea asyncio."""
        ...

    async def stop(self) -> None:
        """Limpieza opcional al cancelar la tarea."""
        ...
