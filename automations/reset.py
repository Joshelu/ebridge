"""
Automatización: reset
=====================
Reinicia el dispositivo enviando el comando "reset" y
esperando la confirmación de arranque.

El dispositivo se espera que responda:
    "READY" o "BOOT" o "OK" tras reiniciarse.

Uso:
    /reset
"""

import asyncio


async def run(ctx, *args):
    ctx.debug("Enviando comando de reset...")
    await ctx.send("reset")

    ctx.debug("Esperando confirmación de arranque (máx. 10s)...")
    try:
        response = await ctx.wait_for(r"READY|BOOT|OK", timeout=10.0)
        ctx.debug(f"Dispositivo reiniciado. Respuesta: {response}")
    except TimeoutError:
        ctx.debug("El dispositivo no respondió tras el reset.")
