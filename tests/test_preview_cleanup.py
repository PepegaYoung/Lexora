import sentencepiece,ctranslate2
import unittest,time
from unittest.mock import Mock,patch
from PIL import Image
from PySide6.QtWidgets import QDialog
from PySide6.QtTest import QTest
from tests import test_usability as usability
from windowwords.core import Box
from windowwords.ocr_preview import inspect_frame


class PreviewImageTests(unittest.TestCase):
    def test_full_frame_is_only_retained_for_processing(self):
        with patch('windowwords.ocr_preview.ocr.read',return_value=()) as read:
            result=inspect_frame(Image.new('RGB',(2560,1440)),'yellow')
        read.assert_called_once()
        for image in result[:2]:
            self.assertLessEqual(image.width,400);self.assertLessEqual(image.height,230)


class PreviewCleanupTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_recording_preview_closes_its_own_capture_even_on_failure(self):
        window=self.window;window.settings['recording_visible']=True;window.recording_target=101
        with patch('windowwords.recording.CleanCapture') as factory:
            capture=factory.return_value;capture.grab.return_value='one-frame'
            self.assertEqual(window.capture_preview_image(Box(0,0,100,100)),'one-frame')
            capture.close.assert_called_once()
            capture.close.reset_mock();capture.grab.side_effect=RuntimeError('capture unavailable')
            with self.assertRaises(RuntimeError):window.capture_preview_image(Box(0,0,100,100))
            capture.close.assert_called_once()

    def test_preview_is_inline_single_flight_and_stale_result_is_discarded(self):
        window=self.window;window.capture_image=Mock(return_value=Image.new('RGB',(600,300)))
        pending=[];window.task=lambda fn,done,failed=None:pending.append((fn,done,failed))
        window.show();window.preview_ocr();window.preview_ocr()
        deadline=time.monotonic()+1
        while not pending and time.monotonic()<deadline:QTest.qWait(10)
        self.assertEqual(len(pending),1);self.assertFalse(window.ocr_preview_button.isEnabled())
        with patch('windowwords.ocr_preview.ocr.read',return_value=()):result=pending[0][0]()
        pending[0][1](result);self.app.processEvents()
        self.assertTrue(window.ocr_preview_button.isEnabled())
        self.assertFalse(window.ocr_preview.isHidden())
        self.assertFalse(window.findChildren(QDialog))
        window.apply_ocr();self.assertTrue(window.ocr_preview.isHidden())
        window.preview_ocr();QTest.qWait(250);window.apply_ocr();pending[-1][1](result)
        self.assertTrue(window.ocr_preview.isHidden());self.assertTrue(window.ocr_preview_button.isEnabled())

    def test_general_settings_are_optional_and_region_switch_uses_auto_settings(self):
        window=self.window;window.show();self.app.processEvents()
        self.assertTrue(window.game_profiles.content.isHidden())
        self.assertTrue(window.game.isHidden() or not window.game.isVisible())
        window.auto_options.set_expanded(True);window.scope_buttons['monitor'].click()
        self.assertEqual(window.store.settings()['screen_scope'],'monitor')
        self.assertFalse(window.capture_buttons['region'].isHidden())
        self.assertFalse(hasattr(window,'auto_start_region'))
        window.scope_buttons['region'].click()
        self.assertFalse(window.capture_buttons['region'].isHidden())
        window.render_buttons['replace'].click()
        self.assertEqual(window.store.settings()['screen_mode'],'replace')
        window.render_buttons['above'].click()
        self.assertEqual(window.store.settings()['screen_mode'],'above')
        self.assertNotIn('auto_start_region',window.store.settings())
        window.tabs.setCurrentIndex(next(i for i in range(window.tabs.count()) if window.tabs.list.item(i).text()=='Настройки'))
        window.settings_tabs.setCurrentIndex(0);self.app.processEvents()
        window.tabs.setCurrentIndex(0);self.app.processEvents()
        self.assertNotEqual(window.card_options.parentWidget(),window.auto_options.parentWidget())
        self.assertEqual(window.open_image_button.size(),window.snapshot_button.size())
        window.resize(880,580);window.ui_scale_pick.setValue(175);window.apply_appearance();QTest.qWait(60)
        self.assertEqual(window.tabs.widget(0).horizontalScrollBar().maximum(),0)

    def test_region_selection_only_saves_region_even_with_legacy_autostart_flag(self):
        window=self.window;window.settings['auto_start_region']=True
        selection=Mock(mode='region',monitor=window.monitor)
        with patch.object(window,'toggle') as toggle,patch.object(window,'task') as task:
            window.freeze_selected(selection,None,Box(12,16,200,60),'','')
            toggle.assert_not_called();task.assert_not_called()
        self.assertFalse(window.running)
        self.assertEqual(window.store.settings()['region'],window.region.json())
        self.assertNotIn('auto_start_region',window.store.settings())
        with patch.object(window,'task'):
            window.toggle()
            self.assertTrue(window.running)
