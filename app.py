"""Portable graphical IEC 60870-5-103 serial reader for Windows."""

from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from iec103.protocol import FrameParser, build_fixed, build_general_interrogation, decode_asdu, hex_bytes
from iec103.serial_worker import SerialSettings, SerialWorker

APP_NAME = "IEC103 Reader"
CONFIG_FILE = Path.home() / "IEC103-Reader.json"


class ReaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} 1.1.0")
        self.geometry("1450x820")
        self.minsize(1050, 620)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.events: queue.Queue = queue.Queue()
        self.worker = SerialWorker(self.events)
        self.parser = FrameParser()
        self.rows: dict[str, str] = {}
        self.row_keys: dict[str, str] = {}
        self.latest_values: dict[str, tuple[object, str]] = {}
        self.scaling_factors: dict[str, float] = {}
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.poll_job: str | None = None
        self._variables()
        self._style()
        self._layout()
        self.load_settings(silent=True)
        self.refresh_ports()
        self.after(40, self.process_events)

    def _variables(self) -> None:
        self.port = tk.StringVar()
        self.baudrate = tk.StringVar(value="9600")
        self.databits = tk.StringVar(value="8")
        self.parity = tk.StringVar(value="E")
        self.stopbits = tk.StringVar(value="1")
        self.link_address = tk.StringVar(value="1")
        self.common_address = tk.StringVar(value="1")
        self.active_master = tk.BooleanVar(value=True)
        self.poll_interval = tk.StringVar(value="1000")
        self.auto_gi = tk.BooleanVar(value=True)
        self.autoscroll = tk.BooleanVar(value=True)
        self.show_noise = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Bereit")
        self.counter = tk.StringVar(value="RX 0 B | TX 0 B | 0 Werte")

    def _style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=23)
        style.configure("Status.TLabel", padding=(8, 4))

    def _layout(self) -> None:
        top = ttk.LabelFrame(self, text="Serielle IEC103-Verbindung", padding=8)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))
        fields = [
            ("COM-Port", self.port, ()),
            ("Baud", self.baudrate, ("1200", "2400", "4800", "9600", "19200", "38400")),
            ("Datenbits", self.databits, ("7", "8")),
            ("Parität", self.parity, ("E", "O", "N")),
            ("Stoppbits", self.stopbits, ("1", "1.5", "2")),
            ("Linkadresse", self.link_address, ()),
            ("Common Address", self.common_address, ()),
            ("Polling (ms)", self.poll_interval, ()),
        ]
        for column, (label, variable, values) in enumerate(fields):
            ttk.Label(top, text=label).grid(row=0, column=column, sticky=tk.W, padx=3)
            widget = ttk.Combobox(top, textvariable=variable, values=values, width=12) if values or column == 0 else ttk.Entry(top, textvariable=variable, width=12)
            if column == 0:
                self.port_box = widget
            widget.grid(row=1, column=column, sticky=tk.EW, padx=3, pady=2)
        ttk.Button(top, text="Ports neu laden", command=self.refresh_ports).grid(row=1, column=8, padx=3)
        self.connect_button = ttk.Button(top, text="Verbinden", command=self.toggle_connection)
        self.connect_button.grid(row=1, column=9, padx=3)
        ttk.Checkbutton(top, text="Aktiver Master", variable=self.active_master).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=3)
        ttk.Checkbutton(top, text="GI nach Verbindung", variable=self.auto_gi).grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=3)
        ttk.Button(top, text="Link zurücksetzen", command=lambda: self.send(build_fixed(0x40, self.number(self.link_address, 0, 255)))).grid(row=2, column=4, padx=3, pady=4)
        ttk.Button(top, text="Klasse 1 abfragen", command=lambda: self.send(build_fixed(0x5A, self.number(self.link_address, 0, 255)))).grid(row=2, column=5, padx=3)
        ttk.Button(top, text="Klasse 2 abfragen", command=lambda: self.send(build_fixed(0x7B, self.number(self.link_address, 0, 255)))).grid(row=2, column=6, padx=3)
        ttk.Button(top, text="Generalabfrage", command=self.send_gi).grid(row=2, column=7, padx=3)
        ttk.Button(top, text="Einstellungen speichern", command=self.save_settings).grid(row=2, column=8, padx=3)

        toolbar = ttk.Frame(self, padding=(8, 3))
        toolbar.pack(fill=tk.X)
        ttk.Checkbutton(toolbar, text="Traffic automatisch scrollen", variable=self.autoscroll).pack(side=tk.LEFT)
        ttk.Checkbutton(toolbar, text="Störbytes anzeigen", variable=self.show_noise).pack(side=tk.LEFT, padx=12)
        ttk.Button(toolbar, text="Traffic leeren", command=self.clear_traffic).pack(side=tk.RIGHT, padx=3)
        ttk.Button(toolbar, text="Wertetabelle leeren", command=self.clear_values).pack(side=tk.RIGHT, padx=3)
        ttk.Button(toolbar, text="CSV exportieren", command=self.export_csv).pack(side=tk.RIGHT, padx=3)
        ttk.Button(toolbar, text="Faktor für Wert setzen", command=self.set_selected_factor).pack(side=tk.RIGHT, padx=3)

        split = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        traffic_frame = ttk.LabelFrame(split, text="Telegrammverkehr", padding=4)
        values_frame = ttk.LabelFrame(split, text="Aktuelle Werte (jede Adresse nur einmal)", padding=4)
        split.add(traffic_frame, weight=2)
        split.add(values_frame, weight=3)

        self.traffic = tk.Text(traffic_frame, wrap=tk.NONE, font=("Consolas", 9), bg="#101418", fg="#d7e1e8", insertbackground="white")
        traffic_y = ttk.Scrollbar(traffic_frame, orient=tk.VERTICAL, command=self.traffic.yview)
        traffic_x = ttk.Scrollbar(traffic_frame, orient=tk.HORIZONTAL, command=self.traffic.xview)
        self.traffic.configure(yscrollcommand=traffic_y.set, xscrollcommand=traffic_x.set)
        self.traffic.grid(row=0, column=0, sticky="nsew")
        traffic_y.grid(row=0, column=1, sticky="ns")
        traffic_x.grid(row=1, column=0, sticky="ew")
        traffic_frame.rowconfigure(0, weight=1)
        traffic_frame.columnconfigure(0, weight=1)
        self.traffic.tag_configure("rx", foreground="#7CFC9A")
        self.traffic.tag_configure("tx", foreground="#79B8FF")
        self.traffic.tag_configure("error", foreground="#FF7B72")
        self.traffic.tag_configure("meta", foreground="#C9D1D9")

        columns = ("address", "type", "element", "received", "factor", "calculated", "quality", "unit", "timestamp", "count")
        self.table = ttk.Treeview(values_frame, columns=columns, show="headings")
        headings = {
            "address": "Adresse", "type": "ASDU-Typ", "element": "Datenelement",
            "received": "Empfangen", "factor": "Faktor", "calculated": "Berechnet",
            "quality": "Qualität", "unit": "Einheit",
            "timestamp": "Zeitstempel", "count": "Anzahl",
        }
        widths = {"address": 190, "type": 170, "element": 130, "received": 115, "factor": 80,
                  "calculated": 125, "quality": 100, "unit": 85, "timestamp": 165, "count": 65}
        for name in columns:
            self.table.heading(name, text=headings[name], command=lambda n=name: self.sort_table(n, False))
            self.table.column(name, width=widths[name], minwidth=55, stretch=name in ("calculated", "type"))
        self.table.bind("<Double-1>", self.set_selected_factor)
        table_y = ttk.Scrollbar(values_frame, orient=tk.VERTICAL, command=self.table.yview)
        table_x = ttk.Scrollbar(values_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=table_y.set, xscrollcommand=table_x.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        table_y.grid(row=0, column=1, sticky="ns")
        table_x.grid(row=1, column=0, sticky="ew")
        values_frame.rowconfigure(0, weight=1)
        values_frame.columnconfigure(0, weight=1)

        statusbar = ttk.Frame(self)
        statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(statusbar, textvariable=self.status, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Label(statusbar, textvariable=self.counter, style="Status.TLabel").pack(side=tk.RIGHT)

    @staticmethod
    def number(variable: tk.StringVar, minimum: int, maximum: int) -> int:
        value = int(variable.get())
        if not minimum <= value <= maximum:
            raise ValueError(f"Wert muss zwischen {minimum} und {maximum} liegen")
        return value

    def serial_settings(self) -> SerialSettings:
        if not self.port.get().strip():
            raise ValueError("Bitte einen COM-Port auswählen")
        stopbits = float(self.stopbits.get())
        return SerialSettings(self.port.get().strip(), int(self.baudrate.get()), int(self.databits.get()), self.parity.get(), stopbits)

    def refresh_ports(self) -> None:
        ports = self.worker.ports()
        self.port_box.configure(values=ports)
        if not self.port.get() and ports:
            self.port.set(ports[0])
        self.status.set(f"{len(ports)} serielle Schnittstelle(n) gefunden")

    def toggle_connection(self) -> None:
        if self.worker.connected:
            self.stop_polling()
            self.worker.disconnect()
            self.connect_button.configure(text="Verbinden")
            return
        try:
            self.worker.connect(self.serial_settings())
            self.connect_button.configure(text="Trennen")
            self.save_settings(silent=True)
            if self.active_master.get():
                self.after(150, lambda: self.send(build_fixed(0x40, self.number(self.link_address, 0, 255))))
                if self.auto_gi.get():
                    self.after(450, self.send_gi)
                self.start_polling()
        except Exception as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)

    def send(self, data: bytes) -> None:
        try:
            self.worker.write(data)
        except Exception as error:
            self.log("ERR", str(error), "error")

    def send_gi(self) -> None:
        try:
            self.send(build_general_interrogation(self.number(self.link_address, 0, 255), self.number(self.common_address, 0, 255)))
        except ValueError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)

    def start_polling(self) -> None:
        self.stop_polling()

        def poll() -> None:
            if self.worker.connected and self.active_master.get():
                address = self.number(self.link_address, 0, 255)
                self.send(build_fixed(0x5A, address))
                self.after(max(100, int(self.poll_interval.get())) // 2, lambda: self.send(build_fixed(0x7B, address)) if self.worker.connected else None)
                self.poll_job = self.after(max(200, int(self.poll_interval.get())), poll)
        self.poll_job = self.after(max(200, int(self.poll_interval.get())), poll)

    def stop_polling(self) -> None:
        if self.poll_job:
            self.after_cancel(self.poll_job)
            self.poll_job = None

    def process_events(self) -> None:
        try:
            for _ in range(500):
                kind, payload = self.events.get_nowait()
                if kind == "rx":
                    self.rx_bytes += len(payload)
                    for frame in self.parser.feed(payload):
                        self.handle_frame(frame)
                elif kind == "tx":
                    self.tx_bytes += len(payload)
                    self.log("TX", hex_bytes(payload), "tx")
                elif kind == "error":
                    self.log("ERR", payload, "error")
                    self.status.set(payload)
                    self.connect_button.configure(text="Verbinden")
                    self.stop_polling()
                else:
                    self.status.set(str(payload))
        except queue.Empty:
            pass
        self.counter.set(f"RX {self.rx_bytes} B | TX {self.tx_bytes} B | {len(self.rows)} Werte")
        self.after(40, self.process_events)

    def handle_frame(self, frame) -> None:
        if frame.kind == "noise" and not self.show_noise.get():
            return
        tag = "rx" if frame.valid else "error"
        summary = f"{hex_bytes(frame.raw)}"
        if frame.error:
            summary += f"  [{frame.error}]"
        self.log("RX", summary, tag)
        if frame.kind != "variable" or not frame.valid or not frame.asdu:
            return
        try:
            asdu = decode_asdu(frame.asdu)
            self.log("   ", f"ASDU {asdu.type_id} {asdu.type_name}; COT {asdu.cause} {asdu.cause_name}; CA {asdu.common_address}; FUN {asdu.function_type}; INF {asdu.information_number}", "meta")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            for value in asdu.values:
                self.update_value(value, timestamp)
        except Exception as error:
            self.log("ERR", f"ASDU konnte nicht dekodiert werden: {error}", "error")

    def update_value(self, value, timestamp: str, increment: bool = True) -> None:
        rendered = json.dumps(value.value, ensure_ascii=False) if isinstance(value.value, (dict, list)) else str(value.value)
        numeric = isinstance(value.value, (int, float)) and not isinstance(value.value, bool)
        factor = self.scaling_factors.get(value.key, 1.0) if numeric else None
        calculated = self.format_number(float(value.value) * factor) if numeric else rendered
        factor_text = self.format_number(factor) if numeric else ""
        address = f"CA {value.common_address} / FUN {value.function_type} / INF {value.information_number}"
        current = self.rows.get(value.key)
        count = 1
        if current:
            old = self.table.item(current, "values")
            count = int(old[9]) + (1 if increment else 0)
            self.table.item(current, values=(address, f"{value.type_id}: {value.type_name}", value.element, rendered, factor_text, calculated, value.quality, value.unit, timestamp, count))
            self.table.move(current, "", 0)
        else:
            item = self.table.insert("", 0, values=(address, f"{value.type_id}: {value.type_name}", value.element, rendered, factor_text, calculated, value.quality, value.unit, timestamp, count))
            self.rows[value.key] = item
            self.row_keys[item] = value.key
        self.latest_values[value.key] = (value, timestamp)

    @staticmethod
    def format_number(value: float) -> str:
        return f"{value:.12g}"

    def set_selected_factor(self, _event=None) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo(APP_NAME, "Bitte zuerst einen Messwert in der Tabelle auswählen.", parent=self)
            return
        item = selected[0]
        key = self.row_keys.get(item)
        latest = self.latest_values.get(key or "")
        if not key or not latest or not isinstance(latest[0].value, (int, float)) or isinstance(latest[0].value, bool):
            messagebox.showinfo(APP_NAME, "Für diesen Wert kann kein Zahlenfaktor gesetzt werden.", parent=self)
            return
        current = self.scaling_factors.get(key, 1.0)
        factor = simpledialog.askfloat(
            APP_NAME,
            f"Faktor für {key}:\n\nBerechnet = Empfangen × Faktor",
            initialvalue=current,
            parent=self,
        )
        if factor is None:
            return
        self.scaling_factors[key] = factor
        value, timestamp = latest
        self.update_value(value, timestamp, increment=False)
        self.save_settings(silent=True)
        self.status.set(f"Faktor {self.format_number(factor)} gespeichert für {key}")

    def log(self, direction: str, message: str, tag: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.traffic.insert(tk.END, f"{timestamp} {direction:<3} {message}\n", tag)
        # Bound the visual log without affecting the value table.
        line_count = int(self.traffic.index("end-1c").split(".")[0])
        if line_count > 20000:
            self.traffic.delete("1.0", "2001.0")
        if self.autoscroll.get():
            self.traffic.see(tk.END)

    def clear_traffic(self) -> None:
        self.traffic.delete("1.0", tk.END)

    def clear_values(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)
        self.rows.clear()
        self.row_keys.clear()
        self.latest_values.clear()

    def sort_table(self, column: str, reverse: bool) -> None:
        values = [(self.table.set(item, column).lower(), item) for item in self.table.get_children("")]
        values.sort(reverse=reverse)
        for index, (_, item) in enumerate(values):
            self.table.move(item, "", index)
        self.table.heading(column, command=lambda: self.sort_table(column, not reverse))

    def export_csv(self) -> None:
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not filename:
            return
        with open(filename, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow([self.table.heading(column, "text") for column in self.table["columns"]])
            for item in self.table.get_children(""):
                writer.writerow(self.table.item(item, "values"))
        self.status.set(f"CSV gespeichert: {filename}")

    def settings_dict(self) -> dict:
        values = {name: variable.get() for name, variable in {
            "port": self.port, "baudrate": self.baudrate, "databits": self.databits,
            "parity": self.parity, "stopbits": self.stopbits, "link_address": self.link_address,
            "common_address": self.common_address, "active_master": self.active_master,
            "poll_interval": self.poll_interval, "auto_gi": self.auto_gi,
        }.items()}
        values["scaling_factors"] = self.scaling_factors
        return values

    def save_settings(self, silent: bool = False) -> None:
        try:
            CONFIG_FILE.write_text(json.dumps(self.settings_dict(), indent=2), encoding="utf-8")
            if not silent:
                self.status.set(f"Einstellungen gespeichert: {CONFIG_FILE}")
        except OSError as error:
            if not silent:
                messagebox.showerror(APP_NAME, str(error), parent=self)

    def load_settings(self, silent: bool = False) -> None:
        if not CONFIG_FILE.exists():
            return
        try:
            values = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            variables = {
                "port": self.port, "baudrate": self.baudrate, "databits": self.databits,
                "parity": self.parity, "stopbits": self.stopbits, "link_address": self.link_address,
                "common_address": self.common_address, "active_master": self.active_master,
                "poll_interval": self.poll_interval, "auto_gi": self.auto_gi,
            }
            for key, variable in variables.items():
                if key in values:
                    variable.set(values[key])
            factors = values.get("scaling_factors", {})
            if isinstance(factors, dict):
                self.scaling_factors = {
                    str(key): float(value) for key, value in factors.items()
                    if isinstance(value, (int, float))
                }
        except (OSError, ValueError) as error:
            if not silent:
                messagebox.showerror(APP_NAME, str(error), parent=self)

    def close(self) -> None:
        self.stop_polling()
        self.worker.disconnect()
        self.destroy()


if __name__ == "__main__":
    ReaderApp().mainloop()
