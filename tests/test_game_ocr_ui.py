import sentencepiece,ctranslate2
from PIL import Image
from unittest.mock import Mock,patch
import time,unittest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QRect
from PySide6.QtWidgets import QStyle,QStyleOptionComboBox
from tests import test_usability as usability


class GameOCRUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    def setUp(self):
        usability.UsabilityTests.setUp(self)
        self.app.processEvents()
    tearDown=usability.UsabilityTests.tearDown

    def test_engine_can_be_saved_and_restored_in_game_profile(self):
        window=self.window
        self.assertEqual(window.ocr_engine_pick.currentData(),'windows')
        window.ocr_engine_pick.setCurrentIndex(window.ocr_engine_pick.findData('game'))
        window.apply_ocr();self.assertEqual(window.store.settings()['ocr_engine'],'game')
        window.game.setText('Example');window.save_profile()
        window.ocr_engine_pick.setCurrentIndex(0);window.apply_ocr()
        window.apply_profile('Example')
        self.assertEqual(window.settings['ocr_engine'],'game')
        self.assertEqual(window.ocr_engine_pick.currentData(),'game')

    def test_preview_uses_unsaved_engine_choice(self):
        window=self.window;window.capture_preview_image=Mock(return_value=Image.new('RGB',(600,300)))
        window.ocr_engine_pick.setCurrentIndex(window.ocr_engine_pick.findData('game'))
        pending=[];window.task=lambda fn,done,failed=None:pending.append((fn,done,failed))
        window.preview_ocr();deadline=time.monotonic()+1
        while not pending and time.monotonic()<deadline:QTest.qWait(10)
        self.assertEqual(len(pending),1)
        with patch('windowwords.ocr_preview.ocr.read',return_value=()) as read:
            pending[0][0]()
        self.assertEqual(read.call_args.args[2],'game')
        self.assertEqual(window.settings['ocr_engine'],'windows')

    def test_device_control_is_only_enabled_for_game_ocr(self):
        window=self.window
        self.assertFalse(window.ocr_device_pick.isEnabled())
        window.ocr_engine_pick.setCurrentIndex(window.ocr_engine_pick.findData('game'))
        self.assertTrue(window.ocr_device_pick.isEnabled())
        window.ocr_device_pick.setCurrentIndex(window.ocr_device_pick.findData('cpu'))
        window.apply_ocr();self.assertEqual(window.store.settings()['ocr_device'],'cpu')

    def test_ocr_choices_fit_after_scaling_and_in_a_small_window(self):
        window=self.window;window.task=lambda *args:None
        window.tabs.setCurrentIndex(next(i for i in range(window.tabs.count()) if window.tabs.list.item(i).text()=='Настройки'))
        window.settings_tabs.setCurrentIndex(1);window.show()
        for scale in (60,100,175):
            window.ui_scale_pick.setValue(scale);window.apply_appearance(False)
            window.resize(1280,720);self.app.processEvents()
            for combo in (window.ocr_engine_pick,window.ocr_device_pick,window.filter_pick):
                for index in range(combo.count()):
                    combo.setCurrentIndex(index);self.app.processEvents()
                    option=QStyleOptionComboBox();combo.initStyleOption(option)
                    rect=combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,combo).adjusted(4,2,-4,-2)
                    required=combo.fontMetrics().boundingRect(QRect(0,0,rect.width(),1000),Qt.TextFlag.TextWordWrap,combo.currentText())
                    with self.subTest(scale=scale,text=combo.currentText()):
                        self.assertLessEqual(required.height(),rect.height())
                        self.assertLessEqual(required.width(),rect.width())

    def test_gpu_fallback_is_visible_and_reports_no_private_error_text(self):
        window=self.window;window.ocr_engine_pick.setCurrentIndex(window.ocr_engine_pick.findData('game'))
        with patch('windowwords.game_ocr.status',return_value={'requested':'gpu','active':'cpu','fallback':'initialization','loading':False}):
            window.refresh_diagnostics();self.assertIn('GPU недоступна',window.ocr_backend_status.text())
            self.assertEqual(window.report()['ocr_runtime']['active'],'cpu')
