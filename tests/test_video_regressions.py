import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch,Mock
from PIL import Image
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from windowwords.core import Box,Line,Word
from windowwords.screen import blocks
from windowwords.screen_layout import layout
from windowwords.screen_text import measure_text,wrapped_text
from windowwords.widgets import Freeze
from tests.test_capture_lifecycle import ScreenHarness
from tests import test_usability as usability


class VideoLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_padded_detector_rows_form_one_body_separate_from_heading(self):
        positions=((107,17),(125,23),(147,21),(169,20),(189,21),(211,20),
                   (233,17),(249,25),(272,24),(295,20),(314,23),(337,21))
        texts=('For someone who is ready','to continue our little journey',
               'the traveller keeps waiting','getting cold feet in the rain',
               'We could always take a map','or follow the river together',
               'there is another way through','getting to the bridge... Should',
               'we go talk to the guide now.','She is making breakfast in',
               'the kitchen each morning, if I','remember correctly.')
        rows=[Line('Journey',Box(65,65,126,28),())]
        rows.extend(Line(text,Box(65+(i%3),y,200,h),()) for i,((y,h),text) in enumerate(zip(positions,texts)))
        result=blocks(rows)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0].text,'Journey')
        self.assertEqual(result[1].text,'\n'.join(texts))

    def test_overlapping_same_baseline_labels_are_not_a_paragraph(self):
        result=blocks([Line('Start',Box(10,20,50,28),()),Line('Settings',Box(12,22,65,27),())])
        self.assertEqual(len(result),2)

    def test_short_translation_uses_space_without_breaking_one_word(self):
        for text in ('Полдень','Подсказки'):
            labels,skipped=layout([(Box(120,40,52,20),text)],300,140,'replace',22,14,measure_text)
            self.assertEqual(skipped,0);self.assertEqual(labels[0].size,22)
            drawn,_=wrapped_text(text,labels[0].size,labels[0].box.w-8)
            self.assertEqual(drawn.lineCount(),1)

    def test_neighbour_limits_expansion_and_font_still_keeps_word_whole(self):
        obstacle=Box(182,35,60,40)
        labels,skipped=layout([(Box(120,40,52,20),'Полдень')],300,140,'replace',22,14,measure_text,[obstacle])
        self.assertEqual(skipped,0)
        drawn,_=wrapped_text(labels[0].text,labels[0].size,labels[0].box.w-8)
        self.assertEqual(drawn.lineCount(),1)

    def test_window_snapshot_backdrop_is_translucent_and_game_stays_opaque(self):
        frame=Image.new('RGB',(100,100),'black');frame.paste('red',(20,30,80,80))
        window=Freeze(frame,{'x':0,'y':0,'w':100,'h':100,'name':'test'},content_box=Box(20,30,60,50))
        window.resize(100,100);window.notice=''
        picture=window.grab().toImage()
        self.assertEqual(picture.pixelColor(50,90).alpha(),130)
        self.assertEqual(picture.pixelColor(50,70).alpha(),255)
        window.close();self.app.processEvents()


class StaticFrameTests(unittest.TestCase):
    def test_only_game_client_is_processed_and_word_coordinates_are_restored(self):
        window=ScreenHarness();window.screen_target=123
        window.capture_image.return_value=Image.new('RGB',(400,300))
        row=Line('Hello',Box(20,30,80,20),(Word('Hello',Box(20,30,80,20)),))
        with patch('windowwords.native.foreground',return_value=123),\
                patch('windowwords.native.client_bounds',return_value=Box(100,150,400,300)),\
                patch('windowwords.screen_mode.ocr.read',return_value=(row,)):
            window.tick();fn,done,failed=window.jobs.pop();done(fn())
        window.capture_image.assert_called_once_with(Box(100,150,400,300))
        self.assertEqual(window.lines[0].box,Box(120,180,80,20))
        self.assertEqual(window.lines[0].words[0].box,Box(120,180,80,20))

    def test_identical_frames_skip_ocr_but_still_stabilize_text(self):
        window=ScreenHarness();window.capture_image.return_value=Image.new('RGB',(800,600),'white')
        row=Line('Hello',Box(20,20,80,20),())
        with patch('windowwords.screen_mode.ocr.read',return_value=(row,)) as read:
            for now in (1,1.4):
                window.tick();fn,done,failed=window.jobs.pop()
                result=fn()
                with patch('windowwords.screen_mode.time.monotonic',return_value=now):done(result)
            self.assertEqual(read.call_count,1)
            self.assertEqual(window.screen_tracks.missing(),['Hello'])
            window.capture_image.return_value=Image.new('RGB',(800,600),'black')
            window.tick();window.jobs.pop()[0]()
            self.assertEqual(read.call_count,2)

    def test_restart_does_not_reuse_previous_session_frame(self):
        window=ScreenHarness();window.capture_image.return_value=Image.new('RGB',(800,600))
        with patch('windowwords.screen_mode.ocr.read',return_value=()) as read:
            window.tick();fn,done,failed=window.jobs.pop();done(fn())
            window.stop();window.running=True
            window.tick();window.jobs.pop()[0]()
            self.assertEqual(read.call_count,2)


class SnapshotSelectionTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_new_selection_hides_card_and_cancels_old_request_without_closing_snapshot(self):
        window=self.window
        window.show_freeze(Image.new('RGB',(800,600)),window.monitor,'study')
        window.show_card('Hello','Hello world');self.app.processEvents()
        snapshot=window.freeze;revision=window.card_epoch.value
        QTest.mousePress(snapshot,Qt.MouseButton.LeftButton,pos=QPoint(80,100))
        self.assertFalse(window.card.isVisible())
        self.assertGreater(window.card_epoch.value,revision)
        self.assertIs(window.freeze,snapshot);self.assertTrue(window.session_active)
        self.assertFalse(window.auto_translate_timer.isActive())
        QTest.mouseRelease(snapshot,Qt.MouseButton.LeftButton,pos=QPoint(80,100))


if __name__=='__main__':unittest.main()
