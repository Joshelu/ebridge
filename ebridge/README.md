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
| `--log` | `-l` | Ruta del fichero de log de sesión | desactivado |
| `--verbose` | `-v` | Activa el logging interno detallado | `false` |

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
| `await ctx.send(comando)` | Envía un comando al puerto serie. También lo muestra en el terminal con el prefijo `[AUTO >>]` |
| `await ctx.wait_for(patron, timeout=5.0)` | Espera un mensaje del serie que coincida con la expresión regular `patron`. Lanza `TimeoutError` si se agota el tiempo |
| `ctx.debug(mensaje)` | Imprime un mensaje de debug en el terminal con el prefijo `[AUTO   ]` |
| `ctx.args` | Lista de argumentos posicionales pasados a la automatización |

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
[10:32:01.234] <<< SERIAL        2459.550: [DEBUG] Button OK: state RELEASED
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
2. Implementa el método `async def run(self)` con la lógica productora/consumidora:
   - Para **recibir** datos del serie: `q = bus.create_rx_subscriber()` y luego `await q.get()`
   - Para **enviar** datos al serie: `await bus.send_to_serial(Message(...))`
3. Instancia la clase en `main.py` y añade `asyncio.create_task(mi_interfaz.run())` a la lista de tareas

No es necesario modificar ningún otro componente.

---

## Estructura del proyecto

```
ebridge/                         ← raíz del repositorio
├── pyproject.toml                       ← definición del paquete instalable
├── README.md
│
├── ebridge/                     ← paquete Python instalable
│   ├── __init__.py                      ← versión y API pública (run_terminal)
│   ├── __main__.py                      ← habilita python -m ebridge
│   ├── cli.py                           ← punto de entrada del comando instalado
│   ├── _runner.py                       ← lógica async compartida por CLI y API
│   ├── _loader.py                       ← resolución de archivos de dispositivo
│   │
│   ├── core/
│   │   ├── message_bus.py               ← bus central de mensajes
│   │   ├── highlighter.py               ← resaltado regex con ANSI
│   │   ├── logger.py                    ← log de sesión en fichero
│   │   ├── automation_engine.py         ← motor de automatizaciones
│   │   └── interfaces/
│   │       ├── base.py                  ← clase base abstracta
│   │       ├── serial_interface.py      ← interfaz puerto serie
│   │       ├── socket_interface.py      ← servidor TCP
│   │       └── terminal_interface.py    ← terminal interactivo
│   │
│   └── devices/                         ← configs incluidas en el paquete
│       ├── example_device.yaml
│       └── gps_module.yaml
│
└── automations/                         ← ejemplos de automatizaciones de usuario
    ├── ponfecha.py
    └── reset.py
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
