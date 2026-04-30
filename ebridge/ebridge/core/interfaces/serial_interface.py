"""
Interfaz de puerto serie.

Usa hilos de Python para las operaciones bloqueantes de pyserial y
los conecta al event loop de asyncio mediante colas thread-safe.

Arquitectura:
  hilo_reader  → lee bytes del serie → asyncio queue → bus.dispatch_rx()
  run() (async) → consume bus.tx_queue → hilo_writer → escribe al serie
"""

import asyncio
import logging
import queue
import threading
from typing import Optional

import serial

from .base import BaseInterface
from ..message_bus import MessageBus, Message, MessageSource
from ebridge._ansi import cprint

log = logging.getLogger(__name__)


class SerialInterface(BaseInterface):
    """
    Gestiona la comunicación con el puerto serie.

    Configuración YAML esperada (sección 'serial'):
        baudrate: 9600
        bytesize: 8          # 5, 6, 7, 8
        parity:   N          # N, E, O, M, S
        stopbits: 1          # 1, 1.5, 2
        timeout:  0.1        # segundos (lectura)
        eol:      "\\r\\n"   # fin de línea para TX (opcional, default \\n)
        encoding: utf-8      # codificación (opcional, default utf-8)
    """

    def __init__(self, bus: MessageBus, port: str, config: dict):
        self._bus = bus
        self._port = port
        self._cfg = config
        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._write_q: queue.Queue = queue.Queue()  # cola thread-safe para TX

    # ------------------------------------------------------------------
    # Propiedades de configuración
    # ------------------------------------------------------------------

    @property
    def _eol(self) -> str:
        return self._cfg.get("eol", "\n")

    @property
    def _encoding(self) -> str:
        return self._cfg.get("encoding", "utf-8")

    def _open_serial(self) -> serial.Serial:
        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
        }
        bytesize_map = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS,
        }
        stopbits_map = {
            1:   serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2:   serial.STOPBITS_TWO,
        }
        return serial.Serial(
            port=self._port,
            baudrate=self._cfg.get("baudrate", 9600),
            bytesize=bytesize_map.get(self._cfg.get("bytesize", 8), serial.EIGHTBITS),
            parity=parity_map.get(self._cfg.get("parity", "N"), serial.PARITY_NONE),
            stopbits=stopbits_map.get(self._cfg.get("stopbits", 1), serial.STOPBITS_ONE),
            timeout=self._cfg.get("timeout", 0.1),
            xonxoff=self._cfg.get("xonxoff", False),
            rtscts=self._cfg.get("rtscts", False),
            dsrdtr=self._cfg.get("dsrdtr", False),
        )

    # ------------------------------------------------------------------
    # Hilo lector: serie → asyncio
    # ------------------------------------------------------------------

    def _reader_thread(self, loop: asyncio.AbstractEventLoop) -> None:
        """Lee bytes del serie y los despacha al event loop de asyncio."""
        buffer = b""
        while self._running:
            try:
                waiting = self._ser.in_waiting
                chunk = self._ser.read(waiting if waiting > 0 else 1)
                if not chunk:
                    continue
                buffer += chunk

                # Procesa líneas completas
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode(self._encoding, errors="replace").strip()
                    if text:
                        msg = Message(source=MessageSource.SERIAL_RX, data=text)
                        asyncio.run_coroutine_threadsafe(
                            self._bus.dispatch_rx(msg), loop
                        )
            except serial.SerialException as e:
                if self._running:
                    log.error("Error de lectura serie: %s", e)
                    asyncio.run_coroutine_threadsafe(
                        self._bus.dispatch_rx(
                            Message(MessageSource.SYSTEM, f"[ERROR] Puerto serie: {e}")
                        ),
                        loop,
                    )
                break
            except Exception as e:
                if self._running:
                    log.exception("Error inesperado en hilo lector: %s", e)

    # ------------------------------------------------------------------
    # Hilo escritor: cola thread-safe → serie
    # ------------------------------------------------------------------

    def _writer_thread(self) -> None:
        """Toma datos de la cola thread-safe y los escribe al serie."""
        while self._running:
            try:
                data: Optional[bytes] = self._write_q.get(timeout=0.1)
                if data is None:
                    break
                self._ser.write(data)
                self._ser.flush()
            except queue.Empty:
                continue
            except serial.SerialException as e:
                if self._running:
                    log.error("Error de escritura serie: %s", e)
            except Exception as e:
                if self._running:
                    log.exception("Error inesperado en hilo escritor: %s", e)

    # ------------------------------------------------------------------
    # Tarea asyncio principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        loop = asyncio.get_event_loop()

        try:
            self._ser = self._open_serial()
        except serial.SerialException as e:
            cprint(f"\033[91m[SERIAL] No se pudo abrir '{self._port}': {e}\033[0m")
            return

        self._running = True
        cprint(f"\033[92m[SERIAL] Puerto abierto: {self._port} "
               f"@ {self._cfg.get('baudrate', 9600)} baudios\033[0m")

        reader_t = threading.Thread(
            target=self._reader_thread, args=(loop,), daemon=True, name="serial-reader"
        )
        writer_t = threading.Thread(
            target=self._writer_thread, daemon=True, name="serial-writer"
        )
        reader_t.start()
        writer_t.start()

        try:
            # Consume la cola asyncio de TX y la pasa al hilo escritor
            while self._running:
                msg: Message = await self._bus.tx_queue.get()
                payload = (msg.data + self._eol).encode(self._encoding)
                self._write_q.put(payload)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._write_q.put(None)  # señal de parada al hilo escritor
            writer_t.join(timeout=1)
            if self._ser and self._ser.is_open:
                self._ser.close()
            cprint("\033[93m[SERIAL] Puerto cerrado.\033[0m")
