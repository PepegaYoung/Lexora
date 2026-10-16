import sentencepiece,ctranslate2
import unittest
from PySide6.QtWidgets import QApplication
from windowwords.core import Box,Line,Word
from windowwords.screen import blocks,Tracker,intersects
from windowwords.screen_layout import layout
from windowwords.screen_text import measure_text,wrapped_text


def rows():
    texts=('For someone who is ready','to continue the journey',
           'the adventure begins here','with a map and a quiet guide.',
           'We can take the shorter path','or follow the river today.',
           'She will meet us by the gate','and bring a lantern along.',
           'Remember to collect supplies','before leaving the village.',
           'The route is marked clearly','on the map beside the bridge.')
    return tuple(Line(text,Box(65+(i%3-1)*.6,190+i*28,180+(i%4)*26,15.6 if i<2 else 20),())
                 for i,text in enumerate(texts))


class ParagraphBlocksTests(unittest.TestCase):
    def test_variable_glyph_heights_and_new_sentences_form_one_paragraph(self):
        original=rows();result=blocks(original)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].text,'\n'.join(line.text for line in original))
        self.assertEqual(result[0].box.y,190)
        self.assertEqual(result[0].text.count('\n'),11)

    def test_headings_and_other_columns_stay_separate(self):
        original=rows()+(Line('MORNING',Box(138,92,116,20),()),
                         Line('Journey',Box(65,140,190,24),()),
                         Line('Coins',Box(410,245,50,20),()))
        result=blocks(original)
        self.assertEqual(len(result),4)
        self.assertEqual([l.text for l in result if '\n' not in l.text],['MORNING','Journey','Coins'])

    def test_row_with_only_short_lowercase_glyphs_keeps_its_neighbours(self):
        original=list(rows());row=original[1]
        original[1]=Line(row.text,Box(row.box.x,row.box.y+3,row.box.w,11.8),())
        self.assertEqual(len(blocks(original)),1)

    def test_blank_gap_separates_two_paragraphs(self):
        first=rows()[:3]
        second=tuple(Line(line.text,Box(line.box.x,line.box.y+110,line.box.w,line.box.h),()) for line in rows()[3:6])
        result=blocks(first+second)
        self.assertEqual(len(result),2)

    def test_numbered_choices_and_short_button_labels_do_not_merge(self):
        for texts in (('1. Open the door','2. Follow the river','3. Return to town'),
                      ('New game','Load game','Settings','Exit')):
            original=[Line(text,Box(65,190+i*28,180,20),()) for i,text in enumerate(texts)]
            self.assertEqual(len(blocks(original)),len(texts))

    def test_adjacent_columns_remain_independent_paragraphs(self):
        first=rows()[:3]
        second=tuple(Line(line.text,Box(line.box.x+340,line.box.y,line.box.w,line.box.h),()) for line in first)
        result=blocks(first+second)
        self.assertEqual(len(result),2)
        self.assertEqual([line.text.count('\n') for line in result],[2,2])

    def test_different_font_sizes_are_not_part_of_same_paragraph(self):
        original=rows()[:3]+(Line('SMALL FOOTNOTE',Box(65,272,180,9),()),)
        result=blocks(original)
        self.assertEqual(len(result),2)

    def test_tracker_requests_and_draws_one_complete_translation(self):
        tracker=Tracker();tracker.update(rows(),0);tracker.update(rows(),.4)
        self.assertEqual(len(tracker.missing()),1)
        tracker.remember(tracker.missing(),['Полный перевод абзаца.'])
        self.assertEqual(len(tracker.ready()),1)
        tracker.update(rows(),.8);self.assertEqual(tracker.missing(),[])

    def test_new_complete_paragraph_removes_previous_partial_panels(self):
        tracker=Tracker();tracker.update(rows()[:2],0,instant=True)
        old=tracker.missing();tracker.remember(old,['Начало абзаца.'])
        tracker.update(rows(),.1);tracker.update(rows(),.5)
        self.assertEqual(tracker.ready(),())
        tracker.remember(tracker.missing(),['Полный перевод.'])
        self.assertEqual(len(tracker.ready()),1)

    def test_all_ocr_words_survive_grouping(self):
        original=tuple(Line(line.text,line.box,(Word(line.text,line.box),)) for line in rows())
        result=blocks(original)
        self.assertEqual(result[0].words,tuple(word for line in original for word in line.words))


class ParagraphLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_single_line_glyph_bounds_do_not_force_tiny_heading(self):
        labels,skipped=layout([(Box(138,92,116,20),'Утро')],356,598,'replace',22,14,measure_text)
        self.assertEqual(skipped,0);self.assertEqual(labels[0].size,22)

    def test_grouped_column_gets_one_readable_panel_in_place(self):
        paragraph=blocks(rows())[0]
        text=('Мы готовы продолжить путешествие. Приключение начинается здесь: нас ждут карта и проводник. '
              'Можно выбрать короткую дорогу или идти вдоль реки. Нас встретят у ворот с фонарём. '
              'Не забудь собрать припасы перед выходом из деревни. Путь отмечен на карте возле моста.')
        entries=[(Box(138,92,116,20),'Утро'),(Box(65,140,190,24),'Путешествие'),(paragraph.box,text)]
        labels,skipped=layout(entries,356,598,'replace',22,14,measure_text)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),3)
        body=labels[-1];self.assertGreaterEqual(body.size,18)
        self.assertAlmostEqual(body.box.x,paragraph.box.x-3)
        self.assertAlmostEqual(body.box.y,paragraph.box.y-3)
        self.assertLessEqual(body.box.x+body.box.w,356)
        self.assertLessEqual(body.box.y+body.box.h,598)
        self.assertLessEqual(wrapped_text(text,body.size,body.box.w-8)[1],body.box.h-8)
        self.assertFalse(any(intersects(a.box,b.box) for i,a in enumerate(labels) for b in labels[i+1:]))
