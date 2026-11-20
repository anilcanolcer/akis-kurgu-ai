import unittest

from main import EditState, format_time, safe_filename


class CoreTests(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(format_time(65.25), "01:05.25")
        self.assertEqual(safe_filename("Merhaba / Dünya!"), "Merhaba__Dünya")
        state = EditState(duration=10, start=2, end=8)
        self.assertEqual(state.end - state.start, 6)


if __name__ == "__main__":
    unittest.main()
