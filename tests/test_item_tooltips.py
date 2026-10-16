import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from windowwords.core import Box,Line
from windowwords.screen import blocks,field_columns,intersects
from windowwords.screen_layout import layout
from windowwords.screen_text import measure_text,wrapped_text
from windowwords.screen_overlay import ScreenOverlay


def tooltip_rows():
    values=(('TRAVELLER GAMBESON',25,18,250,28),('LIGHT ARMOR',22,55,159,31),('24 ARMOR -6',21,97,214,37),
            ('+7 % Resistance to piercing damage.',34,159,428,38),('+10 % Resistance to bludgeoning damage',28,193,479,36),
            ('+15 % Resistance to slashing damage.',20,229,447,38),('Common item',21,274,151,31),('Required Level 1',24,315,181,31))
    return tuple(Line(text,Box(x,y,w,h),()) for text,x,y,w,h in values)


class ItemTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_title_type_stats_and_requirements_are_eight_separate_fields(self):
        rows=tooltip_rows();parts=blocks(rows)
        self.assertEqual([part.text for part in parts],[row.text for row in rows])
        self.assertTrue(all('\n' not in part.text for part in parts))

    def test_wrapped_property_keeps_its_own_continuation(self):
        rows=(Line('+7% Resistance to piercing',Box(20,100,300,30),()),
              Line('damage',Box(112,132,116,30),()),Line('+10% Resistance to bludgeoning',Box(20,164,300,30),()),
              Line('damage',Box(112,196,116,30),()))
        parts=blocks(rows)
        self.assertEqual(len(parts),2)
        self.assertEqual(parts[0].text,'+7% Resistance to piercing\ndamage')

    def test_a_single_percentage_in_normal_prose_is_not_a_stat_table(self):
        rows=(Line('Only 50% of the travellers returned',Box(20,100,300,24),()),
              Line('to the village before sunrise and',Box(20,130,300,24),()),
              Line('the guide waited at the northern gate.',Box(20,160,300,24),()))
        self.assertEqual(len(blocks(rows)),1);self.assertEqual(field_columns(rows),{})

    def test_column_does_not_include_nearby_icons_or_another_text_column(self):
        rows=tooltip_rows();other=Line('Pocket',Box(560,320,60,25),())
        fields=field_columns(rows+(other,))
        self.assertEqual(len(fields),8);self.assertNotIn(other.box,fields)
        self.assertEqual(len(set(fields.values())),1)

    def test_replacement_is_aligned_and_does_not_mask_item_preview_or_values(self):
        parts=blocks(tooltip_rows());fields=field_columns(parts)
        texts=('Стёганка путешественника','Лёгкая броня','24 брони · −6','+7% Сопротивление колющему урону',
               '+10% Сопротивление дробящему урону','+15% Сопротивление рубящему урону','Обычный предмет','Требуется уровень 1')
        entries=[(line.box,text) for line,text in zip(parts,texts)]
        labels,skipped=layout(entries,628,400,'replace',22,14,measure_text,[p.box for p in parts],fields=fields)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),8)
        self.assertEqual(len({label.size for label in labels}),1)
        self.assertEqual(len({label.box.x for label in labels}),1)
        icon=Box(540,25,60,80);values=Box(20,354,215,32)
        for label in labels:
            self.assertLess(label.box.h,60)
            self.assertGreaterEqual(label.box.x+label.box.w,label.source.x+label.source.w)
            self.assertFalse(intersects(label.box,icon));self.assertFalse(intersects(label.box,values))
            self.assertLessEqual(wrapped_text(label.text,label.size,label.box.w-8)[1],label.box.h-6)
        self.assertTrue(all(not intersects(a.box,b.box) for i,a in enumerate(labels) for b in labels[i+1:]))

    def test_late_translations_keep_headers_anchored_to_the_column(self):
        parts=blocks(tooltip_rows());fields=field_columns(parts)
        first=(parts[0].box,'Стёганка путешественника')
        initial,_=layout([first],628,400,'replace',22,14,measure_text,[p.box for p in parts],fields=fields)
        next_entries=[first,(parts[3].box,'+7% Сопротивление колющему урону')]
        later,_=layout(next_entries,628,400,'replace',22,14,measure_text,[p.box for p in parts],previous=initial,fields=fields)
        self.assertEqual(initial[0].box.x,later[0].box.x)
        self.assertEqual(initial[0].box.y,later[0].box.y)

    def test_overlay_restores_field_column_in_client_coordinates_on_another_monitor(self):
        parts=blocks(tooltip_rows());region=Box(-2560,120,2560,1440);bounds=Box(-2100,500,628,400)
        shifted=tuple(Line(part.text,Box(part.box.x+460,part.box.y+380,part.box.w,part.box.h),()) for part in parts)
        translated=('Стёганка','Лёгкая броня','24 брони · −6','+7% Колющий урон','+10% Дробящий урон','+15% Рубящий урон','Обычный предмет','Уровень 1')
        widget=ScreenOverlay();settings={'screen_mode':'replace','font_size':22,'offset':14}
        try:
            with patch.object(widget,'show'),patch('windowwords.screen_overlay.native.place'),patch('windowwords.screen_overlay.native.exclude_capture',return_value=True):
                skipped=widget.display_segments(list(zip(shifted,translated)),region,{'x':-2560,'y':120,'w':2560,'h':1440},settings,shifted,bounds)
            scale=widget.devicePixelRatioF()
            expected,_=layout([(p.box,t) for p,t in zip(parts,translated)],628,400,'replace',22*scale,14*scale,measure_text,[p.box for p in parts],fields=field_columns(parts))
            self.assertEqual(skipped,0);self.assertEqual(widget.labels,expected)
        finally:
            widget.close();widget.deleteLater();self.app.sendPostedEvents(None,QEvent.Type.DeferredDelete)


if __name__=='__main__':unittest.main()
