import unittest

from iec103.protocol import FrameParser, build_fixed, build_general_interrogation, build_variable, decode_asdu


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

    def test_unknown_type_retains_raw_payload(self):
        asdu = decode_asdu(bytes([200, 0x81, 1, 1, 2, 3, 0xDE, 0xAD]))
        self.assertEqual(asdu.type_id, 200)
        self.assertEqual(asdu.values[0].value, "DE AD")

    def test_variable_frame_checksum(self):
        raw = build_variable(0x73, 4, bytes([5, 0x81, 1, 1, 0, 0]) + b"DEVICE")
        frame = FrameParser().feed(raw)[0]
        self.assertTrue(frame.valid)
        self.assertEqual(decode_asdu(frame.asdu).values[0].value, "DEVICE")


if __name__ == "__main__":
    unittest.main()
