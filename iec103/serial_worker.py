"""Threaded serial transport isolated from the Tk event loop."""

from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
from typing import Any

import serial
from serial.tools import list_ports


@dataclass(slots=True)
class SerialSettings:
    port: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "E"
    stopbits: float = 1
    timeout: float = 0.1


class SerialWorker:
    def __init__(self, events: queue.Queue[tuple[str, Any]]) -> None:
        self.events = events
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()

    @staticmethod
    def ports() -> list[str]:
        return [port.device for port in list_ports.comports()]

    @property
    def connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def connect(self, settings: SerialSettings) -> None:
        if self.connected:
            return
        self._serial = serial.Serial(
            port=settings.port, baudrate=settings.baudrate,
            bytesize=settings.bytesize, parity=settings.parity,
            stopbits=settings.stopbits, timeout=settings.timeout,
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, name="iec103-serial", daemon=True)
        self._thread.start()
        self.events.put(("status", f"Verbunden mit {settings.port}"))

    def disconnect(self) -> None:
        self._stop.set()
        serial_port = self._serial
        self._serial = None
        if serial_port:
            try:
                serial_port.close()
            except serial.SerialException:
                pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.events.put(("status", "Getrennt"))

    def write(self, data: bytes) -> None:
        with self._write_lock:
            if not self._serial or not self._serial.is_open:
                raise serial.PortNotOpenError("Serielle Schnittstelle ist nicht geöffnet")
            self._serial.write(data)
            self._serial.flush()
        self.events.put(("tx", data))

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                serial_port = self._serial
                if not serial_port:
                    return
                data = serial_port.read(max(serial_port.in_waiting, 1))
                if data:
                    self.events.put(("rx", data))
            except serial.SerialException as error:
                self.events.put(("error", str(error)))
                self._stop.set()
            except Exception as error:  # keep GUI alive for driver-specific errors
                self.events.put(("error", f"Unerwarteter serieller Fehler: {error}"))
                self._stop.set()
            time.sleep(0.005)
