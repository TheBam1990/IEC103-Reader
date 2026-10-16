from datetime import datetime
import unittest

from iec103.protocol import FrameParser, build_asdu_frame, build_fixed, build_general_command, build_general_interrogation, build_time_synchronization, build_variable, decode_asdu, parse_hex_bytes


class FrameTests(unittest.TestCase):
    def test_fixed_roundtrip(self):
        frame = FrameParser().feed(build_fixed(0x5A, 1))[0]
        self.assertTrue(frame.valid)
        self.assertEqual(frame.control, 0x5A)
        self.assertEqual(frame.link_address, 1)

    def test_fragmented_variable_frame(self):
        raw = build_general_interrogation(1, 2, 7)
        parser = FrameParser()
        self.assertEqual(parser.feed(raw[:4]), [])
        frames = parser.feed(raw[4:])
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0].valid)
        asdu = decode_asdu(frames[0].asdu)
        self.assertEqual((asdu.type_id, asdu.common_address), (7, 2))
        self.assertEqual(asdu.values[0].value, 7)

    def test_invalid_checksum_is_reported(self):
        raw = bytearray(build_fixed(0x40, 1))
        raw[3] ^= 1
        frame = FrameParser().feed(bytes(raw))[0]
        self.assertFalse(frame.valid)
        self.assertIn("checksum", frame.error.lower())

    def test_measurands_are_individual_stable_keys(self):
        asdu = decode_asdu(bytes([3, 0x81, 2, 1, 160, 1, 0x00, 0x40, 0x00, 0x20]))
        self.assertEqual(len(asdu.values), 2)
        self.assertNotEqual(asdu.values[0].key, asdu.values[1].key)
        self.assertEqual(asdu.values[0].common_address, 1)
        self.assertEqual(asdu.values[0].function_type, 160)

    def test_type_9_decodes_13_bit_mval_without_status_bits(self):
        # 2048 << 3 is normalized 0.5; the lowest three bits are status only.
        asdu = decode_asdu(bytes([9, 0x81, 2, 1, 160, 1, 0x05, 0x40]))
        self.assertEqual(asdu.values[0].value, 0.5)
        self.assertNotEqual(asdu.values[0].quality, "good")

    def test_type_9_decodes_negative_mval(self):
        encoded = ((-1024 << 3) & 0xFFFF).to_bytes(2, "little")
        asdu = decode_asdu(bytes([9, 0x81, 2, 1, 160, 1]) + encoded)
        self.assertEqual(asdu.values[0].value, -0.25)

    def test_unknown_type_retains_raw_payload(self):
        asdu = decode_asdu(bytes([200, 0x81, 1, 1, 2, 3, 0xDE, 0xAD]))
        self.assertEqual(asdu.type_id, 200)
        self.assertEqual(asdu.values[0].value, "DE AD")

    def test_variable_frame_checksum(self):
        raw = build_variable(0x73, 4, bytes([5, 0x81, 1, 1, 0, 0]) + b"DEVICE")
        frame = FrameParser().feed(raw)[0]
        self.assertTrue(frame.valid)
        self.assertEqual(decode_asdu(frame.asdu).values[0].value, "DEVICE")

    def test_general_command_off_and_on(self):
        off = FrameParser().feed(build_general_command(1, 2, 134, 157, 1, 23, fcb=False))[0]
        on = FrameParser().feed(build_general_command(1, 2, 134, 157, 2, 24, fcb=True))[0]
        self.assertTrue(off.valid and on.valid)
        self.assertEqual(off.control, 0x53)
        self.assertEqual(on.control, 0x73)
        self.assertEqual(off.asdu, bytes((20, 0x81, 20, 2, 134, 157, 1, 23)))
        self.assertEqual(on.asdu[-2:], bytes((2, 24)))

    def test_general_command_rejects_invalid_dco(self):
        with self.assertRaises(ValueError):
            build_general_command(1, 1, 1, 1, 0)

    def test_time_synchronization_contains_cp56_time(self):
        frame = FrameParser().feed(build_time_synchronization(1, 2, datetime(2026, 10, 16, 18, 19, 20, 123000)))[0]
        self.assertTrue(frame.valid)
        self.assertEqual(frame.asdu[:6], bytes((6, 0x81, 8, 2, 0xFF, 0)))
        self.assertEqual(frame.asdu[6:], bytes((0x9B, 0x4E, 19, 18, 0xB0, 10, 26)))

    def test_custom_asdu_and_hex_parser(self):
        payload = parse_hex_bytes("00:0A ff")
        frame = FrameParser().feed(build_asdu_frame(3, 4, 21, 0x81, 41, 5, 6, payload))[0]
        self.assertTrue(frame.valid)
        self.assertEqual(frame.asdu, bytes((21, 0x81, 41, 4, 5, 6, 0, 10, 255)))
        with self.assertRaises(ValueError):
            parse_hex_bytes("ABC")


if __name__ == "__main__":
    unittest.main()
