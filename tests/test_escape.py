import unittest
from windowwords.native import EscapeGate


class EscapeTests(unittest.TestCase):
    def test_whole_press_is_swallowed_after_close_until_release(self):
        calls = []
        gate = EscapeGate(calls.append)
        gate.enabled = True
        self.assertTrue(gate.process(27,0x100))
        gate.enabled = False
        self.assertTrue(gate.process(27,0x100))
        self.assertTrue(gate.process(27,0x101))
        self.assertEqual(calls,['escape'])
        self.assertFalse(gate.process(27,0x100))
        self.assertFalse(gate.process(27,0x101))

    def test_other_keys_and_escape_outside_session_are_untouched(self):
        gate = EscapeGate(lambda action:self.fail('unexpected close'))
        self.assertFalse(gate.process(27,0x100))
        gate.enabled = True
        self.assertFalse(gate.process(65,0x100))
