# Changelog

Todas las novedades relevantes de eBridge. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
[SemVer](https://semver.org/lang/es/).

## [2.0.0] — 2026-09-04

Versión mayor porque cambia la API programática. El uso desde la línea de
comandos y los scripts de automatización existentes siguen funcionando igual.

### Licencia

- **Resuelta la contradicción de licencia.** El repositorio declaraba GPL-3.0
  en `LICENSE` y MIT en `pyproject.toml`. La licencia efectiva es
  **GPL-3.0-or-later**.
- `pyproject.toml` usa ahora el campo `license` como expresión SPDX y
  `license-files` (PEP 639), de modo que el wheel y el sdist incluyen el texto
  de la licencia. Antes se publicaban sin ningún fichero de licencia.
- Todos los ficheros fuente llevan cabecera `SPDX-License-Identifier` y línea
  de copyright (Jose Luis Alcoba Huertas).
- Añadidos `authors`, `classifiers`, `keywords` y `urls` al paquete.
- El banner de arranque muestra el aviso de garantía que pide la GPL-3.0 para
  programas interactivos.

### Corregido

- **`--log` reventaba con cualquier dispositivo sin sección `log:` en el
  YAML.** `SessionLogger` hacía `Path(directory + filepath)` con `directory`
  valiendo `None`, así que `ebridge example_device --port COM3 --log s.log`
  moría con `TypeError` antes de arrancar. La ruta se compone ahora con
  `Path`, que además admite `~` y no obliga a poner la barra final en el YAML.
- **`load_device_config()` llamaba a `sys.exit(1)`.** Una función de librería
  no puede matar el proceso: quien usaba `run_terminal()` desde otro programa
  no podía capturar el fallo. Ahora lanza `DeviceConfigError`.
- **La salida se rompía sin consola disponible.** `print_formatted_text` lanza
  `NoConsoleScreenBufferError` con la salida redirigida, en CI o bajo pytest.
  `ui.cprint()` degrada a `print()` en texto plano.
- **El resaltado se aplicaba en cascada sobre texto ya coloreado**, así que una
  regla numérica podía casar dentro de un `\x1b[91m` y corromper la línea. Las
  coincidencias se calculan ahora sobre el texto original, en una sola pasada.
- **`MessageBus.dispatch_rx()` recorría la lista de suscriptores mientras
  hacía `await`.** Una automatización que terminase en ese hueco mutaba la
  lista en plena iteración. Se itera sobre una copia.
- **Un cliente TCP lento bloqueaba a todos los demás:** el bucle de difusión
  mantenía el lock durante `writer.drain()`. Cada cliente tiene ahora su propia
  cola acotada y su propia tarea de escritura.
- **Una automatización editada podía seguir ejecutando la versión anterior**
  por la caché de `__pycache__` (validada por mtime y tamaño). El script se
  compila directamente desde el fuente en cada invocación.
- `asyncio.get_event_loop()` (deprecado) sustituido por `get_running_loop()`.
- Eliminada la dependencia `colorama`, que estaba declarada y no se usaba.
- `SerialInterface._eol` estaba anotado `-> str` y devolvía `bytes`.

### Estructura del repositorio

- **Aplanado el triple anidamiento** `ebridge/ebridge/ebridge/`. La raíz del
  repositorio es ahora también la raíz del paquete: `pyproject.toml`,
  `LICENSE`, `README.md`, `CHANGELOG.md`, `ebridge/` (el paquete), `tests/`,
  `automations/` y `examples/`. Ya no hacen falta dos copias de `LICENSE` ni
  dos `README.md`.
- Las automatizaciones **de ejemplo** se han movido a `examples/automations/`.
  No se han unificado con `automations/`, que son las que están en uso: son
  cosas distintas y pueden diferir a propósito. El README lo deja explícito.
- `.vscode/launch.json` apunta a `${workspaceFolder}` y añade configuraciones
  para pytest. Antes `python -m ebridge` no encontraba el
  paquete desde la raíz del workspace.

### Añadido

- **Reconexión automática del puerto serie** (`serial.reconnect`, desactivada
  por defecto; `serial.reconnect_delay` controla el intervalo). Cuando el
  puerto desaparece —desenchufar el USB, reprogramar o reiniciar el
  dispositivo— eBridge reintenta abrirlo en lugar de quedarse colgado de un
  puerto muerto. Lo que se escriba mientras está caído espera en la cola y se
  envía al reconectar. La caída y la recuperación se publican como mensajes
  de sistema, de modo que llegan también al log de sesión y a los clientes del
  bridge TCP. Sirve igualmente al arrancar: se puede lanzar eBridge antes de
  enchufar el dispositivo.
- Con la reconexión resuelta apareció un caso límite propio: un mensaje sacado
  de la cola de TX en el mismo instante en que caía el enlace se perdía al
  cancelar la espera. Ahora se guarda y se envía al reconectar.
- `ebridge/ui.py`: capa de salida semántica (`ui.ok`, `ui.warn`, `ui.error`,
  `ui.note`, `ui.info`). **Es el único sitio del proyecto donde deben aparecer
  códigos ANSI escritos a mano.**
- `--no-color` y soporte de la variable de entorno `NO_COLOR`.
- `--version`.
- `ebridge/core/config.py`: configuración YAML tipada y validada. Los valores
  por defecto viven en un único sitio, los valores inválidos dan un error
  legible y **las claves mal escritas se avisan** en lugar de ignorarse.
- `ebridge/core/registry.py`: registro de interfaces. Añadir una interfaz es
  un módulo con `@register("nombre")` más una línea de import, sin tocar el
  runner ni la CLI.
- `ebridge/errors.py`: jerarquía de excepciones (`EBridgeError`,
  `ConfigError`, `DeviceConfigError`, `AutomationError`, `InterfaceError`).
- `BaseInterface.stop()` ahora forma parte del ciclo de vida: el runner la
  llama siempre al cerrar, incluso si `run()` ha fallado.
- Las automatizaciones de varios ficheros pueden importar módulos hermanos sin
  parchear `sys.path`.
- Las rutas de `script:` se resuelven relativas al YAML del dispositivo, de
  modo que una configuración funciona desde cualquier directorio de trabajo.
- `/list` y `/help` muestran la descripción de cada automatización.
- Aviso al escuchar en `0.0.0.0`: el bridge TCP no tiene autenticación.
- Códigos de salida: `0` correcto, `1` error de configuración, `130` Ctrl+C.
- Suite de tests con pytest (`pip install -e ".[dev]" && pytest`).

### Cambios incompatibles (API programática)

| Antes | Ahora |
|---|---|
| `load_device_config()` devuelve `dict` | devuelve `DeviceConfig` |
| `load_device_config()` hace `sys.exit(1)` | lanza `DeviceConfigError` |
| `Highlighter(lista_de_dicts)` | `Highlighter(iterable de HighlightRule)` |
| `RegisterLinker(dict)` | `RegisterLinker(RegisterLinkConfig)` |
| `SerialInterface(bus, port, dict)` | `SerialInterface(bus, port, SerialConfig)` |
| `SessionLogger(ruta, dict)` | `SessionLogger(ruta, LogConfig)` |
| `AutomationEngine(bus, dict)` | `AutomationEngine(bus, mapa de AutomationConfig)` |
| `engine.run_automation(nombre, args, print_fn)` | `engine.run_automation(nombre, args)` |
| `cli.main()` no devuelve nada | devuelve el código de salida |

`run_terminal()` mantiene la misma firma. Los scripts de automatización no
cambian: `ctx.send`, `ctx.wait_for`, `ctx.debug` y `ctx.args` siguen igual.

## [1.0.0] — 2026-04-29

Primera versión: terminal serie interactivo, bridge TCP, resaltado por
expresiones regulares configurable por dispositivo, motor de automatizaciones,
log de sesión y enlaces OSC 8 al explorador de registros.
