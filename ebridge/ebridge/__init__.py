"""
eBridge — Enhanced Bridge
=========================
Terminal serie interactivo con bridge TCP y sistema de automatizaciones.

Uso como módulo:
    python -m ebridge example_device --port /dev/ttyUSB0

Uso programático (integrar en otro proyecto):
    from ebridge import run_terminal
    import asyncio

    asyncio.run(run_terminal(
        device="mi_dispositivo",   # devices/mi_dispositivo.yaml
        port="/dev/ttyUSB0",
        socket_port=5000,
        log_file="sesion.log",
    ))

Clases principales disponibles para construir interfaces propias:
    from ebridge.core.message_bus       import MessageBus, Message, MessageSource
    from ebridge.core.highlighter       import Highlighter
    from ebridge.core.automation_engine import AutomationEngine, AutomationContext
    from ebridge.core.logger            import SessionLogger
    from ebridge.core.interfaces.base   import BaseInterface
"""

__version__ = "1.0.0"
__author__  = "eBridge"
__all__     = ["run_terminal"]


# ---------------------------------------------------------------------------
# API de alto nivel: run_terminal()
# ---------------------------------------------------------------------------

from ebridge._runner import run_terminal  # noqa: E402
