import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch,Mock
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from windowwords.core import Box,Line,Word,Generation
from windowwords.screen import blocks,Tracker
from windowwords.screen_recovery import recover_labels
from windowwords.native import EscapeGate
from tests import test_usability as usability
from tests.test_capture_lifecycle import ScreenHarness
from windowwords.screen_mode import ScreenMode


def row(text,x=100,y=100,w=180,h=20):return Line(text,Box(x,y,w,h),())


class ScreenTextTests(unittest.TestCase):
    def test_crosses_and_standalone_key_icons_never_enter_translation(self):
        lines=[row(text,y=50+i*80) for i,text in enumerate(('X','XX*XXX','xxx','[E]','O 759'))]
        lines.extend([row('OK',y=600),row('Trousers',y=650),row('I am ready.',y=700)])
        self.assertEqual([line.text for line in blocks(lines)],['OK','Trousers','I am ready.'])

    def test_keyboard_button_row_splits_before_separated_keys(self):
        positions=(('Preview',664,59),('Item',730,32),('Space',785,47),('Equip',844,44),('R',911,11),('Drop',941,40))
        words=tuple(Word(text,Box(x,1012,w,25)) for text,x,w in positions)
        lines=blocks((Line('Preview Item Space Equip R Drop',Box(659,1012,323,25),words),))
        self.assertEqual([line.text for line in lines],['Preview Item','Space Equip','R Drop'])

    def test_keys_inside_regular_sentences_are_not_split(self):
        words=tuple(Word(text,Box(20+i*40,20,35,20)) for i,text in enumerate(('Press','R','to','open','the','door')))
        self.assertEqual(len(blocks((Line('Press R to open the door',Box(20,20,235,20),words),))),1)

    def test_centered_subtitle_tail_and_confirmation_form_complete_paragraphs(self):
        for lines in ((row('A long English sentence continues here',x=280,y=825,w=1350,h=24),
                       row('and finishes with another wrapped line',x=280,y=858,w=1350,h=24),
                       row('with a guide.',x=885,y=890,w=140,h=24)),
                      (row('Are you sure you want to return? Progress',x=710,y=490,w=500,h=20),
                       row('will be lost.',x=905,y=517,w=110,h=18))):
            result=blocks(lines)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0].text,'\n'.join(line.text for line in lines))

    def test_short_ocr_dropout_does_not_blink_but_obsolete_text_expires(self):
        tracker=Tracker();tracker.update((row('Water'),),0,instant=True);tracker.remember(['Water'],['Вода'])
        tracker.update((),.9);self.assertEqual(len(tracker.ready()),1)
        tracker.update((),1.6);self.assertEqual(tracker.ready(),())

    def test_new_stable_word_and_numbers_replace_previous_text(self):
        tracker=Tracker();tracker.update((row('Water 8'),),0,instant=True);tracker.remember(['Water 8'],['Вода 8'])
        tracker.update((row('Water 7'),),.4);tracker.update((row('Water 7'),),.8)
        self.assertEqual(tracker.ready(),())
        self.assertEqual(tracker.missing(),['Water 7'])


class LocalRecoveryTests(unittest.TestCase):
    def setUp(self):self.image=Image.new('RGB',(800,600));self.old=row('Water')

    def test_missing_label_is_restored_only_after_exact_fresh_ocr(self):
        with patch('windowwords.screen_recovery.ocr.read',return_value=(row('Water',x=2,y=2),)) as read:
            result=recover_labels(self.image,(),(self.old,),'raw','game','gpu')
        self.assertEqual(result,(self.old,));self.assertEqual(read.call_count,1)
        self.assertLess(read.call_args.args[0].width,250)

    def test_changed_word_or_number_is_never_guessed_as_previous_label(self):
        for text in ('Bread','Water 7','Walcr',''):
            with self.subTest(text=text),patch('windowwords.screen_recovery.ocr.read',return_value=(row(text),)):
                self.assertEqual(recover_labels(self.image,(),(self.old,),'raw','windows','cpu'),())

    def test_visible_label_and_adjacent_ui_do_not_trigger_unnecessary_ocr(self):
        lines=(self.old,row('Bread',y=200))
        with patch('windowwords.screen_recovery.ocr.read') as read:
            self.assertEqual(recover_labels(self.image,lines,(self.old,),'raw','game','gpu'),lines)
            read.assert_not_called()


class RecoveryBoundsTests(unittest.TestCase):
    def setUp(self):self.image=Image.new('RGB',(800,600));self.old=row('Water')
    def test_recovery_replaces_wrong_local_read_keeps_neighbour_and_limits_work(self):
        wrong=row('Walcr');neighbour=row('Bread',y=200)
        with patch('windowwords.screen_recovery.ocr.read',return_value=(row('Water'),)) as read:
            result=recover_labels(self.image,(wrong,neighbour),(self.old,row('Milk',y=300)),'raw','game','gpu',limit=1)
        self.assertEqual(result,(self.old,neighbour));self.assertEqual(read.call_count,1)

    def test_client_crop_offset_and_outside_box_are_safe(self):
        shifted=row('Water',x=420,y=280,w=100,h=20)
        with patch('windowwords.screen_recovery.ocr.read',return_value=(row('Water'),)) as read:
            result=recover_labels(Image.new('RGB',(200,120)),(),(shifted,),'raw','game','gpu',(400,250))
            self.assertEqual(result,(shifted,));self.assertLess(read.call_args.args[0].width,130)
            read.reset_mock()
            self.assertEqual(recover_labels(self.image,(),(row('Water',x=900),),'raw','game','gpu'),())
            read.assert_not_called()


class SceneTranslationTests(unittest.TestCase):
    def window(self):
        window=ScreenHarness();window.pump_screen=ScreenMode.pump_screen.__get__(window)
        window.translator=Mock();window.translator.translate_segments.return_value=['Старый текст']
        window.isMinimized=lambda:False
        window.screen_tracks.update((row('Old text'),),0,instant=True)
        return window

    def test_old_scene_request_cancels_without_stopping_new_translation(self):
        window=self.window();window.pump_screen();fn,done,failed=window.jobs[-1]
        fn();cancel=window.translator.translate_segments.call_args.kwargs['cancel']
        self.assertFalse(cancel())
        window.screen_tracks.update((row('New text',y=350),),2,instant=True)
        self.assertTrue(cancel())
        failed('Request cancelled')
        self.assertTrue(window.running);self.assertEqual(len(window.jobs),2)
        self.assertTrue(window.cloud_busy)

    def test_partial_hud_change_does_not_cancel_a_still_visible_batch(self):
        window=self.window();window.screen_tracks.update((row('Old text'),row('Gold 8',y=300)),0,instant=True)
        window.pump_screen();window.jobs[-1][0]();cancel=window.translator.translate_segments.call_args.kwargs['cancel']
        window.screen_tracks.update((row('Old text'),row('Gold 7',y=300)),2,instant=True)
        self.assertFalse(cancel())

    def test_actual_service_failure_on_current_scene_stops_translation(self):
        window=self.window();window.pump_screen();window.jobs[-1][2]('Service unavailable')
        self.assertFalse(window.running)


class AutoEscapeTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_auto_passes_escape_to_game_and_uses_toggle_to_stop(self):
        window=self.window;window.settings['screen_scope']='monitor';window.task=lambda *args:None
        window.keys.set_escape=Mock()
        window.start_screen(False)
        window.keys.set_escape.assert_called_with(False)
        window.on_hotkey('escape');self.assertTrue(window.running)
        window.on_hotkey('toggle');self.assertFalse(window.running)
        gate=EscapeGate(lambda action:self.fail('Escape must stay in the game'))
        self.assertFalse(gate.process(0x1B,0x100));self.assertFalse(gate.process(0x1B,0x101))

    def test_current_frame_and_dictionary_keep_escape_close(self):
        window=self.window;window.task=lambda *args:None;window.keys.set_escape=Mock()
        window.start_screen(True);window.keys.set_escape.assert_called_with(True)
        window.on_hotkey('escape');self.assertFalse(window.running)
        window.show_freeze(self.image(),window.monitor,'study');window.begin_session()
        window.on_hotkey('escape');self.assertIsNone(window.freeze);self.assertFalse(window.session_active)

    def image(self):return Image.new('RGB',(800,600))


if __name__=='__main__':unittest.main()
