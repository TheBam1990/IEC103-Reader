"""Compact send centre for the IEC103 reader."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .protocol import (
    FrameParser,
    build_asdu_frame,
    build_fixed,
    build_general_command,
    build_general_interrogation,
    build_time_synchronization,
    hex_bytes,
    parse_hex_bytes,
)


class SendDialog(tk.Toplevel):
    """Modal-independent toolbox; only one compact button is needed in the main UI."""

    SPECIAL_PRESETS = {
        "Generischer Befehl (TK 21)": (21, 0x81, 40, 0, 0, ""),
        "Generisch lesen (TK 21 / COT 41)": (21, 0x81, 41, 0, 0, ""),
        "Generisch schreiben (TK 21 / COT 40)": (21, 0x81, 40, 0, 0, ""),
        "Störschriebliste (TK 23)": (23, 0x81, 31, 0xFF, 0, ""),
        "Störschriebauftrag (TK 24)": (24, 0x81, 31, 0xFF, 0, "00 00 01"),
        "Freie Spezial-ASDU": (21, 0x81, 40, 0, 0, ""),
    }

    def __init__(
        self,
        parent: tk.Misc,
        link_address: Callable[[], int],
        common_address: Callable[[], int],
        next_fcb: Callable[[], bool],
        transmit: Callable[[bytes, str, bool], bool],
    ) -> None:
        super().__init__(parent)
        self.title("IEC103 senden")
        self.geometry("760x500")
        self.minsize(690, 440)
        self.transient(parent)
        self.link_address = link_address
        self.common_address = common_address
        self.next_fcb = next_fcb
        self.transmit = transmit
        self.preview = tk.StringVar(value="Vorschau wird vor dem Senden aktualisiert.")
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Zieladressen werden aus dem Hauptfenster übernommen. Schreibende Befehle werden immer nochmals bestätigt.",
        ).pack(fill=tk.X, padx=10, pady=(10, 4))
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._standard_tab(notebook)
        self._command_tab(notebook)
        self._special_tab(notebook)
        self._expert_tab(notebook)
        preview_frame = ttk.LabelFrame(self, text="Telegrammvorschau", padding=6)
        preview_frame.pack(fill=tk.X, padx=10, pady=4)
        ttk.Entry(preview_frame, textvariable=self.preview, state="readonly", font=("Consolas", 9)).pack(fill=tk.X)
        ttk.Button(self, text="Schließen", command=self.destroy).pack(anchor=tk.E, padx=10, pady=(2, 10))

    @staticmethod
    def _entry(
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        column: int,
        width: int = 10,
        row: int = 0,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky=tk.W, padx=4, pady=(8, 2))
        ttk.Entry(parent, textvariable=variable, width=width).grid(row=row + 1, column=column, sticky=tk.EW, padx=4)

    def _show_and_send(self, frame: bytes, description: str, dangerous: bool = False) -> None:
        self.preview.set(hex_bytes(frame))
        self.transmit(frame, description, dangerous)

    def _standard_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="Standard")
        ttk.Label(tab, text="Standardisierte Abfragen und Zeitsynchronisation").pack(anchor=tk.W, pady=(0, 10))
        actions = (
            ("Link zurücksetzen", lambda: build_fixed(0x40, self.link_address()), "Link zurücksetzen", False),
            ("Klasse 1 abfragen", lambda: build_fixed(0x5A, self.link_address()), "Klasse 1 abfragen", False),
            ("Klasse 2 abfragen", lambda: build_fixed(0x7B, self.link_address()), "Klasse 2 abfragen", False),
            ("Generalabfrage", lambda: build_general_interrogation(self.link_address(), self.common_address()), "Generalabfrage", False),
            ("PC-Zeit synchronisieren", lambda: build_time_synchronization(self.link_address(), self.common_address(), datetime.now(), self.next_fcb()), "Zeitsynchronisation", True),
        )
        for text, builder, description, dangerous in actions:
            ttk.Button(tab, text=text, width=28, command=lambda b=builder, d=description, x=dangerous: self._safe_build(b, d, x)).pack(anchor=tk.W, pady=3)
        ttk.Label(tab, text="Die Zeitsynchronisation verwendet die lokale Uhrzeit des PCs.", foreground="#555555").pack(anchor=tk.W, pady=10)

    def _command_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="Schalten")
        self.fun = tk.StringVar()
        self.inf = tk.StringVar()
        self.dco = tk.StringVar(value="1 - AUS")
        self.rii = tk.StringVar(value="1")
        self._entry(tab, "FUN", self.fun, 0)
        self._entry(tab, "INF", self.inf, 1)
        ttk.Label(tab, text="Befehl").grid(row=0, column=2, sticky=tk.W, padx=4, pady=(8, 2))
        ttk.Combobox(tab, textvariable=self.dco, values=("1 - AUS", "2 - EIN"), state="readonly", width=14).grid(row=1, column=2, padx=4)
        self._entry(tab, "RII", self.rii, 3)
        ttk.Button(tab, text="Schaltbefehl senden", command=self._send_command).grid(row=1, column=4, padx=12)
        ttk.Label(tab, text="Achtung: Dieser Befehl kann einen realen Ausgang oder Schalter betätigen.", foreground="#9b2c2c").grid(row=2, column=0, columnspan=5, sticky=tk.W, padx=4, pady=14)

    def _special_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="Generik / Störschrieb")
        self.special_preset = tk.StringVar(value=next(iter(self.SPECIAL_PRESETS)))
        self.special_type = tk.StringVar()
        self.special_vsq = tk.StringVar()
        self.special_cot = tk.StringVar()
        self.special_fun = tk.StringVar()
        self.special_inf = tk.StringVar()
        self.special_payload = tk.StringVar()
        ttk.Label(tab, text="Vorlage").grid(row=0, column=0, sticky=tk.W, padx=4, pady=(0, 2))
        box = ttk.Combobox(tab, textvariable=self.special_preset, values=tuple(self.SPECIAL_PRESETS), state="readonly", width=34)
        box.grid(row=1, column=0, columnspan=5, sticky=tk.EW, padx=4)
        box.bind("<<ComboboxSelected>>", lambda _event: self._apply_special_preset())
        for column, (label, variable) in enumerate((("Typ", self.special_type), ("VSQ", self.special_vsq), ("COT", self.special_cot), ("FUN", self.special_fun), ("INF", self.special_inf))):
            self._entry(tab, label, variable, column, 9, row=2)
            tab.columnconfigure(column, weight=1)
        ttk.Label(tab, text="Nutzdaten (Hex, ohne ASDU-Kopf)").grid(row=4, column=0, columnspan=5, sticky=tk.W, padx=4, pady=(16, 2))
        ttk.Entry(tab, textvariable=self.special_payload, font=("Consolas", 10)).grid(row=5, column=0, columnspan=5, sticky=tk.EW, padx=4)
        ttk.Button(tab, text="Spezial-ASDU senden", command=self._send_special).grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=4, pady=14)
        ttk.Separator(tab).grid(row=7, column=0, columnspan=5, sticky=tk.EW, padx=4, pady=(0, 10))
        ttk.Label(tab, text="Hinweis: Generische Deskriptoren und Störschriebparameter sind gerätespezifisch. Nutzdaten deshalb nur nach Herstellerdokumentation eintragen.", foreground="#9b2c2c", wraplength=680, justify=tk.LEFT).grid(row=8, column=0, columnspan=5, sticky=tk.W, padx=4)
        self._apply_special_preset()

    def _expert_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="Hex-Experte")
        self.raw_mode = tk.StringVar(value="ASDU")
        self.raw_hex = tk.StringVar()
        ttk.Radiobutton(tab, text="Nur ASDU (FT1.2-Rahmen automatisch bilden)", variable=self.raw_mode, value="ASDU").pack(anchor=tk.W)
        ttk.Radiobutton(tab, text="Vollständiges FT1.2-Telegramm", variable=self.raw_mode, value="FRAME").pack(anchor=tk.W)
        ttk.Label(tab, text="Hexbytes").pack(anchor=tk.W, pady=(14, 2))
        ttk.Entry(tab, textvariable=self.raw_hex, font=("Consolas", 10)).pack(fill=tk.X)
        ttk.Button(tab, text="Hex-Telegramm senden", command=self._send_raw).pack(anchor=tk.W, pady=12)
        ttk.Label(tab, text="Expertenmodus: Plausibilitätsprüfung ersetzt keine Gerätedokumentation. Vollständige Rahmen müssen eine gültige Prüfsumme besitzen.", foreground="#9b2c2c", wraplength=680).pack(anchor=tk.W)

    def _safe_build(self, builder: Callable[[], bytes], description: str, dangerous: bool) -> None:
        try:
            self._show_and_send(builder(), description, dangerous)
        except ValueError as error:
            messagebox.showerror("IEC103 senden", str(error), parent=self)

    @staticmethod
    def _number(variable: tk.StringVar, name: str) -> int:
        try:
            value = int(variable.get(), 0)
        except ValueError as error:
            raise ValueError(f"{name} muss eine Ganzzahl sein") from error
        if not 0 <= value <= 255:
            raise ValueError(f"{name} muss zwischen 0 und 255 liegen")
        return value

    def _send_command(self) -> None:
        try:
            dco = 1 if self.dco.get().startswith("1") else 2
            frame = build_general_command(self.link_address(), self.common_address(), self._number(self.fun, "FUN"), self._number(self.inf, "INF"), dco, self._number(self.rii, "RII"), self.next_fcb())
            self._show_and_send(frame, f"Schaltbefehl {'AUS' if dco == 1 else 'EIN'}", True)
        except ValueError as error:
            messagebox.showerror("IEC103 senden", str(error), parent=self)

    def _apply_special_preset(self) -> None:
        values = self.SPECIAL_PRESETS[self.special_preset.get()]
        for variable, value in zip((self.special_type, self.special_vsq, self.special_cot, self.special_fun, self.special_inf, self.special_payload), values):
            variable.set(str(value))

    def _send_special(self) -> None:
        try:
            frame = build_asdu_frame(self.link_address(), self.common_address(), self._number(self.special_type, "Typ"), self._number(self.special_vsq, "VSQ"), self._number(self.special_cot, "COT"), self._number(self.special_fun, "FUN"), self._number(self.special_inf, "INF"), parse_hex_bytes(self.special_payload.get()), self.next_fcb())
            self._show_and_send(frame, self.special_preset.get(), True)
        except ValueError as error:
            messagebox.showerror("IEC103 senden", str(error), parent=self)

    def _send_raw(self) -> None:
        try:
            data = parse_hex_bytes(self.raw_hex.get())
            if not data:
                raise ValueError("Bitte Hexdaten eingeben")
            if self.raw_mode.get() == "ASDU":
                if len(data) < 6:
                    raise ValueError("Eine IEC103-ASDU benötigt mindestens sechs Kopfbytes")
                frame = build_asdu_frame(self.link_address(), data[3], data[0], data[1], data[2], data[4], data[5], data[6:], self.next_fcb())
            else:
                frames = FrameParser().feed(data)
                if len(frames) != 1 or not frames[0].valid or frames[0].raw != data:
                    raise ValueError("Kein einzelnes gültiges FT1.2-Telegramm mit korrekter Prüfsumme")
                frame = data
            self._show_and_send(frame, "Hex-Expertenmodus", True)
        except ValueError as error:
            messagebox.showerror("IEC103 senden", str(error), parent=self)
