import sentencepiece,ctranslate2
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from windowwords.app import MainWindow,STYLE
from windowwords.storage import Store
from windowwords.widgets import Freeze
from windowwords import ocr
from windowwords.core import Box,Line


class Keys:
    def __init__(self,*args):self.escape = False
    def start(self):pass
    def stop(self):pass
    def join(self,**kwargs):pass
    def set_escape(self,enabled):self.escape = enabled


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch('windowwords.native.Hotkeys',Keys),patch('windowwords.native.foreground',return_value=4321),
            patch('windowwords.native.is_our_window',return_value=False),patch('windowwords.native.restore_foreground',return_value=True),
            patch.object(Freeze,'show_on_monitor',lambda window:window.show()),patch('windowwords.safety.running_executables',return_value=set())]
        self.mocks = [p.start() for p in self.patches]
        self.patches.append(patch('windowwords.native.transition_keys_held',return_value=False))
        self.patches[-1].start()
        self.app.setStyleSheet(STYLE)
        store=Store(Path(self.temp.name))
        settings=store.settings()
        settings.update(game_mode='overlay',provider='subscription')
        store.save_settings(settings)
        self.window = MainWindow(store)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        for widget in (self.window.card,self.window.overlay,self.window.result_window,self.window):widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def session(self):
        self.window.begin_session()
        self.window.hide()
        self.window.show_freeze(Image.new('RGB',(300,150)),self.window.monitor,'region')
        self.window.show_card('sword','He drew his sword.')
        self.app.processEvents()

    def assert_closed(self):
        self.app.processEvents()
        self.assertFalse(self.window.session_active)
        self.assertIsNone(self.window.freeze)
        self.assertFalse(self.window.card.isVisible())
        self.assertTrue(not self.window.isVisible() or self.window.isMinimized())
        self.assertFalse(self.window.keys.escape)
        self.mocks[3].assert_called_with(4321)

    def test_escape_in_editable_card_closes_all_to_game(self):
        self.session()
        self.window.card.sentence.setFocus()
        QTest.keyClick(self.window.card.sentence,Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assert_closed()

    def test_native_escape_when_game_has_focus(self):
        self.session()
        self.window.on_hotkey('escape')
        self.assert_closed()

    def test_screen_escape_stops_translation_without_showing_main(self):
        self.window.timer.stop()
        self.window.screen_scope.setCurrentIndex(self.window.screen_scope.findData('monitor'))
        self.window.start_screen(True)
        self.assertTrue(self.window.running)
        self.assertTrue(self.window.keys.escape)
        self.assertTrue(self.window.isMinimized())
        self.window.on_hotkey('escape')
        self.assertFalse(self.window.running)
        self.assertFalse(self.window.keys.escape)
        self.assertFalse(self.window.overlay.isVisible())
        self.assertTrue(self.window.isMinimized())

    def test_snapshot_translates_all_lines_and_does_not_recapture(self):
        self.window.timer.stop()
        self.window.region=Box(100,100,600,200)
        self.window.settings['provider']='local'
        self.window.overlay.display_segments=Mock(return_value=0)
        pending=[]
        self.window.task=lambda fn,done,failed=None:pending.append((fn,done))
        self.window.start_screen(True)
        self.window.tick()
        _,ocr_done=pending.pop(0)
        ocr_done([Line('Open',Box(20,80,100,25),()),Line('Quit',Box(20,130,100,25),())])
        self.assertEqual(len(pending),1)
        _,translate_done=pending.pop(0)
        translate_done(('Открыть','Выход'))
        self.window.tick()
        self.assertEqual(pending,[])
        entries=self.window.overlay.display_segments.call_args.args[0]
        self.assertEqual([text for line,text in entries],['Открыть','Выход'])

    def test_stopped_screen_rejects_late_response(self):
        self.window.timer.stop()
        self.window.region=Box(100,100,600,90)
        self.window.overlay.display_segments=Mock(return_value=0)
        pending=[]
        self.window.task=lambda fn,done,failed=None:pending.append(done)
        self.window.start_screen(True)
        self.window.tick()
        pending.pop(0)([Line('Open',Box(0,50,100,25),())])
        answer=pending.pop(0)
        self.window.stop()
        answer(('Открыть',))
        self.window.overlay.display_segments.assert_not_called()

    def test_card_close_button_closes_frame_too(self):
        self.session()
        self.window.card.close()
        self.app.processEvents()
        self.assert_closed()

    def test_closed_capture_cannot_reappear_after_delayed_result(self):
        pending = []
        self.window.task = lambda fn,done,failed=None:pending.append(done)
        self.window.capture_freeze('study')
        QTest.qWait(260)
        self.assertEqual(len(pending),1)
        self.window.on_hotkey('escape')
        pending[0](Image.new('RGB',(300,150)))
        self.assert_closed()

    def test_translate_selection_not_entire_context(self):
        self.session()
        captured = []
        self.window.translator.translate = lambda settings,text,*args,**kwargs:(captured.append(text) or 'меч','mock')
        self.window.task = lambda fn,done,failed=None:done(fn())
        self.window.analyze_card(False)
        self.assertEqual(captured,['sword'])
        self.window.analyze_card(False,True)
        self.assertEqual(captured[-1],'He drew his sword.')

    def test_closed_card_rejects_late_translation(self):
        self.session()
        pending = []
        self.window.task = lambda fn,done,failed=None:pending.append(done)
        self.window.analyze_card(False)
        self.window.close_session()
        pending[0](('late answer','mock'))
        self.assertFalse(self.window.card.isVisible())
        self.assertNotEqual(self.window.card.answer.toPlainText(),'late answer')

    def test_appearance_applies_to_text_card_and_overlay(self):
        self.window.ui_scale_pick.setValue(150)
        self.window.card_width_pick.setValue(720)
        self.window.card_height_pick.setValue(760)
        self.window.card_background_pick.setValue(70)
        self.window.opacity_pick.setValue(60)
        self.window.apply_appearance()
        self.assertIn('font-size:23px',self.app.styleSheet())
        self.assertEqual(self.window.card.width(),720)
        self.assertEqual(self.window.card.windowOpacity(),1.0)
        self.assertAlmostEqual(self.window.card.background_alpha,.7)
        self.assertEqual(self.window.settings['opacity'],.6)

    def test_plain_translator_disables_gpt_explanation(self):
        self.window.settings['provider'] = 'yandex'
        self.window.show_card('sword','He drew his sword.')
        self.assertFalse(self.window.card.explain_button.isEnabled())

    def test_free_provider_has_no_key_controls_and_can_be_selected(self):
        for name in ('yandex_web',):
            self.window.provider.setCurrentIndex(self.window.provider.findData(name))
            self.assertTrue(self.window.apply_settings())
            self.assertEqual(self.window.settings['provider'],name)
            self.assertNotIn(name,self.window.cloud_keys)
            self.assertFalse(self.window.model_group.isVisible())
        self.window.settings['card_opacity']=.5
        self.window.show_card('sword','He drew his sword.')
        self.assertEqual(self.window.card.windowOpacity(),1.0)
        self.assertFalse(self.window.card.explain_button.isEnabled())

    def test_small_card_large_text_keeps_controls_scrollable(self):
        self.window.ui_scale_pick.setValue(175)
        self.window.card_width_pick.setValue(400)
        self.window.card_height_pick.setValue(400)
        self.window.apply_appearance()
        self.window.show_card('sword','He drew his sword.')
        self.app.processEvents()
        area = self.window.card.content_area
        self.assertEqual(area.horizontalScrollBar().maximum(),0)
        self.assertGreater(area.verticalScrollBar().maximum(),0)
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        self.assertTrue(self.window.card.explain_button.isVisible())

    def test_all_ocr_profiles_preserve_frame_coordinates(self):
        image = Image.new('RGB',(300,120),'yellow')
        for value,_,_ in ocr.PROFILES:
            with self.subTest(profile=value):
                output = ocr.prepare(image,value)
                self.assertEqual(output.size,image.size)
                self.assertEqual(output.mode,'RGB')

    def test_capture_keeps_main_window_available_for_alt_tab(self):
        self.window.capture_freeze('study')
        self.assertTrue(self.window.isVisible())

    def test_switching_to_game_before_escape_keeps_main_minimized(self):
        with patch('windowwords.native.foreground',return_value=8765),patch('windowwords.native.is_our_window',return_value=True):
            self.window.capture_freeze('study')
        self.window.close_session()
        self.assertTrue(self.window.isMinimized())
        self.app.processEvents()
        self.mocks[3].assert_called_with(4321)
        self.assertTrue(self.window.isMinimized())
        self.window.close_session()
        self.assertTrue(self.window.isVisible())

    def test_wheel_and_buttons_change_unfocused_value(self):
        value = self.window.ui_scale_pick
        before = value.value()
        wheel = QWheelEvent(QPointF(10,10),QPointF(10,10),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(value,wheel)
        self.assertEqual(value.value(),before+value.singleStep())
        self.assertTrue(wheel.isAccepted())

    def test_model_display_name_saves_server_slug(self):
        self.window.model_connection_ready=Mock(return_value=True)
        self.window.translator.models = lambda provider:[('gpt-6.1-sol','GPT-6.1 Sol')]
        self.window.task = lambda fn,done,failed=None:done(fn())
        self.window.get_models()
        self.window.model_pick.setCurrentIndex(self.window.model_pick.findData('gpt-6.1-sol'))
        self.window.apply_settings()
        self.assertEqual(self.window.settings['models']['subscription'],'gpt-6.1-sol')

    def test_one_bad_ocr_frame_does_not_cancel_gpt_or_hide_translation(self):
        from windowwords.screen import Tracker
        self.window.timer.stop()
        self.window.region = Box(100,100,600,90)
        self.window.running = True
        self.window.screen_snapshot=False
        self.window.screen_tracks=Tracker()
        self.window.overlay.hide = Mock()
        self.window.overlay.display_segments = Mock(return_value=0)
        callbacks = []
        self.window.task = lambda fn,done,failed=None:callbacks.append((done,failed))
        def frame(text,now):
            with patch('windowwords.screen_mode.time.monotonic',return_value=now):
                self.window.tick()
                done,_ = callbacks.pop(0)
                done([Line(text,Box(0,0,600,40),())] if text else [])
        frame('Maybe they missed something.',0)
        frame('Maybe they missed something.',.4)
        answer,_ = callbacks.pop(0)
        revision = self.window.epoch.value
        self.window.overlay.hide.reset_mock()
        frame('Maybe they rnissed something.',.5)
        frame('Maybe they missed something.',.7)
        self.assertEqual(self.window.epoch.value,revision)
        answer(('Может быть, они что-то упустили.',))
        self.window.overlay.display_segments.assert_called_once()
        self.window.overlay.hide.reset_mock()
        frame('',.8)
        frame('',1.15)
        self.assertEqual(self.window.epoch.value,revision)
        self.window.overlay.hide.assert_not_called()
        frame('',2.3)
        self.assertFalse(self.window.screen_tracks.ready())
        self.window.overlay.hide.assert_called()
