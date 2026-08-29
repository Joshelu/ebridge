# eBridge — Enhanced Bridge

eBridge (**Enhanced Bridge**) es un terminal serie interactivo con bridge TCP, resaltado de texto configurable por dispositivo y sistema de automatizaciones, construido sobre un patrón productor/consumidor que permite extenderlo con nuevas interfaces sin modificar el código existente.

---

## Características

- **Terminal interactivo** con historial de comandos persistente y autocompletado
- **Bridge TCP** bidireccional: controla el puerto serie desde `netcat`, `telnet` o scripts externos al mismo tiempo que el terminal
- **Configuración por dispositivo** en YAML: parámetros serie, resaltado regex y automatizaciones en un único archivo
- **Resaltado de texto** con expresiones regulares y colores ANSI configurables por dispositivo
- **Automatizaciones** asíncronas: scripts de Python con una API de alto nivel para enviar comandos y esperar respuestas sin bloquear el terminal ni el socket
- **Log de sesión** en fichero de texto plano con timestamp y fuente de cada mensaje
- **Chunking de escritura** configurable para dispositivos con buffer UART pequeño
- **Arquitectura productor/consumidor** extensible: añadir nuevas interfaces sin tocar el código existente
- **Compatible con Windows Terminal**, PowerShell, Linux y macOS

---

## Requisitos

- Python 3.10 o superior
- Dependencias (se instalan automáticamente): `pyserial`, `pyyaml`, `prompt_toolkit`, `colorama`

---

## Instalación

### Desde el repositorio

```bash
git clone https://github.com/TU_USUARIO/ebridge.git
cd ebridge
python -m pip install -e .
```

La flag `-e` instala en modo editable: cualquier cambio en el código tiene efecto inmediato sin necesidad de reinstalar.

### Nota para entornos corporativos (Azure AD / equipos de empresa)

En equipos unidos a dominio con políticas restrictivas, `pip.exe` puede estar bloqueado. Usa siempre el módulo de Python directamente:

```powershell
# En lugar de:    pip install ...
# Usa siempre:    python -m pip install ...

python -m pip install -e .
```

### Comando `ebridge` en Windows

En entornos corporativos el ejecutable `ebridge.exe` generado por pip puede estar bloqueado por políticas del sistema. La solución es usar el módulo directamente o crear un alias en PowerShell:

```powershell
# Usar directamente (siempre funciona)
python -m ebridge --help

# O crear un alias permanente en el perfil de PowerShell
if (!(Test-Path $PROFILE)) { New-Item $PROFILE -Force }
Add-Content $PROFILE "`nfunction ebridge { python -m ebridge @args }"

# Recargar el perfil para activarlo en la sesión actual
. $PROFILE
```

---

## Inicio rápido

```bash
# Linux / macOS
python -m ebridge example_device --port /dev/ttyUSB0

# Windows (PowerShell)
python -m ebridge example_device --port COM3

# Con log de sesión y socket en puerto personalizado
python -m ebridge example_device --port COM3 --log sesion.log --socket-port 5001

# Sin servidor socket
python -m ebridge example_device --port /dev/ttyUSB0 --no-socket

# Con logging detallado (útil para depuración)
python -m ebridge example_device --port COM3 --verbose
```

### Uso como API Python

```python
import asyncio
from ebridge import run_terminal

asyncio.run(run_terminal(
    device      = "example_device",
    port        = "/dev/ttyUSB0",
    socket_port = 5000,
    log_file    = "sesion.log",
))
```

---

## Argumentos de línea de comandos

| Argumento | Alias | Descripción | Por defecto |
|---|---|---|---|
| `device` | | Nombre del dispositivo (`devices/<nombre>.yaml`) | — |
| `--port` | `-p` | Puerto serie (`/dev/ttyUSB0`, `COM3`…) | — |
| `--socket-port` | `-s` | Puerto TCP del servidor socket | `5000` |
| `--socket-host` | | Dirección de escucha del socket | `0.0.0.0` |
| `--no-socket` | | Deshabilita el servidor socket | `false` |
| `--log` | `-l` | Ruta del fichero de log de sesión | desactivado |
| `--verbose` | `-v` | Activa el logging interno detallado | `false` |

---

## Comandos del terminal

| Entrada | Acción |
|---|---|
| Cualquier texto | Se envía directamente al puerto serie |
| `/nombre_automatizacion [args...]` | Ejecuta una automatización |
| `/list` | Lista las automatizaciones disponibles |
| `/help` | Muestra la ayuda |
| `/quit` o `Ctrl+D` | Sale del programa limpiamente |
| `Ctrl+C` | Limpia la línea actual (no sale) |

```
mi_device $ info                   ← se envía al serie
mi_device $ /ponfecha 27 4         ← ejecuta la automatización ponfecha
mi_device $ /list                  ← muestra automatizaciones disponibles
mi_device $ /quit                  ← cierra el programa
```

---

## Bridge TCP (socket)

Al arrancar, eBridge levanta un servidor TCP (por defecto en el puerto `5000`). Cualquier cliente conectado puede:

- **Recibir** en tiempo real todos los datos que llegan del puerto serie
- **Enviar** comandos que serán reenviados al puerto serie

```bash
# Conectar desde otra terminal (Linux/macOS)
nc 127.0.0.1 5000

# Desde un script Python
import socket
s = socket.socket()
s.connect(('127.0.0.1', 5000))
s.sendall(b'mi_comando\n')
respuesta = s.recv(1024)
```

---

## Configuración de dispositivos

Cada dispositivo se define en un archivo YAML dentro de `devices/`. El nombre del archivo (sin extensión) es el argumento que se pasa al arrancar.

### Orden de búsqueda

eBridge busca el archivo de configuración en este orden:

1. `devices/<nombre>.yaml` en el **directorio de trabajo actual** (proyecto del usuario)
2. Configuraciones **incluidas en el paquete** (`ebridge/devices/`)

Esto permite añadir o sobrescribir dispositivos creando una carpeta `devices/` local sin tocar el paquete instalado.

### Estructura completa del YAML

```yaml
# devices/mi_dispositivo.yaml

# ── Puerto serie ──────────────────────────────────────────────
serial:
  baudrate: 9600
  bytesize: 8           # 5 | 6 | 7 | 8
  parity:   N           # N=None | E=Even | O=Odd | M=Mark | S=Space
  stopbits: 1           # 1 | 1.5 | 2
  timeout:  0.1         # segundos de timeout de lectura
  eol:      "\r\n"      # fin de línea para TX: "\n" | "\r" | "\r\n"
  encoding: utf-8       # codificación de caracteres

  # Chunking de escritura — para dispositivos con buffer UART pequeño.
  # Si los comandos largos se truncan, ajusta estos dos parámetros.
  # Con write_chunk_size: 0 se envía todo de una vez (comportamiento por defecto).
  write_chunk_size:  0      # bytes por envío (0 = sin chunking)
  write_chunk_delay: 0.01   # segundos de espera entre chunks

# ── Resaltado de texto ────────────────────────────────────────
highlights:
  - pattern: "\\bOK\\b"
    color:   green
  - pattern: "\\bERROR\\b"
    color:   bold_red

# ── Automatizaciones ──────────────────────────────────────────
automations:
  mi_auto:
    script:      automations/mi_auto.py
    description: "Descripción de la automatización"
```

### Parámetro `write_chunk_size`

Algunos microcontroladores tienen un buffer UART de hardware reducido (típicamente 16 bytes en STM32, AVR o ESP32). Si el PC envía un comando largo a ráfaga, el dispositivo puede descartar los bytes que no caben en el FIFO antes de que el firmware los lea.

El síntoma característico es que los comandos cortos funcionan pero los largos se truncan siempre en el mismo punto (generalmente 16 bytes).

| `write_chunk_size` | `write_chunk_delay` | Cuándo usarlo |
|---|---|---|
| `0` | — | Dispositivos con flow control o buffer grande (por defecto) |
| `8` | `0.01` | Punto de partida para dispositivos con FIFO pequeño |
| `4` | `0.005` | Firmware lento vaciando el FIFO |
| `1` | `0.001` | Caso extremo, byte a byte |

### Colores disponibles para el resaltado

| | | | |
|---|---|---|---|
| `red` | `green` | `yellow` | `blue` |
| `magenta` | `cyan` | `white` | `orange` |
| `bold_red` | `bold_green` | `bold` | `dim` |

### Dispositivos de ejemplo incluidos

| Archivo | Descripción |
|---|---|
| `devices/example_device.yaml` | Dispositivo genérico a 9600 baudios con resaltado de OK/ERROR, fechas, IPs y valores hexadecimales |
| `devices/gps_module.yaml` | Módulo GPS a 4800 baudios con resaltado de tramas NMEA |

---

## Automatizaciones

Las automatizaciones son scripts de Python que se ejecutan de forma asíncrona, sin bloquear el terminal ni el socket. Se invocan desde el terminal con `/nombre [args...]`.

### Crear una automatización

Crea un archivo `.py` en `automations/` que defina `async def run(ctx, *args)`:

```python
# automations/mi_automatizacion.py

async def run(ctx, *args):
    ctx.debug("Iniciando automatización")

    await ctx.send("mi_comando")

    try:
        respuesta = await ctx.wait_for(r"OK|ERROR", timeout=5.0)
    except TimeoutError:
        ctx.debug("El dispositivo no respondió")
        return

    if "OK" in respuesta:
        ctx.debug("Éxito, enviando siguiente comando")
        await ctx.send("siguiente_comando")
        respuesta = await ctx.wait_for(r"OK|ERROR", timeout=5.0)

    ctx.debug(f"Resultado: {respuesta}")
```

Regístrala en el YAML del dispositivo:

```yaml
automations:
  mi_automatizacion:
    script:      automations/mi_automatizacion.py
    description: "Descripción breve"
```

### API del contexto (`ctx`)

| Método | Descripción |
|---|---|
| `await ctx.send(comando)` | Envía un comando al puerto serie y lo muestra en terminal con `[AUTO >>]` |
| `await ctx.wait_for(patron, timeout=5.0)` | Espera del serie un mensaje que coincida con la regex `patron`. Lanza `TimeoutError` si se agota el tiempo |
| `ctx.debug(mensaje)` | Imprime un mensaje de debug en el terminal con `[AUTO   ]` |
| `ctx.args` | Lista de argumentos posicionales recibidos |

### Automatizaciones de ejemplo incluidas

**`ponfecha`** — Establece el día y el mes en el dispositivo esperando `OK` entre pasos:

```
mi_device $ /ponfecha          ← usa la fecha actual del sistema
mi_device $ /ponfecha 27       ← día 27, mes actual
mi_device $ /ponfecha 27 4     ← día 27, mes 4
```

**`reset`** — Envía `reset` y espera confirmación de arranque (`READY`, `BOOT` o `OK`) con timeout de 10 segundos:

```
mi_device $ /reset
```

---

## Log de sesión

Con `--log fichero.log` todos los mensajes se guardan en texto plano sin códigos de color:

```
======================================================================
Sesión iniciada: 2025-04-28T10:32:01.123456
======================================================================
[10:32:01.234] <<< SERIAL        4.230: smatrix > info
[10:32:02.100] >>> TERMINAL      read_reg CONFIG_REG 1
[10:32:02.350] <<< SERIAL        CONFIG_REG = 0x1A
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
| `>>> TERMINAL` | Comandos escritos por el usuario en el terminal |
| `>>> SOCKET` | Comandos recibidos de un cliente TCP |
| `    AUTO` | Mensajes de automatizaciones |
| `    SYSTEM` | Mensajes internos del sistema |

---

## Arquitectura

El sistema se basa en el patrón **productor/consumidor** sobre `asyncio`. Todos los componentes se comunican exclusivamente a través del `MessageBus` central.

```
                        ┌──────────────────────────────────┐
                        │           MessageBus              │
                        │                                   │
  SerialReader ────────►│ dispatch_rx() ──► rx_subscribers  │──► TerminalDisplay
  (hilo Python)         │                                   │──► SocketBroadcast
                        │                                   │──► AutomationWait
                        │                                   │──► SessionLogger
                        │                                   │
  Terminal   ──────────►│ send_to_serial() ──► tx_queue     │──► SerialWriter
  Socket     ──────────►│                                   │    (hilo Python)
  Automation ──────────►│                   ──► log_queue   │──► SessionLogger
                        └──────────────────────────────────┘
```

### Módulos

| Módulo | Responsabilidad |
|---|---|
| `_ansi.py` | Función `cprint()`: impresión con colores ANSI compatible con Windows Terminal |
| `_loader.py` | Resolución y carga de archivos de configuración de dispositivos |
| `_runner.py` | Lógica asyncio compartida entre CLI y API programática |
| `cli.py` | Punto de entrada del comando instalado y `python -m ebridge` |
| `core/message_bus.py` | Bus central de mensajes: colas asyncio y pub/sub |
| `core/interfaces/serial_interface.py` | Puente entre pyserial (bloqueante, hilos) y asyncio |
| `core/interfaces/socket_interface.py` | Servidor TCP: acepta clientes y hace broadcast del RX |
| `core/interfaces/terminal_interface.py` | Terminal interactivo (prompt_toolkit) |
| `core/automation_engine.py` | Carga y ejecuta scripts de automatización |
| `core/highlighter.py` | Resaltado de texto con regex y colores ANSI |
| `core/logger.py` | Escritura del log de sesión en fichero |
| `core/interfaces/base.py` | Clase base abstracta para nuevas interfaces |

### Añadir una nueva interfaz

1. Crea un archivo en `ebridge/core/interfaces/` que subclasee `BaseInterface`
2. Implementa `async def run(self)`:
   - Para **recibir** datos del serie: `q = bus.create_rx_subscriber()` → `await q.get()`
   - Para **enviar** datos al serie: `await bus.send_to_serial(Message(...))`
3. Instánciala en `_runner.py` y añádela a la lista de tareas con `asyncio.create_task()`

No es necesario modificar ningún otro componente.

---

## Estructura del proyecto

```
ebridge/                             ← raíz del repositorio
├── pyproject.toml                   ← definición del paquete instalable
├── README.md
│
├── ebridge/                         ← paquete Python
│   ├── __init__.py                  ← versión y API pública (run_terminal)
│   ├── __main__.py                  ← habilita python -m ebridge
│   ├── cli.py                       ← punto de entrada del comando instalado
│   ├── _runner.py                   ← lógica async compartida
│   ├── _loader.py                   ← resolución de configs de dispositivo
│   ├── _ansi.py                     ← cprint() compatible con Windows
│   │
│   ├── core/
│   │   ├── message_bus.py
│   │   ├── highlighter.py
│   │   ├── logger.py
│   │   ├── automation_engine.py
│   │   └── interfaces/
│   │       ├── base.py
│   │       ├── serial_interface.py
│   │       ├── socket_interface.py
│   │       └── terminal_interface.py
│   │
│   └── devices/                     ← configuraciones incluidas en el paquete
│       ├── example_device.yaml
│       └── gps_module.yaml
│
└── automations/                     ← scripts de automatización del usuario
    ├── ponfecha.py
    └── reset.py
```

---

## Notas de compatibilidad

### Colores en Windows Terminal

Todos los mensajes con color pasan por `cprint()` (`ebridge/_ansi.py`), que usa `print_formatted_text(ANSI(...))` de prompt_toolkit. Esto garantiza que los colores se rendericen correctamente en Windows Terminal incluso con políticas de Azure AD activas.

**No usar `cmd.exe`**: no tiene soporte completo de VT100. Usar siempre **Windows Terminal** con PowerShell.

### Entorno virtual en Windows

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

# Si PowerShell bloquea la ejecución de scripts:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

python -m pip install -e .
python -m ebridge example_device --port COM3
```

### Entorno virtual en Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m ebridge example_device --port /dev/ttyUSB0
```
