import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch
from PIL import Image
from windowwords.core import Box,Line,Word
from windowwords.screen import without_metrics,blocks,Tracker
from windowwords import ocr


class MetricsTests(unittest.TestCase):
    def test_simple_and_detailed_performance_rows_are_ignored(self):
        for text in ('132 FPS','FPS 132','FPS: 132','132FPS','fps','Frame time: 7.4 ms',
                     'GPU: 94 %','CPU 31%','VRAM 6.2 GB','RAM: 12 GB','Ping: 40 ms',
                     'FPS 132 | GPU 96% | CPU 34%','FPS 132, Frame time 7.5 ms'):
            with self.subTest(text=text):
                self.assertEqual(without_metrics((Line(text,Box(10,10,180,14),()),)),())

    def test_regular_game_stats_and_headings_are_preserved(self):
        for text in ('NOON','MORNING','32 ARMOR +2','132 gold','Resistance to damage 30%',
                     'This runs at 60 FPS.','The CPU controls this door.','Use FPS mode'):
            with self.subTest(text=text):
                line=Line(text,Box(10,10,280,22),())
                self.assertEqual(without_metrics((line,)),(line,))

    def test_merged_fps_and_heading_keep_only_heading_words_and_bounds(self):
        words=(Word('132',Box(790,29,24,11)),Word('FPS',Box(820,29,25,11)),Word('NOON',Box(556,84,88,25)))
        line=Line('132 FPS NOON',Box(556,29,289,80),words)
        result=without_metrics((line,))
        self.assertEqual(len(result),1);self.assertEqual(result[0].text,'NOON')
        self.assertEqual(result[0].box,words[-1].box)
        self.assertEqual(result[0].words,(words[-1],))

    def test_far_apart_same_height_metric_and_game_words_are_separated(self):
        words=(Word('NOON',Box(556,30,88,20)),Word('132',Box(790,30,24,20)),Word('FPS',Box(820,30,25,20)))
        result=without_metrics((Line('NOON 132 FPS',Box(556,30,289,20),words),))
        self.assertEqual(result[0].text,'NOON');self.assertEqual(result[0].box,words[0].box)

    def test_fps_in_a_normal_sentence_is_not_removed(self):
        words=tuple(Word(text,Box(50+i*40,560,36,20)) for i,text in enumerate(('This','runs','at','60','FPS')))
        line=Line('This runs at 60 FPS',Box(50,560,196,20),words)
        self.assertEqual(without_metrics((line,)),(line,))

    def test_fps_with_ocr_word_geometry_is_completely_removed(self):
        words=(Word('132',Box(790,29,24,11)),Word('FPS',Box(820,29,25,11)))
        self.assertEqual(without_metrics((Line('132 FPS',Box(790,29,55,11),words),)),())

    def test_counter_never_enters_translation_or_layout(self):
        rows=(Line('132 FPS',Box(790,29,55,11),()),Line('NOON',Box(556,84,88,25),()))
        tracker=Tracker();tracker.update(rows,0,instant=True)
        self.assertEqual(tracker.missing(),['NOON']);tracker.remember(['NOON'],['Полдень'])
        self.assertEqual(len(tracker.ready()),1);self.assertEqual(blocks(rows)[0].text,'NOON')

    def test_every_read_profile_filters_before_word_selection(self):
        rows=(Line('132 FPS',Box(790,29,55,11),()),Line('NOON',Box(556,84,88,25),()))
        async def recognized(*args):return rows
        for profile in ('raw','white','yellow','small'):
            with self.subTest(profile=profile),patch.object(ocr,'recognize',side_effect=recognized):
                self.assertEqual(ocr.read(Image.new('RGB',(900,300)),profile),(rows[1],))
