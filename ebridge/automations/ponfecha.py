"""
Automatización: ponfecha
========================
Establece la fecha (día y mes) en el dispositivo.

El dispositivo espera:
    set day <DIA>   → responde "OK" o "ERROR"
    set mes <MES>   → responde "OK" o "ERROR"

Uso desde el terminal:
    /ponfecha            → usa la fecha actual del sistema
    /ponfecha 27         → día 27, mes actual
    /ponfecha 27 4       → día 27, mes 4

La automatización:
  1. Envía "set day <DIA>" y espera "OK" o "ERROR"
  2. Si recibe "OK", envía "set mes <MES>" y espera "OK" o "ERROR"
  3. Muestra mensajes de debug en el terminal durante todo el proceso
"""

from datetime import datetime


async def run(ctx, *args):
    """
    Punto de entrada de la automatización.

    Args:
        ctx:    AutomationContext (inyectado por el motor de automatizaciones)
        *args:  Argumentos opcionales: [dia] [mes]
    """
    now = datetime.now()

    # Parseo de argumentos con valores por defecto = fecha actual
    try:
        day = int(args[0]) if len(args) >= 1 else now.day
    except ValueError:
        ctx.debug(f"Argumento 'dia' inválido: '{args[0]}'. Se usará el día actual.")
        day = now.day

    try:
        month = int(args[1]) if len(args) >= 2 else now.month
    except ValueError:
        ctx.debug(f"Argumento 'mes' inválido: '{args[1]}'. Se usará el mes actual.")
        month = now.month

    ctx.debug(f"Iniciando configuración de fecha: día={day}, mes={month}")

    # ---- Paso 1: establecer el día ----
    ctx.debug(f"Enviando comando para el día...")
    await ctx.send(f"set day {day}")

    try:
        response = await ctx.wait_for(r"\b(OK|ERROR)\b", timeout=5.0)
    except TimeoutError as e:
        ctx.debug(f"Sin respuesta del dispositivo: {e}")
        return

    if "ERROR" in response:
        ctx.debug(f"El dispositivo rechazó el día ({day}): {response}")
        return

    ctx.debug(f"Día {day} configurado correctamente.")

    # ---- Paso 2: establecer el mes ----
    ctx.debug(f"Enviando comando para el mes...")
    await ctx.send(f"set mes {month}")

    try:
        response = await ctx.wait_for(r"\b(OK|ERROR)\b", timeout=5.0)
    except TimeoutError as e:
        ctx.debug(f"Sin respuesta del dispositivo: {e}")
        return

    if "ERROR" in response:
        ctx.debug(f"El dispositivo rechazó el mes ({month}): {response}")
        return

    ctx.debug(f"Mes {month} configurado correctamente.")
    ctx.debug(f"✓ Fecha configurada: {day:02d}/{month:02d}")
