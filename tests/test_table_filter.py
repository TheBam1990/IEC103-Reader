import unittest

from iec103.table_filter import matches_filter


class TableFilterTests(unittest.TestCase):
    def setUp(self):
        self.values = (
            "CA 1 / FUN 134 / INF 157",
            "9: Messwerte II",
            "Messwert 2",
            "0.5",
            "200",
            "100",
            "good",
            "A",
            "2026-10-16 12:00:00.000",
            "3",
        )

    def test_empty_filter_matches(self):
        self.assertTrue(matches_filter(self.values, ""))

    def test_all_columns_are_searched_case_insensitively(self):
        self.assertTrue(matches_filter(self.values, "fun 134"))
        self.assertTrue(matches_filter(self.values, "MESSWERTE II"))

    def test_selected_column_limits_search(self):
        self.assertTrue(matches_filter(self.values, "100", 5))
        self.assertFalse(matches_filter(self.values, "100", 0))

    def test_unknown_text_does_not_match(self):
        self.assertFalse(matches_filter(self.values, "nicht vorhanden"))


if __name__ == "__main__":
    unittest.main()
