"""Regression scenarios from moving backgrounds, dense menus and late batches."""
import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from windowwords.core import Box,Line
from windowwords.screen import Tracker,same_text,intersects
from windowwords.screen_layout import layout
from windowwords.screen_text import measure_text
from windowwords import game_ocr
from windowwords.screen_recovery import recover_labels,tracked_subtitle
from tests.test_capture_lifecycle import ScreenHarness


PROSE=('The traveller reached the northern village before sunrise. '
       'He found a note from the guide, who had left to gather information about the missing girl.')
def row(text,box=Box(280,820,1300,90)):return Line(text,box,())
def polygon(box):return [[box.x,box.y],[box.x+box.w,box.y],[box.x+box.w,box.y+box.h],[box.x,box.y+box.h]]


class TrackingReadabilityTests(unittest.TestCase):
    def test_punctuation_and_spaces_do_not_restart_long_prose_translation(self):
        tracker=Tracker();tracker.update([row(PROSE)],0,True);tracker.remember([PROSE],['Перевод всей фразы'])
        variants=[PROSE.replace('. He','.He'),PROSE.replace('guide,','guide'),PROSE+' .']
        for now,text in enumerate(variants,1):
            tracker.update([row(text,Box(282,821,1310,89))],now)
            self.assertEqual(len(tracker.items),1);self.assertEqual(tracker.missing(),[])
            self.assertEqual(tracker.ready(),((row(PROSE),'Перевод всей фразы'),))

    def test_new_word_number_or_short_choice_punctuation_remains_a_new_text(self):
        for first,second in ((PROSE,PROSE.replace('sunrise','midnight')),
                             (PROSE+' He had 10 coins.',PROSE+' He had 11 coins.'),
                             (PROSE+' Wait 1.5 seconds.',PROSE+' Wait 15 seconds.'),
                             (PROSE+' Read CodeGold2.0.',PROSE+' Read CodeGold20.'),
                             (PROSE+' Take 1-5 coins.',PROSE+' Take 15 coins.'),('Open?','Open!')):
            self.assertFalse(same_text(first,second))
            tracker=Tracker();tracker.update([row(first)],0,True);tracker.remember([first],['Old'])
            tracker.update([row(second)],.4);tracker.update([row(second)],.8)
            self.assertEqual(tracker.ready(),());self.assertEqual(tracker.missing(),[second])

    def test_partial_paragraph_does_not_split_panel_or_extend_old_lifetime(self):
        tracker=Tracker();tracker.update([row(PROSE)],0,True);tracker.remember([PROSE],['Complete'])
        part=PROSE[PROSE.index('He found'):]
        partial=row(part,Box(280,850,1200,60))
        tracker.update([partial],.4);tracker.update([partial],1.0)
        self.assertEqual(tracker.ready(),((row(PROSE),'Complete'),));self.assertEqual(len(tracker.items),1)
        tracker.update([partial],1.6)
        self.assertEqual(tracker.ready(),());self.assertEqual(len(tracker.items),1)

    def test_new_prose_scene_clears_a_menu_before_grace_timeout(self):
        tracker=Tracker();menu=[row(text,Box(280,100+i*70,120,24)) for i,text in enumerate(('Start','Settings','Exit'))]
        tracker.update(menu,0,True);tracker.remember([l.text for l in menu],['Начать','Настройки','Выход'])
        tracker.update([row(PROSE)],.1);tracker.update([row(PROSE)],.4)
        self.assertEqual([t.line.text for t in tracker.items],[PROSE]);self.assertEqual(tracker.ready(),())

    def test_same_text_in_distant_location_does_not_steal_existing_track(self):
        tracker=Tracker();tracker.update([row('Open',Box(10,10,60,20))],0,True)
        old=tracker.items[0].id
        tracker.update([row('Open',Box(500,300,60,20))],.2)
        self.assertEqual(len(tracker.items),2);self.assertEqual(tracker.items[0].id,old)
        self.assertEqual(tracker.items[0].line.box,Box(10,10,60,20))


class GeometryReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_last_word_ctc_padding_is_limited_by_the_detector(self):
        box=Box(275,822,1341,32);word=Box(1579,822,161,32)
        result=game_ocr.convert([[polygon(box),'had.',.99,[polygon(word)],['had.'],[.99]]],1920,1080)
        self.assertEqual(result[0].words[0].box,Box(1579,822,37,32))
        self.assertLessEqual(result[0].words[0].box.x+result[0].words[0].box.w,box.x+box.w)

    def test_invalid_word_alignment_keeps_the_whole_decoded_text(self):
        box=Box(10,10,100,20)
        result=game_ocr.convert([[polygon(box),'Hello world',.99,[polygon(Box(10,10,40,20)),polygon(Box(160,10,40,20))],['Hello','world'],[.99,.99]]],300,100)
        self.assertEqual([w.text for w in result[0].words],['Hello world'])
        self.assertEqual(result[0].words[0].box,box)

    def test_dense_menu_uses_one_compact_aligned_column(self):
        entries=[(Box(280+i%2*3,370+i*43,100,27),text) for i,text in enumerate(('Продолжить','Новая игра','Загрузить игру','Настройки','Модификации','Авторы','Выход'))]
        labels,skipped=layout(entries,1920,1080,'above',22,14,measure_text)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),len(entries))
        self.assertEqual({label.placement for label in labels},{'group-above'})
        self.assertEqual(len({label.box.x for label in labels}),1)
        self.assertEqual({label.size for label in labels},{22})
        for label in labels:self.assertLess(label.box.w,260)

    def test_short_side_fallback_does_not_allocate_a_paragraph_sized_strip(self):
        labels,skipped=layout([(Box(1050,300,85,22),'Серебряный меч')],1920,1080,'above',22,14,measure_text,[Box(1040,210,120,88)])
        self.assertEqual(skipped,0);self.assertLess(labels[0].box.w,220)

    def test_late_batch_keeps_valid_caption_geometry_and_font(self):
        entry=(Box(100,200,100,20),'Открыть меню')
        first,_=layout([entry],800,600,'above',22,14,measure_text)
        second=(Box(300,205,90,20),'Закрыть')
        labels,_=layout([entry,second],800,600,'above',22,14,measure_text,previous=first)
        self.assertEqual(next(l for l in labels if l.source==entry[0]),first[0])

    def test_pinned_caption_reflows_when_new_source_would_be_obscured(self):
        entry=(Box(100,200,100,20),'Открыть меню')
        first,_=layout([entry],800,600,'above',22,14,measure_text)
        obstruction=first[0].box
        labels,_=layout([entry],800,600,'above',22,14,measure_text,[obstruction],first)
        self.assertTrue(all(not intersects(l.box,obstruction,1) for l in labels))


class ProseRecoveryTests(unittest.TestCase):
    def test_a_missing_complete_subtitle_can_be_verified_in_a_fresh_crop(self):
        image=Image.new('RGB',(1920,1080));old=row(PROSE)
        with patch('windowwords.screen_recovery.ocr.read',return_value=(row(PROSE.replace('. He','.He'),Box(5,5,1300,90)),)) as read:
            result=recover_labels(image,(),(old,),'raw','game','gpu')
        self.assertEqual(result,(old,));self.assertEqual(read.call_count,1)

    def test_long_caption_recovery_rejects_a_changed_word_or_number(self):
        image=Image.new('RGB',(1920,1080));old=row(PROSE+' He had 10 coins.')
        for text in (old.text.replace('10','11'),old.text.replace('sunrise','midnight')):
            with self.subTest(text=text),patch('windowwords.screen_recovery.ocr.read',return_value=(row(text),)):
                self.assertEqual(recover_labels(image,(),(old,),'raw','game','gpu'),())

    def test_visible_multiline_prose_does_not_repeat_local_ocr(self):
        old=row(PROSE,Box(100,100,800,60));first,second=PROSE.split('. ',1)
        lines=(row(first+'.',Box(100,100,800,24)),row(second,Box(100,130,800,24)))
        with patch('windowwords.screen_recovery.ocr.read') as read:
            self.assertEqual(recover_labels(Image.new('RGB',(1920,1080)),lines,(old,),'raw','game','gpu'),lines)
            read.assert_not_called()

    def test_tracked_subtitle_requires_fresh_complete_text_and_rejects_changes(self):
        old=row(PROSE);image=Image.new('RGB',(1920,1080))
        for text,expected in ((PROSE,(old,)),(PROSE.replace('sunrise','midnight'),None),(PROSE[:70],None)):
            with self.subTest(text=text),patch('windowwords.screen_recovery.ocr.read',return_value=(row(text),)):
                self.assertEqual(tracked_subtitle(image,(old,),'raw','game','gpu'),expected)
        with patch('windowwords.screen_recovery.ocr.read') as read:
            self.assertIsNone(tracked_subtitle(image,(old,row('Exit',Box(10,10,80,20))),'raw','game','gpu'))
            read.assert_not_called()

    def test_obvious_new_scene_does_not_spend_work_on_old_menu_crops(self):
        old=tuple(row(text,Box(100,100+i*70,120,20)) for i,text in enumerate(('Start','Settings','Exit')))
        with patch('windowwords.screen_recovery.ocr.read') as read:
            incoming=(row(PROSE),)
            self.assertEqual(recover_labels(Image.new('RGB',(1920,1080)),incoming,old,'raw','game','gpu'),incoming)
            read.assert_not_called()


class SubtitleScanTests(unittest.TestCase):
    def window(self):
        window=ScreenHarness();window.capture_image.return_value=Image.new('RGB',(800,600))
        old=row(PROSE,Box(100,400,600,60));window.screen_tracks.update((old,),0,True)
        window.screen_full_scan=((window.epoch.value,Box(0,0,800,600),Box(0,0,800,600),'raw','windows','gpu'),0)
        return window,old

    def test_verified_subtitle_uses_local_read_between_full_scans(self):
        window,old=self.window()
        with patch('windowwords.screen_mode.time.monotonic',return_value=.4),patch('windowwords.screen_recovery.tracked_subtitle',return_value=(old,)) as local,patch('windowwords.screen_mode.ocr.read') as full:
            window.tick();fn,done,failed=window.jobs.pop();done(fn())
            full.assert_not_called();local.assert_called_once();self.assertEqual(window.lines,(old,))

    def test_periodic_scan_and_changed_subtitle_always_use_full_detector(self):
        for now,local_result in ((.8,None),(.4,None)):
            window,old=self.window()
            with self.subTest(now=now),patch('windowwords.screen_mode.time.monotonic',return_value=now),patch('windowwords.screen_recovery.tracked_subtitle',return_value=local_result),patch('windowwords.screen_mode.ocr.read',return_value=(old,)) as full:
                window.tick();fn,done,failed=window.jobs.pop();done(fn());full.assert_called_once()

    def test_snapshot_does_not_take_the_local_subtitle_shortcut(self):
        window,old=self.window();window.screen_snapshot=True;window.screen_loaded=False
        with patch('windowwords.screen_mode.time.monotonic',return_value=.4),patch('windowwords.screen_recovery.tracked_subtitle') as local,patch('windowwords.screen_mode.ocr.read',return_value=(old,)) as full:
            window.tick();fn,done,failed=window.jobs.pop();done(fn());full.assert_called_once();local.assert_not_called()


if __name__=='__main__':unittest.main()
