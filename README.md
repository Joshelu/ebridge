# eBridge — Enhanced Bridge

eBridge (**Enhanced Bridge**) es un terminal serie interactivo con bridge TCP, resaltado de texto configurable por dispositivo y sistema de automatizaciones basado en el patrón productor/consumidor.

---

## Características

- **Terminal interactivo** con historial de comandos persistente y autocompletado
- **Bridge TCP** bidireccional: controla el puerto serie desde `netcat`, `telnet` o cualquier script externo simultáneamente al terminal
- **Configuración por dispositivo** en YAML: parámetros serie, resaltado regex y automatizaciones, todo en un único archivo
- **Resaltado de texto** con expresiones regulares y colores ANSI configurables por dispositivo
- **Automatizaciones** asíncronas: scripts de Python con una API de alto nivel para enviar comandos, esperar respuestas y mostrar mensajes de debug, sin bloquear el terminal ni el socket
- **Log de sesión** en fichero de texto plano con timestamp y fuente de cada mensaje
- **Arquitectura productor/consumidor** que permite añadir nuevas interfaces (MQTT, Bluetooth, HTTP…) sin modificar el código existente
- **Compatible con Windows Terminal**, Linux y macOS

---

## Instalación

### Como paquete (recomendado)

```bash
pip install ebridge
```

O directamente desde el repositorio:

```bash
git clone <repo>
cd ebridge
pip install .
```

Para desarrollo con recarga en caliente:

```bash
pip install -e .
```

### Requisitos

- Python 3.10 o superior
- Las dependencias se instalan automáticamente con el paquete:
  , , , 

---

## Inicio rápido

Tras instalar el paquete, el comando `ebridge` queda disponible globalmente:

```bash
# Linux / macOS
ebridge example_device --port /dev/ttyUSB0

# Windows (PowerShell)
ebridge example_device --port COM3

# Con log de sesión y socket en puerto personalizado
ebridge example_device --port COM3 --log sesion.log --socket-port 5001

# Sin servidor socket
ebridge example_device --port /dev/ttyUSB0 --no-socket
```

También se puede invocar directamente como módulo Python (sin instalar el comando):

```bash
python -m ebridge example_device --port /dev/ttyUSB0
```

O integrarlo en un script Python:

```python
import asyncio
from ebridge import run_terminal

asyncio.run(run_terminal(
    device      = example_device,
    port        = /dev/ttyUSB0,
    socket_port = 5000,
    log_file    = sesion.log,
))
```

---

## Argumentos de línea de comandos

| Argumento | Alias | Descripción | Por defecto |
|---|---|---|---|
| `device` | | Nombre del dispositivo. Debe existir como `devices/<nombre>.yaml` | — |
| `--port` | `-p` | Puerto serie (`/dev/ttyUSB0`, `COM3`…) | — |
| `--socket-port` | `-s` | Puerto TCP del servidor socket | `5000` |
| `--socket-host` | | Dirección de escucha del socket | `0.0.0.0` |
| `--no-socket` | | Deshabilita el servidor socket | `false` |
| `--log` | `-l` | Fichero de log de sesión. Si es un nombre suelto, se guarda bajo `log.directory` del YAML | desactivado |
| `--no-color` | | Desactiva los colores ANSI (también se respeta la variable de entorno `NO_COLOR`) | `false` |
| `--verbose` | `-v` | Activa el logging interno detallado, con tracebacks de las automatizaciones | `false` |
| `--version` | | Muestra la versión y sale | — |

El proceso devuelve `0` si todo va bien, `1` si la configuración del
dispositivo no existe o es inválida, y `130` si se interrumpe con Ctrl+C.

---

## Comandos del terminal

Una vez iniciado, el terminal acepta los siguientes comandos:

| Entrada | Acción |
|---|---|
| Cualquier texto | Se envía directamente al puerto serie |
| `/nombre_automatizacion [args...]` | Ejecuta una automatización |
| `/list` | Lista las automatizaciones disponibles para el dispositivo |
| `/help` | Muestra la ayuda |
| `/quit` o `Ctrl+D` | Sale del programa limpiamente |
| `Ctrl+C` | Limpia la línea actual (no sale) |

**Ejemplo:**
```
example_device $ hola mundo        ← se envía al serie
example_device $ /ponfecha 27 4    ← ejecuta la automatización ponfecha con args 27 y 4
example_device $ /list             ← muestra: ponfecha, reset
example_device $ /quit             ← cierra el programa
```

---

## Bridge TCP (socket)

Al arrancar, el terminal levanta un servidor TCP en el puerto indicado (por defecto `5000`). Cualquier cliente que se conecte puede:

- **Recibir** en tiempo real todos los datos que llegan del puerto serie
- **Enviar** comandos que serán reenviados al puerto serie, igual que si se escribiesen en el terminal

```bash
# Conectar desde otra terminal
nc 127.0.0.1 5000

# O desde un script Python
import socket
s = socket.socket()
s.connect(('127.0.0.1', 5000))
s.sendall(b'mi comando\n')
respuesta = s.recv(1024)
```

El terminal y el socket operan de forma completamente simultánea e independiente.

---

## Configuración de dispositivos

Cada dispositivo tiene su propio archivo YAML en el directorio `devices/`. El nombre del archivo (sin extensión) es el que se pasa como argumento al arrancar.

### Estructura del archivo YAML

```yaml
# devices/mi_dispositivo.yaml

# ── Puerto serie ─────────────────────────────────────────────
serial:
  baudrate: 9600
  bytesize: 8       # 5 | 6 | 7 | 8
  parity:   N       # N=None | E=Even | O=Odd | M=Mark | S=Space
  stopbits: 1       # 1 | 1.5 | 2
  timeout:  0.1     # segundos de timeout de lectura
  eol:      "\r\n"  # fin de línea para TX: \n | \r | \r\n
  encoding: utf-8   # codificación de caracteres

  # Reapertura automática del puerto (ver más abajo)
  reconnect:       false
  reconnect_delay: 2.0

  # Envío troceado, para dispositivos con FIFO de recepción pequeño
  tx_chunk_size:  0      # 0 = desactivado
  tx_chunk_delay: 0.01   # segundos entre trozos

# ── Resaltado de texto ────────────────────────────────────────
highlights:
  - pattern: "\\bOK\\b"
    color:   green
  - pattern: "\\bERROR\\b"
    color:   bold_red

# ── Automatizaciones ──────────────────────────────────────────
automations:
  ponfecha:
    script:      automations/ponfecha.py
    description: "Establece la fecha en el dispositivo"
  reset:
    script:      automations/reset.py
    description: "Reinicia el dispositivo"
```

### Reconexión automática del puerto

Con `serial.reconnect: true`, eBridge recupera el puerto por su cuenta cuando
se pierde: al desenchufar y volver a enchufar el USB, al reprogramar el
dispositivo o al reiniciarlo.

```yaml
serial:
  reconnect:       true
  reconnect_delay: 2.0   # segundos entre reintentos
```

Qué ocurre exactamente:

- El terminal avisa una vez de que el enlace ha caído y empieza a reintentar
  en silencio, para no llenar la pantalla mientras el dispositivo está fuera.
- **Lo que escribas mientras está caído no se pierde**: espera en la cola de
  envío y sale en cuanto vuelve el puerto.
- Al recuperarlo, avisa con `Puerto reabierto`.
- La caída y la recuperación se registran como mensajes de sistema, así que
  aparecen en el log de sesión y les llegan a los clientes del bridge TCP.
- Si `reconnect` está desactivado (por defecto), perder el puerto cierra la
  interfaz serie, que es el comportamiento de siempre.

También cubre el arranque: con `reconnect: true` puedes lanzar eBridge antes
de enchufar el dispositivo y esperará a que aparezca.

### Colores disponibles para el resaltado

| Nombre | Nombre | Nombre |
|---|---|---|
| `red` | `green` | `yellow` |
| `blue` | `magenta` | `cyan` |
| `white` | `orange` | `bold_red` |
| `bold_green` | `bold` | `dim` |

### Dispositivos de ejemplo incluidos

| Archivo | Descripción |
|---|---|
| `devices/example_device.yaml` | Dispositivo genérico a 9600 baudios con resaltado de OK/ERROR, fechas, IPs y hexadecimales |
| `devices/gps_module.yaml` | Módulo GPS a 4800 baudios con resaltado de tramas NMEA |

---

## Automatizaciones

Las automatizaciones permiten ejecutar secuencias de comandos sobre el dispositivo de forma asíncrona, sin bloquear el terminal ni el socket. Se invocan desde el terminal con `/nombre_automatizacion [args...]`.

### Cómo crear una automatización

Crea un archivo `.py` en el directorio `automations/` con la función `async def run(ctx, *args)`:

```python
# automations/mi_automatizacion.py

async def run(ctx, *args):
    ctx.debug("Iniciando mi automatización")

    # Envía un comando al puerto serie
    await ctx.send("mi_comando")

    # Espera una respuesta que coincida con el patrón regex (timeout en segundos)
    try:
        respuesta = await ctx.wait_for(r"OK|ERROR", timeout=5.0)
    except TimeoutError:
        ctx.debug("El dispositivo no respondió")
        return

    if "OK" in respuesta:
        ctx.debug("Comando aceptado, enviando siguiente paso...")
        await ctx.send("siguiente_comando")
        respuesta = await ctx.wait_for(r"OK|ERROR", timeout=5.0)

    ctx.debug(f"Resultado final: {respuesta}")
```

Luego regístrala en el YAML del dispositivo:

```yaml
automations:
  mi_automatizacion:
    script:      automations/mi_automatizacion.py
    description: "Descripción de lo que hace"
```

Y ejecútala desde el terminal:
```
mi_dispositivo $ /mi_automatizacion arg1 arg2
```

### API del contexto (`ctx`)

| Método | Descripción |
|---|---|
| `await ctx.send(comando)` | Envía un comando al puerto serie. También lo muestra en el terminal con el prefijo `[AUTO]` |
| `await ctx.wait_for(patron, timeout=5.0)` | Espera un mensaje del serie que coincida con la expresión regular `patron`. Lanza `TimeoutError` si se agota el tiempo |
| `ctx.debug(mensaje)` | Imprime un mensaje de debug en el terminal con el prefijo `[AUTO]` |
| `ctx.args` | Lista de argumentos posicionales pasados a la automatización |

### Automatizaciones de varios ficheros

El directorio del script se añade a `sys.path` durante la carga, así que un
script puede importar módulos hermanos directamente:

```python
# automations/mi_automatizacion.py
import mi_ayudante          # automations/mi_ayudante.py

async def run(ctx, *args):
    await ctx.send(mi_ayudante.construir_comando(args))
```

El script se recompila en cada invocación: al editarlo y volver a lanzarlo se
ejecuta la versión nueva sin reiniciar el terminal.

Las rutas de `script:` se resuelven primero **relativas al propio YAML** y, si
ahí no existe el fichero, relativas al directorio de trabajo. Gracias a eso una
configuración de dispositivo funciona desde cualquier directorio.

> Una automatización es código Python que se ejecuta con los permisos del
> usuario. Un YAML de dispositivo de origen desconocido debe tratarse con el
> mismo cuidado que cualquier código de origen desconocido.

### Automatizaciones incluidas

#### `ponfecha`
Establece el día y el mes en el dispositivo mediante los comandos `set day` y `set mes`, esperando confirmación `OK` entre cada paso.

```
example_device $ /ponfecha          ← usa la fecha actual del sistema
example_device $ /ponfecha 27       ← día 27, mes actual
example_device $ /ponfecha 27 4     ← día 27, mes 4
```

#### `reset`
Envía el comando `reset` y espera la confirmación de arranque del dispositivo (`READY`, `BOOT` o `OK`) con un timeout de 10 segundos.

```
example_device $ /reset
```

---

## Log de sesión

Con `--log fichero.log`, todos los mensajes de la sesión se guardan en un fichero de texto plano sin códigos de color, con timestamp y etiqueta de fuente:

```
======================================================================
Sesión iniciada: 2025-04-28T10:32:01.123456
======================================================================
[10:32:01.234] <<< SERIAL        [DEBUG] Button OK: state RELEASED
[10:32:02.100] >>> TERMINAL      reset
[10:32:02.350] <<< SERIAL        READY
[10:32:05.000] >>> SOCKET        status
[10:32:05.120] <<< SERIAL        running
[10:32:05.200]     AUTO          Iniciando 'ponfecha' con args=['27', '4']
[10:32:05.210] >>> SERIAL        set day 27
[10:32:05.310] <<< SERIAL        OK
[10:32:05.320] >>> SERIAL        set mes 4
[10:32:05.410] <<< SERIAL        OK

Sesión terminada: 2025-04-28T10:35:44.789012
```

| Etiqueta | Origen |
|---|---|
| `<<< SERIAL` | Datos recibidos del puerto serie |
| `>>> SERIAL` | Datos enviados al puerto serie |
| `>>> TERMINAL` | Comandos escritos por el usuario |
| `>>> SOCKET` | Comandos recibidos de un cliente socket |
| `    AUTO` | Mensajes de automatizaciones |
| `    SYSTEM` | Mensajes internos del sistema |

---

## Arquitectura

El sistema se basa en el patrón **productor/consumidor** implementado con `asyncio`. Todos los componentes se comunican exclusivamente a través del `MessageBus` central, sin referencias directas entre sí.

```
                        ┌─────────────────────────────────┐
                        │           MessageBus             │
                        │                                  │
  SerialReader ────────►│ dispatch_rx() ──► rx_subscribers │──► TerminalDisplay
  (hilo Python)         │                                  │──► SocketBroadcast
                        │                                  │──► AutomationWait
                        │                                  │──► SessionLogger
                        │                                  │
  Terminal   ──────────►│ send_to_serial() ──► tx_queue    │──► SerialWriter
  Socket     ──────────►│                                  │    (hilo Python)
  Automation ──────────►│                  ──► log_queue   │──► SessionLogger
                        └─────────────────────────────────┘
```

### Componentes

| Módulo | Responsabilidad |
|---|---|
| `core/message_bus.py` | Bus central: colas asyncio, suscripción pub/sub y enrutamiento de mensajes |
| `core/interfaces/serial_interface.py` | Puente entre pyserial (bloqueante, hilos) y asyncio |
| `core/interfaces/socket_interface.py` | Servidor TCP: acepta clientes y hace broadcast de los datos RX |
| `core/interfaces/terminal_interface.py` | Terminal interactivo basado en prompt_toolkit |
| `core/automation_engine.py` | Carga y ejecuta scripts de automatización; provee `AutomationContext` |
| `core/highlighter.py` | Aplica colores ANSI a texto mediante reglas regex configurables |
| `core/logger.py` | Consume el log_queue y escribe en fichero |
| `core/interfaces/base.py` | Clase base abstracta para nuevas interfaces |

### Añadir una nueva interfaz

Para integrar una nueva fuente/destino de comunicación (MQTT, Bluetooth, HTTP, WebSocket…):

1. Crea un archivo en `core/interfaces/` que subclasee `BaseInterface`
2. Implementa `async def run(self)` con la lógica productora/consumidora:
   - Para **recibir** datos del serie: `q = bus.create_rx_subscriber()` y luego `await q.get()`
   - Para **enviar** datos al serie: `await bus.send_to_serial(Message(...))`
   - Opcionalmente, implementa `async def stop(self)` para liberar recursos
     al cerrar (el runner la llama siempre, aunque `run()` haya fallado)
3. Registra una factoría con el decorador `@register("nombre")`
4. Añade la línea de import en `core/interfaces/__init__.py`

```python
# ebridge/core/interfaces/mqtt_interface.py
from ebridge.core.interfaces.base import BaseInterface
from ebridge.core.registry import BuildContext, register

class MqttInterface(BaseInterface):
    async def run(self) -> None:
        ...

@register("mqtt")
def _build(ctx: BuildContext) -> MqttInterface | None:
    # Devolver None desactiva la interfaz en esta sesión
    return MqttInterface(bus=ctx.bus, config=ctx.config)
```

No hay que tocar el runner ni el parser de la línea de comandos: el runner
pregunta al registro qué interfaces construir y las arranca todas por igual.

Una interfaz marcada con `@register("nombre", primary=True)` gobierna la vida
del programa: cuando termina, el runner cierra el resto. El terminal es la
primaria por defecto.

---

## Estructura del proyecto

```
ebridge/                         ← raíz del repositorio Y del paquete
├── pyproject.toml                       ← definición del paquete instalable
├── LICENSE                              ← GPL-3.0
├── CHANGELOG.md
├── README.md
│
├── ebridge/                     ← paquete Python instalable
│   ├── __init__.py                      ← versión y API pública (run_terminal)
│   ├── __main__.py                      ← habilita python -m ebridge
│   ├── cli.py                           ← punto de entrada del comando instalado
│   ├── ui.py                            ← ÚNICO sitio con códigos ANSI
│   ├── errors.py                        ← jerarquía de excepciones
│   ├── _runner.py                       ← lógica async compartida por CLI y API
│   ├── _loader.py                       ← resolución de archivos de dispositivo
│   │
│   ├── core/
│   │   ├── config.py                    ← configuración YAML tipada y validada
│   │   ├── message_bus.py               ← bus central de mensajes
│   │   ├── registry.py                  ← registro de interfaces
│   │   ├── highlighter.py               ← resaltado regex con ANSI
│   │   ├── register_linker.py           ← enlaces OSC 8 a registros
│   │   ├── logger.py                    ← log de sesión en fichero
│   │   ├── automation_engine.py         ← motor de automatizaciones
│   │   └── interfaces/
│   │       ├── __init__.py              ← registra las interfaces incluidas
│   │       ├── base.py                  ← clase base abstracta
│   │       ├── serial_interface.py      ← interfaz puerto serie
│   │       ├── socket_interface.py      ← servidor TCP
│   │       ├── log_interface.py         ← adaptador del log al registro
│   │       └── terminal_interface.py    ← terminal interactivo
│   │
│   └── devices/                         ← configs incluidas en el paquete
│       ├── example_device.yaml
│       └── gps_module.yaml
│
├── tests/                       ← suite de pytest
│
├── automations/                 ← automatizaciones EN USO
│   ├── ponfecha.py
│   └── reset.py
│
└── examples/
    └── automations/             ← automatizaciones de EJEMPLO (plantillas)
        ├── ponfecha.py
        └── reset.py
```

> **`automations/` y `examples/automations/` no son lo mismo y no deben
> unificarse.** `automations/` son las que se usan de verdad (las que
> referencian los YAML de `ebridge/devices/`). `examples/automations/` son
> plantillas de referencia para escribir automatizaciones nuevas

### Convenciones para quien toque el código

- **Nada de códigos ANSI fuera de `ui.py`.** El resto del código llama a
  `ui.ok()`, `ui.warn()`, `ui.error()`, `ui.note()`, `ui.info()`. Así
  `--no-color` y cualquier cambio de paleta siguen funcionando en todo el
  programa sin tocar más de un archivo.
- **El núcleo no imprime errores fatales ni llama a `sys.exit()`.** Lanza una
  excepción de `ebridge.errors` y deja que la CLI decida el mensaje y el
  código de salida. Así eBridge sigue siendo usable como librería.
- **Las opciones del YAML se declaran en `core/config.py`**, no con
  `dict.get()` repartidos por el código. Añadir una opción es añadir un campo
  a la dataclass correspondiente; las claves desconocidas se avisan al
  arrancar en lugar de ignorarse en silencio.

### Tests

```bash
pip install -e ".[dev]"
pytest
```

### Orden de resolución de dispositivos

Al ejecutar `ebridge mi_dispositivo --port ...`, el paquete busca la
configuración en este orden:

1. `devices/mi_dispositivo.yaml` en el **directorio de trabajo actual** (permite sobrescribir o añadir dispositivos sin modificar el paquete)
2. Configuraciones **incluidas en el paquete** (`ebridge/devices/`)

Esto significa que los usuarios pueden añadir sus propios dispositivos creando
una carpeta `devices/` en su proyecto, sin necesidad de tocar el paquete instalado.

---

## Notas de compatibilidad

### Windows Terminal (PowerShell)

Los colores ANSI funcionan correctamente en Windows Terminal mediante `print_formatted_text(ANSI(...))` de prompt_toolkit. **No usar `cmd.exe`** ya que no tiene soporte completo de VT100.

### Virtual environments

```powershell
# Crear y activar el entorno virtual (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install ebridge
ebridge example_device --port COM3
```

```bash
# Linux / macOS
python -m venv .venv
source .venv/bin/activate
pip install ebridge
ebridge example_device --port /dev/ttyUSB0
```

---

## Licencia

eBridge se distribuye bajo la **GNU General Public License v3.0 o posterior**
(`GPL-3.0-or-later`). El texto completo está en [LICENSE](LICENSE).

    Copyright (C) 2026  Jose Luis Alcoba Huertas

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

Cada fichero fuente lleva la cabecera `SPDX-License-Identifier: GPL-3.0-or-later`.
Las dependencias (pyserial, PyYAML, prompt_toolkit) son todas permisivas
(BSD/MIT) y por tanto compatibles con la GPL-3.0.
