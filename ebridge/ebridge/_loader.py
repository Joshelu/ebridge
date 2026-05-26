"""
Resolución de archivos de configuración de dispositivos.

Orden de búsqueda para ``load_device_config("nombre")``:

1. ``devices/nombre.yaml``  en el directorio de trabajo actual  (proyecto del usuario)
2. ``devices/nombre.yml``   en el directorio de trabajo actual
3. Configuraciones incluidas en el paquete  (``ebridge/devices/``)

Esto permite:
- Sobrescribir cualquier dispositivo incluido simplemente creando un
  archivo ``devices/<nombre>.yaml`` en el proyecto del usuario.
- Usar los dispositivos de ejemplo del paquete sin configuración adicional.
"""

from __future__ import annotations

import sys
from pathlib import Path
from ebridge._ansi import cprint


def load_device_config(device_name: str) -> dict:
    """
    Carga y devuelve la configuración YAML del dispositivo indicado.

    Args:
        device_name: Nombre del dispositivo (con o sin extensión ``.yaml``).

    Returns:
        Diccionario con la configuración del dispositivo.

    Raises:
        SystemExit: Si no se encuentra ningún archivo de configuración.
    """
    import yaml  # importación diferida para no penalizar imports de __init__

    name = device_name.removesuffix(".yaml").removesuffix(".yml")

    # ── 1. Buscar en el directorio de trabajo del usuario ──────────────
    cwd_candidates = [
        Path(f"devices/{name}.yaml"),
        Path(f"devices/{name}.yml"),
        Path(name),             # ruta absoluta o relativa completa
    ]
    for path in cwd_candidates:
        if path.exists():
            config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cprint(f"\033[90m[SYS] Configuración cargada: {path.resolve()}\033[0m")
            return config

    # ── 2. Buscar en los dispositivos incluidos en el paquete ───────────
    try:
        # importlib.resources.files() — Python ≥ 3.9, disponible incluso
        # cuando el paquete está instalado como wheel (sin archivos sueltos).
        from importlib.resources import files as _res_files
        pkg_devices = _res_files("ebridge.devices")
        for ext in (".yaml", ".yml"):
            resource = pkg_devices.joinpath(f"{name}{ext}")
            try:
                text   = resource.read_text(encoding="utf-8")
                config = yaml.safe_load(text) or {}
                cprint(
                    f"\033[90m[SYS] Configuración cargada desde el paquete: "
                    f"ebridge/devices/{name}{ext}\033[0m"
                )
                return config
            except (FileNotFoundError, TypeError):
                continue
    except Exception:
        pass

    # ── 3. No encontrado ────────────────────────────────────────────────
    searched = [str(p) for p in cwd_candidates] + [
        f"ebridge/devices/{name}.yaml (incluido en el paquete)"
    ]
    cprint(
        f"\033[91m[ERROR] No se encontró la configuración del dispositivo "
        f"'{device_name}'.\n"
        f"        Rutas buscadas:\n" +
        "\n".join(f"          - {s}" for s in searched) +
        "\033[0m"
    )
    sys.exit(1)
