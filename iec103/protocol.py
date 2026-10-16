"""IEC 60870-5-103 FT1.2 framing and defensive ASDU decoding.

The decoder intentionally retains raw bytes for every ASDU. IEC 103 generic
data and disturbance transfer structures can be vendor-specific; those are
shown without dropping data even when no safe scalar interpretation exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import struct
from typing import Any

START_FIXED = 0x10
START_VARIABLE = 0x68
END = 0x16
ACK = 0xE5

TYPE_NAMES = {
    1: "Time-tagged message",
    2: "Time-tagged message with relative time",
    3: "Measurands I",
    4: "Time-tagged measurands with relative time",
    5: "Identification",
    6: "Time synchronization",
    7: "General interrogation",
    8: "General interrogation termination",
    9: "Measurands II",
    10: "Generic data",
    11: "Generic identification",
    20: "General command",
    21: "Generic command",
    22: "Generic data acknowledgement",
    23: "List recorded disturbances",
    24: "Order for disturbance data",
    25: "Acknowledgement for disturbance data",
    26: "Ready for disturbance data transmission",
    27: "Ready for disturbance channel transmission",
    28: "Ready for tags transmission",
    29: "Transmission of tags",
    30: "Transmission of disturbance values",
    31: "End of disturbance transmission",
}

COT_NAMES = {
    1: "spontaneous", 2: "cyclic", 3: "reset frame count unit",
    4: "reset communication unit", 5: "startup/restart", 6: "activation",
    7: "activation confirmation", 8: "deactivation",
    9: "deactivation confirmation", 10: "activation termination",
    11: "return information remote command",
    12: "return information local command", 20: "general interrogation",
    40: "generic write", 41: "generic read", 42: "generic write confirmation",
    43: "generic read confirmation", 44: "generic write negative confirmation",
    45: "generic read negative confirmation",
}


def hex_bytes(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


@dataclass(slots=True)
class Frame:
    kind: str
    raw: bytes
    valid: bool = True
    control: int | None = None
    link_address: int | None = None
    asdu: bytes = b""
    error: str = ""


@dataclass(slots=True)
class ValueUpdate:
    key: str
    type_id: int
    type_name: str
    common_address: int
    function_type: int
    information_number: int
    element: str
    value: Any
    quality: str = ""
    unit: str = ""


@dataclass(slots=True)
class Asdu:
    type_id: int
    type_name: str
    vsq: int
    cause: int
    cause_name: str
    common_address: int
    function_type: int
    information_number: int
    payload: bytes
    raw: bytes
    values: list[ValueUpdate] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class FrameParser:
    """Incremental parser for IEC 103 FT1.2 with one-byte link addresses."""

    def __init__(self, max_buffer: int = 65536) -> None:
        self.buffer = bytearray()
        self.max_buffer = max_buffer

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        if len(self.buffer) > self.max_buffer:
            del self.buffer[:-self.max_buffer]
        frames: list[Frame] = []
        while self.buffer:
            start = self.buffer[0]
            if start == ACK:
                frames.append(Frame("ack", bytes([ACK])))
                del self.buffer[0]
                continue
            if start == START_FIXED:
                if len(self.buffer) < 5:
                    break
                raw = bytes(self.buffer[:5])
                del self.buffer[:5]
                valid = raw[4] == END and ((raw[1] + raw[2]) & 0xFF) == raw[3]
                frames.append(Frame("fixed", raw, valid, raw[1], raw[2], error="" if valid else "Invalid checksum or end byte"))
                continue
            if start == START_VARIABLE:
                if len(self.buffer) < 4:
                    break
                length = self.buffer[1]
                if self.buffer[2] != length or self.buffer[3] != START_VARIABLE:
                    frames.append(Frame("invalid", bytes(self.buffer[:4]), False, error="Invalid repeated length/start"))
                    del self.buffer[0]
                    continue
                total = length + 6
                if len(self.buffer) < total:
                    break
                raw = bytes(self.buffer[:total])
                del self.buffer[:total]
                body = raw[4:4 + length]
                checksum = raw[4 + length]
                valid = raw[5 + length] == END and (sum(body) & 0xFF) == checksum and length >= 2
                frames.append(Frame("variable", raw, valid, body[0] if body else None, body[1] if len(body) > 1 else None, body[2:] if len(body) > 2 else b"", "" if valid else "Invalid length, checksum or end byte"))
                continue
            # Keep noise visible to the caller, one byte at a time.
            frames.append(Frame("noise", bytes([start]), False, error="Unexpected byte"))
            del self.buffer[0]
        return frames


def build_fixed(control: int, link_address: int) -> bytes:
    control &= 0xFF
    link_address &= 0xFF
    return bytes([START_FIXED, control, link_address, (control + link_address) & 0xFF, END])


def build_variable(control: int, link_address: int, asdu: bytes) -> bytes:
    body = bytes([control & 0xFF, link_address & 0xFF]) + asdu
    length = len(body)
    if length > 255:
        raise ValueError("IEC103 variable frame is too long")
    return bytes([START_VARIABLE, length, length, START_VARIABLE]) + body + bytes([sum(body) & 0xFF, END])


def build_general_interrogation(link_address: int, common_address: int, scan_number: int = 1) -> bytes:
    asdu = bytes([7, 0x81, 6, common_address & 0xFF, 0xFF, 0, scan_number & 0xFF])
    return build_variable(0x73, link_address, asdu)


def build_general_command(
    link_address: int,
    common_address: int,
    function_type: int,
    information_number: int,
    dco: int,
    return_identifier: int = 1,
    fcb: bool = False,
) -> bytes:
    """Build IEC103 ASDU 20 (general command) with confirmed user data."""
    for name, value in (
        ("Linkadresse", link_address), ("Common Address", common_address),
        ("FUN", function_type), ("INF", information_number),
        ("RII", return_identifier),
    ):
        if not 0 <= value <= 255:
            raise ValueError(f"{name} muss zwischen 0 und 255 liegen")
    if dco not in (1, 2):
        raise ValueError("DCO muss 1 (AUS) oder 2 (EIN) sein")
    # IEC103 general command: TYP 20, VSQ 1, COT 20, CA, FUN, INF, DCO, RII.
    asdu = bytes((20, 0x81, 20, common_address, function_type, information_number, dco, return_identifier))
    control = 0x73 if fcb else 0x53
    return build_variable(control, link_address, asdu)


def _quality(flags: int) -> str:
    names = []
    if flags & 0x80: names.append("invalid")
    if flags & 0x40: names.append("not topical")
    if flags & 0x20: names.append("substituted")
    if flags & 0x10: names.append("blocked")
    if flags & 0x08: names.append("overflow")
    return ", ".join(names) or "good"


def _cp32(data: bytes) -> str:
    if len(data) < 4:
        return hex_bytes(data)
    milliseconds = int.from_bytes(data[0:2], "little")
    minute = data[2] & 0x3F
    hour = data[3] & 0x1F
    return f"{hour:02d}:{minute:02d}:{milliseconds / 1000:06.3f}"


def _cp56(data: bytes) -> str:
    if len(data) < 7:
        return hex_bytes(data)
    ms = int.from_bytes(data[0:2], "little")
    try:
        value = datetime(2000 + (data[6] & 0x7F), data[5] & 0x0F, data[4] & 0x1F,
                         data[3] & 0x1F, data[2] & 0x3F, ms // 1000,
                         (ms % 1000) * 1000, tzinfo=timezone.utc)
        return value.isoformat()
    except ValueError:
        return hex_bytes(data[:7])


def _normalized(raw: bytes) -> tuple[float, int, int]:
    word = int.from_bytes(raw[:2], "little")
    # IEC 60870-5-103 MVAL: signed 13-bit value in bits 3..15 and three
    # status bits in bits 0..2. Arithmetic right shift preserves the sign.
    raw_value = struct.unpack("<h", raw[:2])[0] >> 3
    return round(raw_value / 4096.0, 7), raw_value, word & 0x07


def decode_asdu(raw: bytes) -> Asdu:
    if len(raw) < 6:
        raise ValueError(f"ASDU header requires 6 bytes, received {len(raw)}")
    type_id, vsq, cause, ca, fun, inf = raw[:6]
    payload = raw[6:]
    type_name = TYPE_NAMES.get(type_id, f"Unknown ASDU {type_id}")
    asdu = Asdu(type_id, type_name, vsq, cause, COT_NAMES.get(cause & 0x3F, f"cause {cause}"), ca, fun, inf, payload, raw)

    def add(element: str, value: Any, quality: str = "", unit: str = "", offset: int = 0) -> None:
        key = f"CA{ca}/FUN{fun}/INF{inf}/T{type_id}/{element}"
        asdu.values.append(ValueUpdate(key, type_id, type_name, ca, fun, inf + offset, element, value, quality, unit))

    asdu.details["raw_payload"] = hex_bytes(payload)
    asdu.details["sequence"] = bool(vsq & 0x80)
    asdu.details["object_count"] = vsq & 0x7F

    if type_id in (1, 2):
        if payload:
            dpi = payload[0] & 0x03
            add("double_point", ("intermediate", "off", "on", "indeterminate")[dpi], _quality(payload[0] & 0xF0))
        if type_id == 2 and len(payload) >= 5:
            add("relative_time_ms", int.from_bytes(payload[1:3], "little"))
            add("fault_number", int.from_bytes(payload[3:5], "little"))
        time_offset = 5 if type_id == 2 else 1
        if len(payload) >= time_offset + 4:
            add("time", _cp32(payload[time_offset:time_offset + 4]))
    elif type_id in (3, 9):
        for index in range(0, len(payload) - 1, 2):
            normalized, _raw_value, flags = _normalized(payload[index:index + 2])
            add(f"measurand_{index // 2 + 1}", normalized, _quality(flags << 4), "normalized")
    elif type_id == 4:
        if len(payload) >= 4:
            add("relative_time_ms", int.from_bytes(payload[0:2], "little"))
            add("fault_number", int.from_bytes(payload[2:4], "little"))
        for index in range(4, max(4, len(payload) - 3), 2):
            if index + 2 <= len(payload) - 4:
                normalized, _raw_value, flags = _normalized(payload[index:index + 2])
                add(f"measurand_{(index - 4) // 2 + 1}", normalized, _quality(flags << 4), "normalized")
        if len(payload) >= 8:
            add("time", _cp32(payload[-4:]))
    elif type_id == 5:
        text = payload.decode("ascii", errors="replace").rstrip("\x00 ")
        add("identification", text)
    elif type_id == 6:
        add("time", _cp56(payload[:7]))
    elif type_id in (7, 8):
        add("scan_number", payload[0] if payload else None)
    elif type_id in (20, 21):
        add("command", payload[0] if payload else None, _quality((payload[0] if payload else 0) & 0xF0))
        if len(payload) > 1:
            add("return_identifier", payload[1])
    elif type_id in (10, 11, 22):
        # Generic identification number (group, entry) plus kind/description.
        if len(payload) >= 2:
            add("generic_identification", f"{payload[0]}.{payload[1]}")
        if len(payload) >= 3:
            add("kind_of_description", payload[2])
        add("generic_raw", hex_bytes(payload))
    elif 23 <= type_id <= 31:
        if len(payload) >= 2:
            add("fault_number", int.from_bytes(payload[0:2], "little"))
        if len(payload) >= 3:
            add("channel_or_order", payload[2])
        if type_id == 30 and len(payload) > 3:
            for index in range(3, len(payload) - 1, 2):
                add(f"disturbance_value_{(index - 3) // 2 + 1}", struct.unpack("<h", payload[index:index + 2])[0])
        add("disturbance_raw", hex_bytes(payload))
    else:
        add("raw", hex_bytes(payload))

    if not asdu.values:
        add("raw", hex_bytes(payload))
    return asdu
