import sentencepiece,ctranslate2
import unittest
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from windowwords import native
from windowwords.core import Box,Line
from windowwords.screen_mode import ScreenMode
from windowwords.screen_overlay import ScreenOverlay
from tests.test_capture_lifecycle import ScreenHarness


class FocusLifecycleTests(unittest.TestCase):
    def focused(self):
        w=ScreenHarness();w.screen_target=123
        w.screen_tracks.update((Line('Open',Box(10,10,80,20),()),),0,instant=True)
        w.screen_tracks.remember(['Open'],['Открыть'])
        return w

    def test_alt_tab_hides_overlay_cancels_jobs_and_preserves_cache(self):
        w=self.focused();w.ocr_busy=w.cloud_busy=True
        old=w.epoch.value;w.screen_ocr_revision=w.screen_cloud_revision=old
        with patch.object(native,'foreground',return_value=999):
            self.assertFalse(w.screen_in_focus());self.assertFalse(w.screen_in_focus())
        self.assertTrue(w.running);self.assertTrue(w.screen_suspended)
        self.assertFalse(w.epoch.accepts(old));self.assertFalse(w.ocr_busy);self.assertFalse(w.cloud_busy)
        self.assertEqual(w.screen_tracks.items,[]);self.assertTrue(w.screen_tracks.cache)
        w.recording_capture.close.assert_called_once();w.message.assert_called_once()
        w.overlay.keep_above_game.assert_not_called();self.assertEqual(w.jobs,[])

    def test_return_to_game_resumes_ocr_without_another_hotkey(self):
        w=self.focused()
        with patch.object(native,'foreground',return_value=999):w.tick()
        self.assertEqual(w.jobs,[])
        with patch.object(native,'foreground',return_value=123),patch.object(native,'client_bounds',return_value=Box(0,0,800,600)):
            w.tick()
        self.assertFalse(w.screen_suspended);self.assertEqual(len(w.jobs),1)
        w.overlay.keep_above_game.assert_called_with(123)

    def test_layer_repair_runs_even_while_ocr_and_translation_are_pending(self):
        w=self.focused();w.ocr_busy=w.cloud_busy=True
        with patch.object(native,'foreground',return_value=123):w.tick()
        w.overlay.keep_above_game.assert_called_once_with(123);self.assertEqual(w.jobs,[])

    def test_late_translation_after_alt_tab_cannot_restore_old_overlay(self):
        w=self.focused();w.pump_screen=ScreenMode.pump_screen.__get__(w)
        w.screen_tracks.cache.clear()
        with patch.object(native,'foreground',return_value=123):w.pump_screen()
        old=w.jobs[-1]
        with patch.object(native,'foreground',return_value=999):w.screen_in_focus()
        old[1](['Old']);old[2]('Obsolete failure')
        self.assertEqual(w.history,[]);w.draw_screen.assert_not_called();self.assertTrue(w.running)

    def test_snapshot_survives_focus_change_without_recapture(self):
        w=self.focused();w.screen_snapshot=w.screen_loaded=True
        with patch.object(native,'foreground',return_value=999):w.tick()
        self.assertEqual(len(w.screen_tracks.ready()),1)
        with patch.object(native,'foreground',return_value=123):w.tick()
        self.assertEqual(w.jobs,[]);w.capture_image.assert_not_called()
        w.draw_screen.assert_called_once()

    def test_separate_result_window_does_not_pause_when_user_clicks_it(self):
        w=self.focused();w.external_mode=lambda:True
        with patch.object(native,'foreground',return_value=999):self.assertTrue(w.screen_in_focus())
        w.overlay.hide.assert_not_called();w.recording_capture.close.assert_not_called()


class OverlayLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.overlay=ScreenOverlay();self.addCleanup(self.overlay.close)
        self.overlay.labels=('label',);self.overlay.show()

    def test_unchanged_overlay_is_raised_when_game_moves_above_it(self):
        overlay=self.overlay;overlay.layer_foreground=123
        with patch.object(native,'foreground',return_value=123),patch.object(native,'window_above',return_value=False),\
                patch.object(native,'promote_overlay',return_value=True) as promote,\
                patch.object(native.user,'SetForegroundWindow') as focus,patch.object(native.user,'ShowCursor') as cursor:
            overlay.keep_above_game(123)
        promote.assert_called_once_with(overlay);focus.assert_not_called();cursor.assert_not_called()
        self.assertEqual(overlay.layer_recoveries,1)
        self.assertTrue(overlay.windowFlags()&Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(overlay.windowFlags()&Qt.WindowType.WindowDoesNotAcceptFocus)

    def test_correct_layer_is_not_repeatedly_raised(self):
        self.overlay.layer_foreground=123
        with patch.object(native,'foreground',return_value=123),patch.object(native,'window_above',return_value=True),\
                patch.object(native,'promote_overlay') as promote:
            self.overlay.keep_above_game(123)
        promote.assert_not_called()

    def test_inactive_game_and_hidden_overlay_are_not_raised(self):
        with patch.object(native,'foreground',return_value=999),patch.object(native,'promote_overlay') as promote:
            self.overlay.keep_above_game(123)
            self.overlay.hide();self.overlay.keep_above_game(999)
        promote.assert_not_called()

    def test_native_repair_changes_only_own_z_order_without_activation(self):
        with patch.object(native.user,'SetWindowPos',return_value=1) as position:
            self.assertTrue(native.promote_overlay(self.overlay))
        args=position.call_args.args
        self.assertEqual(args[0],int(self.overlay.winId()))
        self.assertEqual(args[1].value,-1 & ((1<<64)-1))
        self.assertEqual(args[-1],0x213)
