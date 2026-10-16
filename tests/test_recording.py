import sentencepiece,ctranslate2
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image
from tests import test_usability as usability
from windowwords import native
from windowwords.core import Box
from windowwords.recording_capture import crop_window
from windowwords.backup import export_backup,import_backup
from windowwords.storage import Store


class RecordingGeometryTests(unittest.TestCase):
    def test_crop_preserves_negative_monitor_coordinates_and_blanks_other_windows(self):
        image=Image.new('RGB',(400,200),'blue')
        result=crop_window(image,Box(-300,100,400,200),Box(-400,50,600,300))
        self.assertEqual(result.size,(600,300))
        self.assertEqual(result.getpixel((101,51)),(0,0,255))
        self.assertEqual(result.getpixel((0,0)),(0,0,0))
        self.assertEqual(result.getpixel((550,250)),(0,0,0))

    def test_other_monitor_is_rejected_instead_of_reading_desktop(self):
        with self.assertRaises(RuntimeError):crop_window(Image.new('RGB',(100,100)),Box(0,0,100,100),Box(1920,0,100,100))

    def test_recording_visibility_survives_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=Store(root/'source');target=Store(root/'target')
            settings=source.settings();self.assertFalse(settings['recording_visible'])
            settings['recording_visible']=True;source.save_settings(settings)
            export_backup(source,source.settings(),root/'backup.json')
            import_backup(target,root/'backup.json');self.assertTrue(target.settings()['recording_visible'])


class RecordingUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_toggle_persists_and_updates_existing_and_new_windows_without_restart(self):
        window=self.window
        with patch.object(native.user,'SetWindowDisplayAffinity',return_value=1) as affinity:
            window.recording_pick.setChecked(True)
            self.assertTrue(window.store.settings()['recording_visible'])
            self.assertTrue(all(w.property('captureVisible') for w in (window,window.card,window.overlay,window.result_window)))
            self.assertTrue(all(call.args[1]==0 for call in affinity.call_args_list))
            window.show_freeze(Image.new('RGB',(100,100)),window.monitor,'region')
            self.assertTrue(window.freeze.property('captureVisible'))
            affinity.reset_mock();window.recording_pick.setChecked(False)
            self.assertFalse(window.store.settings()['recording_visible'])
            self.assertTrue(all(call.args[1]==0x11 for call in affinity.call_args_list))
            self.assertFalse(window.freeze.property('captureVisible'))

    def test_clean_capture_has_no_desktop_fallback_and_target_is_stable_during_auto(self):
        window=self.window;window.settings['recording_visible']=True
        window.recording_target=101;window.recording_capture.grab=Mock(return_value='clean-game-frame')
        with patch('windowwords.app.mss.mss') as desktop:
            self.assertEqual(window.capture_image(Box(0,0,300,200)),'clean-game-frame')
            window.recording_target=None
            with self.assertRaises(RuntimeError):window.capture_image(Box(0,0,300,200))
            desktop.assert_not_called()
        window.recording_target=101;window.running=True
        with patch('windowwords.native.foreground',return_value=202):window.remember_recording_target()
        self.assertEqual(window.recording_target,101)
        window.running=False
        with patch('windowwords.native.foreground',return_value=202),patch('windowwords.native.is_our_window',return_value=False):window.remember_recording_target()
        self.assertEqual(window.recording_target,202)

    def test_game_protection_still_blocks_capture_in_recording_mode(self):
        window=self.window;window.settings['recording_visible']=True;window.safety_blocked=True
        with patch.object(window.recording_capture,'grab') as clean:
            with self.assertRaises(RuntimeError):window.capture_image(Box(0,0,300,200))
            clean.assert_not_called()
