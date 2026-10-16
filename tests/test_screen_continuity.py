"""Continuous reading, scene changes and delayed translation regressions."""
import sentencepiece,ctranslate2
import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from windowwords.core import Box,Line,normalized
from windowwords.screen import Tracker
from windowwords.screen_layout import layout
from windowwords.screen_text import measure_text
from tests.test_item_tooltips import tooltip_rows
from windowwords.screen import field_columns,blocks
from tests.test_capture_lifecycle import ScreenHarness


PROSE='The traveller reached the village before sunrise. He found a note from the guide about the missing girl.'
OTHER='The guide waited beside the northern gate. A guard approached him and asked for news from the capital.'
def row(text,box=Box(100,400,600,60)):return Line(text,box,())


class ContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_alternating_wrong_readings_never_replace_confirmed_caption(self):
        tracker=Tracker();tracker.update([row(PROSE)],0,True);tracker.remember([PROSE],['Перевод'])
        for index,text in enumerate([PROSE.replace('guide','guicle'),PROSE.replace('guide','quide')]*3,1):
            tracker.update([row(text)],index*.2)
            self.assertEqual(tracker.missing(),[])
            self.assertEqual([line.text for line,target in tracker.ready()],[PROSE])

    def test_pending_reading_restarts_after_empty_observation(self):
        tracker=Tracker();tracker.update([row('New subtitle')],0)
        tracker.update([], .2);tracker.update([row('New subtitle')],.4)
        self.assertEqual(tracker.missing(),[])
        tracker.update([row('New subtitle')],.8)
        self.assertEqual(tracker.missing(),['New subtitle'])

    def test_new_phrase_still_replaces_old_after_two_confirming_readings(self):
        tracker=Tracker();tracker.update([row(PROSE)],0,True);tracker.remember([PROSE],['Old'])
        tracker.update([row(OTHER)],.2);self.assertEqual(len(tracker.ready()),1)
        tracker.update([row(OTHER)],.6)
        self.assertEqual(tracker.ready(),());self.assertEqual(tracker.missing(),[OTHER])

    def test_common_hud_cannot_hold_old_prose_after_scene_change(self):
        tracker=Tracker();hud=row('Gold 10',Box(10,10,100,20))
        tracker.update([hud,row(PROSE)],0,True);tracker.remember(['Gold 10',PROSE],['Золото 10','Old'])
        incoming=[hud,row(OTHER,Box(100,100,600,80))]
        tracker.update(incoming,.1);tracker.update(incoming,.5)
        self.assertEqual({t.line.text for t in tracker.items},{'Gold 10',OTHER})
        self.assertEqual([line.text for line,target in tracker.ready()],['Gold 10'])

    def test_new_menu_clears_old_menu_even_with_same_hud(self):
        tracker=Tracker();hud=row('Gold 10',Box(10,10,100,20))
        old=[row(text,Box(100,100+i*70,120,24)) for i,text in enumerate(('Continue','Settings','Exit'))]
        new=[row(text,Box(400,100+i*70,120,24)) for i,text in enumerate(('Inventory','Journal','Character'))]
        tracker.update([hud]+old,0,True);tracker.remember([l.text for l in [hud]+old],['Old']*4)
        tracker.update([hud]+new,.1);tracker.update([hud]+new,.5)
        self.assertEqual({t.line.text for t in tracker.items},{'Gold 10','Inventory','Journal','Character'})

    def test_one_missing_hud_label_does_not_clear_the_whole_scene(self):
        tracker=Tracker();old=[row(text,Box(100,100+i*70,120,24)) for i,text in enumerate(('Inventory','Journal','Character'))]
        tracker.update(old,0,True);tracker.remember([l.text for l in old],['Old']*3)
        tracker.update(old[:2]+[row('Water 7',Box(500,400,100,24))],.1)
        tracker.update(old[:2]+[row('Water 7',Box(500,400,100,24))],.5)
        self.assertEqual(len(tracker.ready()),3)

    def test_source_width_jitter_keeps_panel_size_font_and_position(self):
        tracker=Tracker();original=row(PROSE)
        tracker.update([original],0,True);tracker.remember([PROSE],['Путешественник добрался до деревни и нашёл записку.'])
        first,_=layout([(line.box,text) for line,text in tracker.ready()],800,600,'replace',22,14,measure_text)
        for now,box in enumerate((Box(103,402,645,65),Box(98,399,570,56)),1):
            tracker.update([row(PROSE,box)],now)
            labels,_=layout([(line.box,text) for line,text in tracker.ready()],800,600,'replace',22,14,measure_text,previous=first)
            self.assertEqual(labels,first)

    def test_real_source_movement_is_not_frozen(self):
        tracker=Tracker();tracker.update([row(PROSE)],0,True)
        moved=row(PROSE,Box(120,420,600,60));tracker.update([moved],.4)
        self.assertEqual(tracker.items[0].line.box,moved.box)

    def test_cache_eviction_preserves_visible_translation(self):
        tracker=Tracker();tracker.update([row('Water')],0,True);tracker.remember(['Water'],['Вода'])
        texts=[f'Old phrase {i}' for i in range(2100)]
        tracker.remember(texts,texts)
        self.assertEqual(len(tracker.cache),2000)
        self.assertEqual(tracker.ready(),((row('Water'),'Вода'),))
        self.assertNotIn(normalized(texts[0]),tracker.cache)

    def test_late_item_fields_do_not_resize_the_visible_header(self):
        parts=blocks(tooltip_rows());fields=field_columns(parts)
        header=(parts[0].box,'Стёганка путешественника')
        first,_=layout([header],628,400,'replace',22,14,measure_text,[l.box for l in parts],fields=fields)
        later,_=layout([header,(parts[3].box,'+7% Сопротивление колющему урону')],628,400,'replace',22,14,measure_text,[l.box for l in parts],previous=first,fields=fields)
        self.assertEqual(later[0],first[0])

    def test_overlapping_detector_padding_does_not_remove_missing_property(self):
        rows=tooltip_rows();tracker=Tracker()
        tracker.update(rows,0,True);tracker.remember([l.text for l in rows],[l.text for l in rows])
        tracker.update(rows[:4]+rows[5:],.4)
        self.assertEqual(len(tracker.ready()),8)
        tracker.update(rows,.8)
        self.assertEqual(len(tracker.ready()),8);self.assertEqual(tracker.missing(),[])

    def test_delayed_batch_history_contains_only_still_visible_members(self):
        window=ScreenHarness();window.isMinimized=lambda:False
        window.translator=Mock();window.translator.translate_segments.return_value=['Золото','Old']
        hud=row('Gold 10',Box(10,10,100,20))
        window.screen_tracks.update([hud,row(PROSE)],0,True)
        window.pump_screen();done=window.jobs[-1][1]
        window.screen_tracks.update([hud,row(OTHER,Box(100,100,600,80))],.1)
        window.screen_tracks.update([hud,row(OTHER,Box(100,100,600,80))],.5)
        done(['Золото','Old'])
        self.assertEqual(window.history,[('Gold 10','Золото')])
        self.assertEqual(len(window.jobs),2)


if __name__=='__main__':unittest.main()
