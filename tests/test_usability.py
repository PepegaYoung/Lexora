import sentencepiece,ctranslate2
from pathlib import Path
import tempfile,unittest,time
import ctypes
from ctypes import wintypes
from unittest.mock import patch,Mock
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QKeyEvent,QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from windowwords.app import MainWindow,STYLE
from windowwords.storage import Store
from windowwords.core import Box,Line,Word
from windowwords.controls import HotkeyEdit
from windowwords import native
from windowwords.design import PAGE_HELP

class Keys:
    def __init__(self,*args):self.started=0;self.stopped=0;self.allow=args[3] if len(args)>3 else True
    def start(self):self.started+=1
    def stop(self):self.stopped+=1
    def join(self,**kwargs):pass
    def set_escape(self,enabled):pass

class UsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch('windowwords.native.Hotkeys',Keys)
        self.patch.start()
        self.capture_patch=patch('windowwords.controls.InputCapture')
        self.capture_patch.start()
        self.app.setStyleSheet(STYLE)
        self.window=MainWindow(Store(Path(self.temp.name)))
        self.window.timer.stop();self.window.hover_timer.stop()
    def tearDown(self):
        self.window.close();self.app.processEvents()
        self.capture_patch.stop();self.patch.stop();self.temp.cleanup()

    def snapshot(self):
        self.window.task=lambda *args:None
        self.window.begin_session()
        self.window.show_freeze(Image.new('RGB',(1000,600)),self.window.monitor,'study')
        self.app.processEvents()
        frame=self.window.freeze
        frame.set_lines([Line('A sword',Box(20,100,200,40),(Word('sword',Box(80,100,100,40)),))])
        return frame

    def test_external_snapshot_fullscreen_and_card_owned_above_it(self):
        frame=self.snapshot()
        self.assertTrue(frame.isFullScreen())
        self.window.show_card('sword','A sword')
        self.app.processEvents()
        self.assertTrue(self.window.card.isVisible())
        self.assertIs(self.window.card.windowHandle().transientParent(),frame.windowHandle())
        self.assertIsNone(self.window.card.parent())
        native.user.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT]
        native.user.GetWindow.restype=wintypes.HWND
        self.assertEqual(native.user.GetWindow(int(self.window.card.winId()),4),int(frame.winId()))
        self.assertFalse(self.window.card.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertLessEqual(self.window.card.close_button.width(),32)
        QTest.mouseClick(self.window.card.close_button,Qt.MouseButton.LeftButton)
        self.assertIsNone(self.window.freeze)
        self.assertFalse(self.window.card.isVisible())
        self.assertFalse(native.user.GetWindow(int(self.window.card.winId()),4))
        # The persistent card must survive deletion of its transient owner.
        self.app.processEvents()
        self.window.show_card('jerkin','A jerkin')
        self.assertTrue(self.window.card.isVisible())

    def test_hover_dwell_opens_card_without_click(self):
        frame=self.snapshot()
        rect=frame.image_rect()
        point=QPointF(rect.x()+130*rect.width()/1000,rect.y()+120*rect.height()/600)
        event=QMouseEvent(QEvent.Type.MouseMove,point,point,Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(frame,event)
        self.assertTrue(frame.word_timer.isActive())
        deadline=time.monotonic()+2
        while not self.window.card.isVisible() and time.monotonic()<deadline:
            QTest.qWait(20)
        self.assertTrue(self.window.card.isVisible())
        self.assertEqual(self.window.card.term.text(),'sword')

    def test_dragging_selection_or_disabling_auto_card_cancels_hover(self):
        frame=self.snapshot()
        frame.hover_word=frame.lines[0].words[0]
        frame.hover_sentence='A sword'
        frame.word_timer.start()
        self.window.set_auto_card(False)
        self.assertFalse(frame.word_timer.isActive())
        frame.preview_word()
        self.assertFalse(self.window.card.isVisible())

    def test_hover_hotkey_in_external_mode_only_toggles_snapshot_cards(self):
        self.assertFalse(self.window.hover)
        self.window.on_hotkey('hover')
        self.assertFalse(self.window.settings['auto_card'])
        self.assertFalse(self.window.hover)

    def record(self,action='study'):
        field=self.window.hotkey_fields[action]
        field.begin()
        return field

    def test_pressed_shift_q_is_saved_and_global_actions_paused_during_capture(self):
        field=self.record()
        previous=self.window.keys
        self.assertTrue(self.window.hotkey_capture_active)
        self.assertEqual(previous.stopped,1)
        self.window.capture_freeze=Mock()
        self.window.on_hotkey('study')
        self.window.capture_freeze.assert_not_called()
        QTest.keyPress(field,Qt.Key.Key_Q,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(field.text(),'Shift+Q')
        self.assertEqual(self.window.store.settings()['hotkeys']['study'],'Shift+Q')
        self.assertTrue(self.window.hotkey_capture_active)
        QTest.keyRelease(field,Qt.Key.Key_Q,Qt.KeyboardModifier.ShiftModifier)
        QTest.keyRelease(field,Qt.Key.Key_Shift)
        self.app.processEvents()
        self.assertFalse(self.window.hotkey_capture_active)
        self.assertIsNot(self.window.keys,previous)
        self.assertEqual(self.window.keys.started,1)
        self.assertFalse(self.window.keys.allow)

    def test_duplicate_is_rejected_and_escape_keeps_previous_binding(self):
        field=self.record('study')
        QTest.keyClick(field,Qt.Key.Key_W,Qt.KeyboardModifier.AltModifier)
        QTest.keyRelease(field,Qt.Key.Key_Alt)
        self.app.processEvents()
        self.assertEqual(field.text(),'Alt+Q')
        self.assertEqual(self.window.settings['hotkeys']['study'],'Alt+Q')
        field.begin()
        QTest.keyClick(field,Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(field.text(),'Alt+Q')
        self.assertFalse(self.window.hotkey_capture_active)

    def test_native_vk_records_latin_key_even_on_russian_layout(self):
        field=self.record()
        # The physical Q key produces Й on a Russian layout; VK remains Q.
        event=QKeyEvent(QEvent.Type.KeyPress,0x0419,Qt.KeyboardModifier.ShiftModifier,0x10,0x51,0,'Й')
        QApplication.sendEvent(field,event)
        self.assertEqual(field.text(),'Shift+Q')
        field.finish();self.app.processEvents()

    def test_modifier_only_is_ignored_and_bare_letter_is_saved(self):
        field=self.record()
        QTest.keyClick(field,Qt.Key.Key_Shift)
        self.assertEqual(field.text(),'Alt+Q')
        QTest.keyClick(field,Qt.Key.Key_A)
        self.assertEqual(field.text(),'A')
        self.assertEqual(self.window.store.settings()['hotkeys']['study'],'A')
        field.finish();self.app.processEvents()

    def test_recording_does_not_apply_unsaved_provider_selection(self):
        original=self.window.settings['provider']
        self.window.provider.setCurrentIndex(self.window.provider.findData('api'))
        field=self.record()
        QTest.keyClick(field,Qt.Key.Key_Q,Qt.KeyboardModifier.ShiftModifier)
        QTest.keyRelease(field,Qt.Key.Key_Shift)
        self.app.processEvents()
        self.assertEqual(self.window.settings['provider'],original)

    def test_closed_help_does_not_reappear_for_same_selection(self):
        self.window.show();self.app.processEvents()
        control=self.window.screen_scope
        self.window.help.show('Пояснение',source=control)
        self.assertFalse(self.window.help_panel.isHidden())
        self.assertLessEqual(self.window.help_panel.height(),100)
        QTest.mouseClick(self.window.help_panel.close_button,Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.help_panel.isHidden())
        self.window.help.show('Пояснение',source=control)
        self.assertTrue(self.window.help_panel.isHidden())
        control.setCurrentIndex(control.findData('monitor'))
        self.assertFalse(self.window.help_panel.isHidden())
        self.assertEqual(control.toolTip(),'')

    def test_help_never_overlaps_working_navigation_at_large_scale(self):
        self.window.ui_scale_pick.setValue(175)
        self.window.apply_appearance()
        self.window.resize(900,650);self.window.show()
        self.window.help.show(max(PAGE_HELP.values(),key=len),source=self.window.provider)
        self.app.processEvents()
        self.assertLessEqual(self.window.help_panel.height(),130)
        label=self.window.help_panel.text
        self.assertGreaterEqual(label.height(),label.heightForWidth(label.width()))
        self.assertLessEqual(self.window.tabs.geometry().bottom(),self.window.help_panel.geometry().top())
