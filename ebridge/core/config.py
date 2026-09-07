# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jose Luis Alcoba Huertas
#
# This file is part of eBridge. eBridge is free software: you can
# redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# See the LICENSE file at the root of the repository for details.
"""
Configuración de dispositivo tipada.

Antes, el YAML circulaba por todo el programa como ``dict`` crudo y cada
módulo hacía su propio ``config.get("clave", valor_por_defecto)``.  Eso tenía
tres problemas:

  1. Los valores por defecto quedaban duplicados en varios sitios y se
     desincronizaban (el baudrate por defecto aparecía dos veces).
  2. Una clave mal escrita en el YAML no daba error: el valor se ignoraba
     en silencio y el usuario no se enteraba.
  3. No había un sitio donde mirar qué claves acepta el YAML.

Ahora el YAML se convierte **una sola vez** en :class:`DeviceConfig`, con
todos los defaults declarados en un único lugar y avisando de las claves
desconocidas.  Añadir una opción nueva al YAML es añadir un campo a la
dataclass correspondiente.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ebridge import ui
from ebridge.errors import ConfigError

__all__ = [
    "SerialConfig",
    "LogConfig",
    "HighlightRule",
    "RegisterLinkConfig",
    "AutomationConfig",
    "DeviceConfig",
]


# ---------------------------------------------------------------------------
# Utilidades de construcción
# ---------------------------------------------------------------------------

_SCALARS = (bool, int, float, str)


def _coerce(value: Any, target: type, where: str, key: str) -> Any:
    """Convierte `value` al tipo declarado en la dataclass.

    YAML ya devuelve tipos nativos, así que esto sirve sobre todo para dar un
    error legible cuando el usuario escribe ``baudrate: "muchos"`` en vez de
    dejar que reviente más tarde dentro de pyserial.
    """
    if target is bool:
        if isinstance(value, bool):
            return value
        raise ConfigError(
            f"{where}: '{key}' debe ser true o false, no {value!r}."
        )
    if target in (int, float):
        # bool es subclase de int en Python; no lo aceptamos como número.
        if isinstance(value, bool):
            raise ConfigError(f"{where}: '{key}' debe ser numérico, no {value!r}.")
        try:
            return target(value)
        except (TypeError, ValueError):
            raise ConfigError(
                f"{where}: '{key}' debe ser numérico, no {value!r}."
            ) from None
    if target is str:
        if value is None:
            raise ConfigError(f"{where}: '{key}' no puede estar vacío.")
        return str(value)
    return value


def _build(cls, data: Optional[Mapping[str, Any]], where: str):
    """Construye una dataclass a partir de un sub-dict del YAML.

    Avisa (sin abortar) de las claves que no corresponden a ningún campo:
    normalmente son erratas, y hasta ahora se ignoraban en silencio.
    """
    data = data or {}
    if not isinstance(data, Mapping):
        raise ConfigError(f"{where}: se esperaba un bloque de claves, no {type(data).__name__}.")

    known = {f.name: f for f in fields(cls) if f.init}
    unknown = [k for k in data if k not in known]
    if unknown:
        ui.warn("CONFIG",
                f"{where}: clave(s) desconocida(s) ignorada(s): "
                f"{', '.join(sorted(unknown))}. "
                f"Válidas: {', '.join(sorted(known))}")

    kwargs: dict[str, Any] = {}
    for name, f in known.items():
        if name not in data:
            continue
        value = data[name]
        if f.type in _SCALARS or f.type in ("bool", "int", "float", "str"):
            target = f.type if isinstance(f.type, type) else {
                "bool": bool, "int": int, "float": float, "str": str,
            }[f.type]
            value = _coerce(value, target, where, name)
        kwargs[name] = value
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Secciones del YAML
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SerialConfig:
    """Sección ``serial:`` del YAML del dispositivo."""

    baudrate: int = 9600
    bytesize: int = 8          # 5, 6, 7, 8
    parity: str = "N"          # N, E, O, M, S
    stopbits: float = 1.0      # 1, 1.5, 2
    timeout: float = 0.1       # segundos de espera en lectura
    eol: str = "\n"            # fin de línea añadido en TX
    encoding: str = "utf-8"
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False
    # Envío troceado, para dispositivos con buffer de recepción pequeño.
    # tx_chunk_size = 0 desactiva el troceado.
    tx_chunk_size: int = 0
    tx_chunk_delay: float = 0.01
    # Reapertura automática del puerto cuando se pierde (típicamente al
    # desenchufar y volver a enchufar el USB, o al reiniciar el dispositivo).
    # Desactivada por defecto para no cambiar el comportamiento histórico:
    # sin ella, perder el puerto deja la sesión con un puerto muerto.
    reconnect: bool = False
    reconnect_delay: float = 2.0

    def __post_init__(self) -> None:
        if self.baudrate <= 0:
            raise ConfigError(f"serial.baudrate debe ser > 0, no {self.baudrate}.")
        if self.reconnect_delay <= 0:
            raise ConfigError(
                f"serial.reconnect_delay debe ser > 0, no {self.reconnect_delay}."
            )
        if self.bytesize not in (5, 6, 7, 8):
            raise ConfigError(f"serial.bytesize debe ser 5, 6, 7 u 8, no {self.bytesize}.")
        if self.parity.upper() not in ("N", "E", "O", "M", "S"):
            raise ConfigError(f"serial.parity debe ser N, E, O, M o S, no {self.parity!r}.")
        if self.stopbits not in (1, 1.5, 2):
            raise ConfigError(f"serial.stopbits debe ser 1, 1.5 o 2, no {self.stopbits}.")
        if self.tx_chunk_size < 0:
            raise ConfigError("serial.tx_chunk_size no puede ser negativo.")


@dataclass(frozen=True)
class LogConfig:
    """Sección ``log:`` del YAML del dispositivo.

    ``directory`` permite dar solo el nombre del fichero en ``--log`` y dejar
    la carpeta fija en el YAML.  Si ``--log`` trae una ruta absoluta,
    ``directory`` se ignora.
    """

    directory: str = ""
    timestamp: bool = False

    def resolve_path(self, log_file: str) -> Path:
        """Combina ``directory`` con el nombre/ruta pedido en la CLI.

        Antes esto era ``Path(directory + log_file)`` con ``directory``
        pudiendo valer ``None``, lo que reventaba con TypeError en cualquier
        dispositivo cuyo YAML no definiera la sección ``log:``.
        """
        path = Path(log_file).expanduser()
        if path.is_absolute() or not self.directory:
            return path
        return (Path(self.directory).expanduser() / path)


@dataclass(frozen=True)
class HighlightRule:
    """Una entrada de la lista ``highlights:`` del YAML."""

    pattern: str
    color: str = "white"


# Patrón por defecto de los enlaces a registros: NOMBRE = 0xVALOR
_DEFAULT_LINK_PATTERN = r"(?P<name>[A-Za-z_]\w*)(?P<sep>\s*=\s*0x)(?P<value>[0-9A-Fa-f]+)"
_DEFAULT_LINK_PREFIXES: tuple[str, ...] = (r"th_\d+_th_", r"th_\d+_", r"ct_", r"cm_", r"sys_")


@dataclass(frozen=True)
class RegisterLinkConfig:
    """Sección ``register_links:`` del YAML del dispositivo."""

    enabled: bool = False
    base_url: str = "http://localhost:8000"
    color: str = "blue"
    underline: bool = True
    pattern: str = _DEFAULT_LINK_PATTERN
    strip_prefixes: Sequence[str] = _DEFAULT_LINK_PREFIXES


@dataclass(frozen=True)
class AutomationConfig:
    """Una entrada del mapa ``automations:`` del YAML."""

    name: str
    script: Path
    description: str = ""


@dataclass(frozen=True)
class DeviceConfig:
    """Configuración completa de un dispositivo, ya validada."""

    name: str
    serial: SerialConfig = field(default_factory=SerialConfig)
    log: LogConfig = field(default_factory=LogConfig)
    highlights: tuple[HighlightRule, ...] = ()
    register_links: RegisterLinkConfig = field(default_factory=RegisterLinkConfig)
    automations: Mapping[str, AutomationConfig] = field(default_factory=dict)
    # Ruta del YAML del que salió esta configuración. Se usa para resolver las
    # rutas de los scripts de automatización relativas al propio YAML, en vez
    # de al directorio de trabajo actual.
    source_path: Optional[Path] = None

    # Claves de primer nivel que reconoce el YAML.
    _TOP_LEVEL_KEYS = frozenset({
        "serial", "log", "highlights", "register_links", "automations",
    })

    @classmethod
    def from_dict(cls, name: str, data: Mapping[str, Any],
                  source_path: Optional[Path] = None) -> "DeviceConfig":
        """Valida un YAML ya parseado y devuelve la configuración tipada."""
        if not isinstance(data, Mapping):
            raise ConfigError(
                f"El YAML de '{name}' debe ser un mapa de claves en el primer nivel."
            )

        unknown = set(data) - cls._TOP_LEVEL_KEYS
        if unknown:
            ui.warn("CONFIG",
                    f"{name}: sección(es) desconocida(s) ignorada(s): "
                    f"{', '.join(sorted(unknown))}. "
                    f"Válidas: {', '.join(sorted(cls._TOP_LEVEL_KEYS))}")

        base_dir = source_path.parent if source_path else None

        return cls(
            name=name,
            serial=_build(SerialConfig, data.get("serial"), f"{name}: serial"),
            log=_build(LogConfig, data.get("log"), f"{name}: log"),
            highlights=cls._build_highlights(data.get("highlights"), name),
            register_links=_build(RegisterLinkConfig, data.get("register_links"),
                                  f"{name}: register_links"),
            automations=cls._build_automations(data.get("automations"), name, base_dir),
            source_path=source_path,
        )

    # -- constructores de las partes con forma propia ----------------------

    @staticmethod
    def _build_highlights(raw: Any, name: str) -> tuple[HighlightRule, ...]:
        if not raw:
            return ()
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ConfigError(f"{name}: 'highlights' debe ser una lista de reglas.")
        rules = []
        for i, item in enumerate(raw):
            if not isinstance(item, Mapping) or "pattern" not in item:
                raise ConfigError(
                    f"{name}: highlights[{i}] debe ser un mapa con al menos 'pattern'."
                )
            rules.append(_build(HighlightRule, item, f"{name}: highlights[{i}]"))
        return tuple(rules)

    @staticmethod
    def _build_automations(raw: Any, name: str,
                           base_dir: Optional[Path]) -> dict[str, AutomationConfig]:
        if not raw:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{name}: 'automations' debe ser un mapa nombre → opciones.")

        out: dict[str, AutomationConfig] = {}
        for auto_name, spec in raw.items():
            if not isinstance(spec, Mapping) or "script" not in spec:
                raise ConfigError(
                    f"{name}: la automatización '{auto_name}' necesita una clave 'script'."
                )
            # Una clave 'script:' presente pero vacía se lee como None. Sin esta
            # comprobación acababa convertida en la ruta literal 'None' y el
            # fallo solo aparecía al invocar la automatización.
            raw_script = spec["script"]
            if raw_script is None or not str(raw_script).strip():
                raise ConfigError(
                    f"{name}: la automatización '{auto_name}' tiene 'script' vacío."
                )
            script = Path(str(raw_script).strip()).expanduser()
            # Resolución de la ruta del script: primero relativa al YAML (así
            # una configuración de dispositivo funciona desde cualquier
            # directorio de trabajo), y si ahí no existe, relativa al CWD
            # (comportamiento histórico, se mantiene por compatibilidad).
            if not script.is_absolute() and base_dir is not None:
                candidate = base_dir / script
                if candidate.exists():
                    script = candidate
            out[auto_name] = AutomationConfig(
                name=auto_name,
                script=script,
                description=str(spec.get("description", "")),
            )
        return out

    def as_dict(self) -> dict[str, Any]:
        """Vuelca la configuración a dict (útil en tests y depuración)."""
        return dataclasses.asdict(self)
