import unittest
from PySide6.QtTest import QTest
from tests import test_usability


class LiveScaleTests(unittest.TestCase):
    setUpClass = classmethod(test_usability.UsabilityTests.setUpClass.__func__)
    setUp = test_usability.UsabilityTests.setUp
    tearDown = test_usability.UsabilityTests.tearDown

    def test_scale_changes_main_window_and_is_saved(self):
        self.window.show()
        QTest.qWait(100)
        original = self.window.tabs.list.font().pixelSize()
        self.window.ui_scale_pick.setValue(140)
        QTest.qWait(700)
        self.assertGreater(self.window.tabs.list.font().pixelSize(), original)
        self.assertEqual(self.window.settings['ui_scale'], 140)
        self.assertEqual(self.window.store.settings()['ui_scale'], 140)


if __name__ == '__main__':
    unittest.main()
