# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""Tests del motor de automatizaciones."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ebridge.core.automation_engine import AutomationContext, AutomationEngine
from ebridge.core.config import AutomationConfig
from ebridge.core.message_bus import Message, MessageBus, MessageSource


def engine_with(tmp_path: Path, name: str, source: str) -> tuple[AutomationEngine, MessageBus]:
    script = tmp_path / f"{name}.py"
    script.write_text(source, encoding="utf-8")
    bus = MessageBus()
    return AutomationEngine(bus, {name: AutomationConfig(name=name, script=script)}), bus


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

async def test_runs_the_script_and_sends_to_serial(tmp_path):
    engine, bus = engine_with(tmp_path, "saluda", """
async def run(ctx, *args):
    await ctx.send("hola " + " ".join(args))
""")
    assert await engine.run_automation("saluda", ["mundo"]) is True
    assert (await bus.tx_queue.get()).data == "hola mundo"


async def test_wait_for_matches_serial_response(tmp_path):
    engine, bus = engine_with(tmp_path, "espera", """
async def run(ctx, *args):
    ctx.result = await ctx.wait_for(r"OK|ERROR", timeout=1.0)
""")
    task = asyncio.create_task(engine.run_automation("espera", []))
    await asyncio.sleep(0)  # deja que la automatización se suscriba
    await bus.dispatch_rx(Message(source=MessageSource.SERIAL_RX, data="respuesta OK"))
    assert await task is True


async def test_timeout_is_reported_and_not_fatal(tmp_path, capsys):
    engine, _ = engine_with(tmp_path, "cuelga", """
async def run(ctx, *args):
    await ctx.wait_for("NUNCA", timeout=0.01)
""")
    assert await engine.run_automation("cuelga", []) is False
    assert "Timeout" in capsys.readouterr().out


async def test_script_exception_is_reported_and_not_fatal(tmp_path, capsys):
    engine, _ = engine_with(tmp_path, "revienta", """
async def run(ctx, *args):
    raise ValueError("boom")
""")
    assert await engine.run_automation("revienta", []) is False
    out = capsys.readouterr().out
    assert "ValueError" in out and "boom" in out


async def test_subscriber_is_released_after_running(tmp_path):
    """Sin cleanup, cada invocación dejaría una cola creciendo sin límite."""
    engine, bus = engine_with(tmp_path, "corta", "async def run(ctx, *a): pass")
    await engine.run_automation("corta", [])
    assert bus.subscriber_count == 0


async def test_subscriber_is_released_even_when_the_script_fails(tmp_path):
    engine, bus = engine_with(tmp_path, "mala", """
async def run(ctx, *args):
    raise RuntimeError("x")
""")
    await engine.run_automation("mala", [])
    assert bus.subscriber_count == 0


# ---------------------------------------------------------------------------
# Carga de módulos
# ---------------------------------------------------------------------------

async def test_sibling_modules_can_be_imported(tmp_path):
    """Regresión: sin esto, una automatización de varios ficheros tenía que
    parchear sys.path a mano (como hacía automations/ota.py)."""
    (tmp_path / "ayudante.py").write_text("VALOR = 'desde el hermano'\n", encoding="utf-8")
    engine, bus = engine_with(tmp_path, "compuesta", """
import ayudante

async def run(ctx, *args):
    await ctx.send(ayudante.VALOR)
""")
    assert await engine.run_automation("compuesta", []) is True
    assert (await bus.tx_queue.get()).data == "desde el hermano"


async def test_edits_to_the_script_take_effect_without_restart(tmp_path):
    script = tmp_path / "editable.py"
    script.write_text("async def run(ctx, *a):\n    await ctx.send('v1')\n", encoding="utf-8")
    bus = MessageBus()
    engine = AutomationEngine(bus, {
        "editable": AutomationConfig(name="editable", script=script)})

    await engine.run_automation("editable", [])
    assert (await bus.tx_queue.get()).data == "v1"

    script.write_text("async def run(ctx, *a):\n    await ctx.send('v2')\n", encoding="utf-8")
    await engine.run_automation("editable", [])
    assert (await bus.tx_queue.get()).data == "v2"


async def test_missing_script_is_reported(tmp_path, capsys):
    bus = MessageBus()
    engine = AutomationEngine(bus, {"fantasma": AutomationConfig(
        name="fantasma", script=tmp_path / "no_existe.py")})
    assert await engine.run_automation("fantasma", []) is False
    assert "no encontrado" in capsys.readouterr().out


async def test_script_without_run_is_reported(tmp_path, capsys):
    engine, _ = engine_with(tmp_path, "sin_run", "VALOR = 1\n")
    assert await engine.run_automation("sin_run", []) is False
    assert "run(ctx" in capsys.readouterr().out


async def test_script_with_syntax_error_is_reported(tmp_path, capsys):
    engine, _ = engine_with(tmp_path, "rota", "def run(  :\n")
    assert await engine.run_automation("rota", []) is False
    assert "Error al cargar" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

async def test_unknown_automation_lists_the_available_ones(tmp_path, capsys):
    engine, _ = engine_with(tmp_path, "existe", "async def run(ctx, *a): pass")
    assert await engine.run_automation("no_existe", []) is False
    out = capsys.readouterr().out
    assert "desconocida" in out and "existe" in out


def test_listing_and_description(tmp_path):
    bus = MessageBus()
    engine = AutomationEngine(bus, {
        "b": AutomationConfig(name="b", script=tmp_path / "b.py", description="Bee"),
        "a": AutomationConfig(name="a", script=tmp_path / "a.py"),
    })
    assert engine.list_automations() == ["a", "b"]     # ordenadas
    assert engine.has_automation("a") and not engine.has_automation("z")
    assert engine.describe("b") == "Bee"
    assert engine.describe("z") == ""


async def test_context_args_are_available_to_the_script(tmp_path):
    engine, bus = engine_with(tmp_path, "args", """
async def run(ctx, *args):
    await ctx.send(",".join(ctx.args))
""")
    await engine.run_automation("args", ["uno", "dos"])
    assert (await bus.tx_queue.get()).data == "uno,dos"


async def test_wait_for_raises_timeout_error():
    bus = MessageBus()
    ctx = AutomationContext(bus)
    with pytest.raises(TimeoutError):
        await ctx.wait_for("NUNCA", timeout=0.01)
    ctx.cleanup()
