# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Resolución de archivos de configuración de dispositivos.

Orden de búsqueda para ``load_device_config("nombre")``:

1. ``devices/nombre.yaml``  en el directorio de trabajo actual  (proyecto del usuario)
2. ``devices/nombre.yml``   en el directorio de trabajo actual
3. La ruta tal cual, por si se ha pasado una ruta completa
4. Configuraciones incluidas en el paquete  (``ebridge/devices/``)

Esto permite sobrescribir cualquier dispositivo incluido creando un archivo
``devices/<nombre>.yaml`` en el proyecto del usuario, y usar los dispositivos
de ejemplo del paquete sin configuración adicional.

Esta función **no** termina el proceso: si no encuentra o no puede interpretar
la configuración, lanza :class:`~ebridge.errors.DeviceConfigError`.  Quien
decide qué hacer con eso es la CLI (imprimirlo y salir) o el programa que
integre eBridge como librería.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from ebridge import ui
from ebridge.core.config import DeviceConfig
from ebridge.errors import DeviceConfigError

__all__ = ["load_device_config"]


def _candidate_paths(name: str) -> list[Path]:
    return [
        Path(f"devices/{name}.yaml"),
        Path(f"devices/{name}.yml"),
        Path(name),             # ruta absoluta o relativa completa
        Path(f"{name}.yaml"),
        Path(f"{name}.yml"),
    ]


def load_device_config(device_name: str) -> DeviceConfig:
    """Carga, valida y devuelve la configuración del dispositivo indicado.

    Args:
        device_name: Nombre del dispositivo (con o sin extensión ``.yaml``),
                     o una ruta a un fichero de configuración.

    Returns:
        La configuración ya validada.

    Raises:
        DeviceConfigError: si no se encuentra ningún fichero, o si el YAML
            está mal formado.
        ConfigError: si el contenido del YAML tiene valores inválidos.
    """
    name = device_name.removesuffix(".yaml").removesuffix(".yml")

    # ── 1. Buscar en el directorio de trabajo del usuario ──────────────────
    candidates = _candidate_paths(name)
    for path in candidates:
        if path.is_file():
            raw = _parse_yaml(path.read_text(encoding="utf-8"), device_name, str(path))
            ui.note("SYS", f"Configuración cargada: {path.resolve()}")
            return DeviceConfig.from_dict(name, raw, source_path=path.resolve())

    # ── 2. Buscar en los dispositivos incluidos en el paquete ─────────────
    packaged = _load_packaged(name, device_name)
    if packaged is not None:
        return packaged

    # ── 3. No encontrado ──────────────────────────────────────────────────
    searched = [str(p) for p in candidates]
    searched.append(f"ebridge/devices/{name}.yaml (incluido en el paquete)")
    raise DeviceConfigError(device_name, searched=searched)


def _parse_yaml(text: str, device_name: str, where: str) -> dict:
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise DeviceConfigError(device_name, reason=f"YAML inválido en {where}: {e}") from e
    if not isinstance(data, dict):
        raise DeviceConfigError(
            device_name,
            reason=f"{where} debe contener un mapa de claves en el primer nivel.",
        )
    return data


def _load_packaged(name: str, device_name: str) -> Optional[DeviceConfig]:
    """Busca la configuración entre las que vienen dentro del paquete.

    Se usa ``importlib.resources`` para que funcione también cuando eBridge
    está instalado como wheel y los YAML no son ficheros sueltos en disco.
    """
    try:
        from importlib.resources import as_file, files
    except ImportError:                                  # pragma: no cover
        return None

    try:
        pkg_devices = files("ebridge.devices")
    except (ModuleNotFoundError, TypeError):             # pragma: no cover
        return None

    for ext in (".yaml", ".yml"):
        resource = pkg_devices.joinpath(f"{name}{ext}")
        try:
            text = resource.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, TypeError):
            continue

        raw = _parse_yaml(text, device_name, f"ebridge/devices/{name}{ext}")
        ui.note("SYS", f"Configuración cargada desde el paquete: ebridge/devices/{name}{ext}")

        # `source_path` sirve para resolver rutas de scripts relativas al YAML.
        # Con un paquete instalado como wheel puede que el fichero no exista en
        # disco; as_file() da una ruta real cuando la hay.
        source: Optional[Path] = None
        try:
            with as_file(resource) as real_path:
                source = Path(real_path)
                # Una ruta temporal no sirve de ancla: desaparece al salir del
                # contexto y resolver contra ella daría rutas inexistentes.
                if Path(tempfile.gettempdir()) in source.parents:
                    source = None
        except (FileNotFoundError, OSError, TypeError):   # pragma: no cover
            source = None

        return DeviceConfig.from_dict(name, raw, source_path=source)

    return None
