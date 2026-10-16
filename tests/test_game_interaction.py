import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent,QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from tests import test_usability as usability
from windowwords.core import Box,Line
from windowwords.screen import blocks,intersects,Tracker
from windowwords.screen_layout import layout
from windowwords.screen_text import measure_text,wrapped_text
from windowwords.backup import export_backup,import_backup
from windowwords.storage import Store
from windowwords import native


class GameInteractionTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_size_locks_prevent_drag_allow_presets_and_survive_backup(self):
        window=self.window;window.show();window.card.show();self.app.processEvents()
        window.window_lock_pick.click();window.card_lock_pick.click()
        self.assertEqual(window.minimumSize(),window.maximumSize())
        self.assertEqual(window.card.minimumSize(),window.card.maximumSize())
        handle=window.card.resize_handles[7];before=window.card.size()
        event=QMouseEvent(QEvent.Type.MouseButtonPress,QPointF(1,1),QPointF(1,1),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(handle,event);self.assertIsNone(handle.origin)
        window.card.resize(800,900);self.assertEqual(window.card.size(),before)
        window.window_size_pick.setCurrentIndex(window.window_size_pick.findData('1080p'));self.app.processEvents()
        self.assertEqual(window.minimumSize(),window.maximumSize())
        self.assertGreater(window.width(),1280)
        window.card_size_pick.setCurrentIndex(window.card_size_pick.findData('large'));window.apply_appearance()
        self.assertEqual((window.card.width(),window.card.height()),(720,840))
        self.assertEqual(window.card.minimumSize(),window.card.maximumSize())
        export_backup(window.store,window.settings,window.store.folder/'backup.json')
        target=Store(window.store.folder/'target');import_backup(target,window.store.folder/'backup.json')
        self.assertTrue(target.settings()['window_size_locked']);self.assertTrue(target.settings()['card_size_locked'])
        window.window_lock_pick.click();window.card_lock_pick.click()
        self.assertNotEqual(window.minimumSize(),window.maximumSize())
        self.assertNotEqual(window.card.minimumSize(),window.card.maximumSize())
        window.card.resize(650,750);self.assertEqual((window.card.width(),window.card.height()),(650,750))

    def test_reset_appearance_unlocks_window_and_card(self):
        window=self.window;window.window_lock_pick.click();window.card_lock_pick.click();window.reset_appearance()
        self.assertFalse(window.window_lock_pick.isChecked());self.assertFalse(window.card_lock_pick.isChecked())
        self.assertFalse(window.store.settings()['card_size_locked'])
        self.assertNotEqual(window.minimumSize(),window.maximumSize())

    def test_paragraphs_join_uppercase_continuations_without_four_line_cutoff(self):
        rows=[Line('This is a long wrapped English sentence',Box(500,100+i*26,280,22),()) for i in range(14)]
        rows.insert(5,Line('Gold',Box(10,222,30,22),()))
        result=blocks(rows)
        paragraph=next(line for line in result if line.box.x==500)
        self.assertEqual(paragraph.text.count('\n'),13)
        self.assertEqual(len(result),2)
        self.assertEqual(len(blocks([Line('1. First choice',Box(50,100,180,20),()),Line('2. Second choice',Box(50,125,180,20),())])),2)

    def test_dense_paragraphs_fit_inside_game_and_stay_near_source(self):
        paragraph=Box(910,140,260,360)
        text='Она продолжает нашу маленькую историю. Нужно поговорить с ней сейчас. '*6
        entries=[(Box(930,10,220,24),'История персонажа'),(paragraph,text),(Box(600,630,90,25),'Холл')]
        for mode in ('above','replace'):
            labels,skipped=layout(entries,1200,700,mode,22,14,measure_text)
            self.assertEqual(skipped,0,(mode,labels))
            self.assertEqual(len(labels),3)
            for label in labels:
                self.assertGreaterEqual(label.box.x,0);self.assertGreaterEqual(label.box.y,0)
                self.assertLessEqual(label.box.x+label.box.w,1200);self.assertLessEqual(label.box.y+label.box.h,700)
                rendered,height=wrapped_text(label.text,label.size,label.box.w-8)
                self.assertLessEqual(height,label.box.h-(8 if mode=='replace' else 6))
                self.assertGreater(rendered.lineCount(),0)
                if mode=='above':self.assertFalse(any(intersects(label.box,source) for source,_ in entries))
            long=next(label for label in labels if label.source==paragraph)
            if mode=='above':
                self.assertEqual(long.placement,'below')
                self.assertGreaterEqual(long.box.y,paragraph.y+paragraph.h)

    def test_unbroken_words_wrap_with_same_metrics_as_painting(self):
        text='СверхдлинноеСловоБезПробелов'*15
        wrapped,height=wrapped_text(text,22,170)
        self.assertGreater(wrapped.lineCount(),1)
        self.assertEqual(measure_text(text,22,170)[1],height)
        self.assertEqual(sum(wrapped.lineAt(i).textLength() for i in range(wrapped.lineCount())),len(text))
        for index in range(wrapped.lineCount()):self.assertLessEqual(wrapped.lineAt(index).naturalTextWidth(),171)

    def test_overlay_uses_game_bounds_on_negative_monitor_and_clips_paint(self):
        window=self.window;overlay=window.overlay
        monitor={'x':-1920,'y':100,'w':1920,'h':1080};region=Box(-1920,100,1920,1080);bounds=Box(-1700,220,1200,700)
        line=Line('A long paragraph',Box(1130,260,260,350),())
        text='Длинный русский перевод остаётся в пределах игры. '*8
        settings=dict(window.settings,screen_mode='replace')
        with patch.object(native,'place') as place,patch.object(native,'exclude_capture',return_value=True):
            skipped=overlay.display_segments([(line,text)],region,monitor,settings,[line],bounds=bounds)
            self.assertEqual(skipped,0);place.assert_called_with(overlay,bounds)
            self.assertEqual(overlay.viewport,bounds)
            self.assertEqual(overlay.position,(-1700,220,1200,700))
            overlay.resize(1200,700);self.app.processEvents()
            image=overlay.grab().toImage()
            label=overlay.labels[0];self.assertLessEqual(label.box.x+label.box.w,1200)
            self.assertEqual(image.pixelColor(10,10).alpha(),0)
            self.assertGreater(image.pixelColor(round(label.box.x+10),round(label.box.y+10)).alpha(),0)
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(overlay.windowFlags()&Qt.WindowType.WindowDoesNotAcceptFocus)

    def test_normal_capture_uses_compatible_desktop_without_wgc(self):
        window=self.window;window.screen_target=123
        box=Box(0,0,800,600);window.recording_capture.grab=Mock(return_value='game-frame')
        with patch.object(window,'capture_image',return_value='desktop-frame') as desktop:
            self.assertEqual(window.capture_screen_image(box),'desktop-frame')
            desktop.assert_called_once_with(box);window.recording_capture.grab.assert_not_called()
        window.safety_blocked=True
        with self.assertRaises(RuntimeError):window.capture_screen_image(box)

    def test_recordable_snapshot_capture_is_closed_even_after_failure(self):
        window=self.window;window.session_target=123
        window.settings['recording_visible']=True;window.recording_target=123;window.session_active=True
        box=Box(0,0,800,600)
        with patch.object(native,'client_bounds',return_value=box),patch('windowwords.recording.CleanCapture') as factory:
            factory.return_value.grab.return_value='frame'
            self.assertEqual(window.capture_session_image(box),'frame');factory.return_value.close.assert_called_once()
            factory.return_value.close.reset_mock();factory.return_value.grab.side_effect=RuntimeError('No frame')
            with self.assertRaises(RuntimeError):window.capture_session_image(box)
            factory.return_value.close.assert_called_once()

    def test_ocr_ignores_window_title_and_desktop_outside_game_client(self):
        window=self.window;window.settings['game_mode']='overlay';window.screen_target=123;window.running=True
        window.settings['screen_scope']='monitor';window.screen_snapshot=False;window.screen_tracks=Tracker()
        m=window.monitor;bounds=Box(m['x']+100,m['y']+100,600,400);pending=[]
        window.task=lambda fn,done,failed=None:pending.append(done)
        window.draw_screen=Mock();window.pump_screen=Mock()
        with patch.object(native,'client_bounds',return_value=bounds),patch.object(native,'foreground',return_value=123):
            window.tick();self.assertEqual(len(pending),1)
            pending[0]((Line('Title bar',Box(110,60,100,20),()),Line('Game text',Box(110,160,100,20),()),Line('Desktop',Box(900,160,100,20),())))
        self.assertEqual([line.text for line in window.lines],['Game text'])

    def test_close_releases_own_mouse_and_keyboard_grabs(self):
        window=self.window;frame=self.snapshot();frame.grabMouse();frame.grabKeyboard()
        with patch.object(native,'transition_keys_held',return_value=False):
            window.close_session(restore=False);self.app.processEvents()
        self.assertIsNone(QWidget.mouseGrabber());self.assertIsNone(QWidget.keyboardGrabber())

    def test_close_waits_for_key_release_and_does_not_change_cursor_counters(self):
        window=self.window;self.snapshot()
        with patch.object(native,'foreground',return_value=123),patch.object(native,'is_our_window',return_value=False),\
                patch.object(native,'restore_foreground',return_value=True) as restore,\
                patch.object(native,'refresh_window_cursor') as refresh,patch.object(native,'transition_keys_held',return_value=True) as held,\
                patch.object(native.user,'ShowCursor') as visibility,patch.object(native.user,'ClipCursor') as clipping:
            window.close_session();self.app.processEvents()
            self.assertIsNone(window.freeze);self.assertFalse(window.card.isVisible());restore.assert_not_called()
            held.return_value=False;QTest.qWait(50)
            restore.assert_called_once_with(123);refresh.assert_called_once_with(123)
            visibility.assert_not_called();clipping.assert_not_called()

    def snapshot(self):
        return usability.UsabilityTests.snapshot(self)

    def test_new_session_cancels_deferred_return_to_old_game(self):
        window=self.window;self.snapshot()
        with patch.object(native,'transition_keys_held',return_value=True) as held,patch.object(native,'restore_foreground') as restore:
            window.close_session();self.app.processEvents();window.begin_session()
            held.return_value=False;QTest.qWait(50);restore.assert_not_called()
