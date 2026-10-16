import sentencepiece,ctranslate2
import unittest
from PySide6.QtWidgets import QApplication
from windowwords.core import Box,Line
from windowwords.screen import field_columns,intersects,protected_lines
from windowwords.screen_layout import layout,Label
from windowwords.screen_text import measure_text,wrapped_text


class AboveGroupsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def assert_safe(self,labels,sources,width,height):
        for label in labels:
            self.assertGreaterEqual(label.box.x,0);self.assertGreaterEqual(label.box.y,0)
            self.assertLessEqual(label.box.x+label.box.w,width);self.assertLessEqual(label.box.y+label.box.h,height)
            self.assertTrue(all(not intersects(label.box,source,1) for source in sources))
            self.assertLessEqual(wrapped_text(label.text,label.size,label.box.w-8)[1],label.box.h-6)
            self.assertTrue(all(measure_text(word,label.size,width)[0]<=label.box.w-8 for word in label.text.split()))
        self.assertTrue(all(not intersects(a.box,b.box) for i,a in enumerate(labels) for b in labels[i+1:]))

    def test_dense_list_at_right_edge_prefers_free_space_below_without_letter_wrapping(self):
        sources=[Box(1650,190+i*50,250,27) for i in range(8)]
        texts=['История Меган','История Джессики','История Элизабет','История Зои','История Элли','История Николь','История Софи','История Эми']
        labels,skipped=layout(list(zip(sources,texts)),1920,1080,'above',22,14,measure_text,sources)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),8)
        self.assertEqual({l.placement for l in labels},{'group-below'})
        self.assertEqual(len({l.box.x for l in labels}),1)
        self.assertEqual({l.size for l in labels},{22})
        self.assert_safe(labels,sources,1920,1080)

    def test_inventory_characteristics_stay_in_one_column_in_source_order(self):
        rows=[Line(t,Box(930,530+i*40,500,30),()) for i,t in enumerate(('ARD SKELLIG AKETON','LIGHT ARMOR','32 ARMOR +2',
              '+30% Resistance to bludgeoning damage','+30% Resistance to slashing damage','+3% Resistance to elemental damage','Empty','Master Item','Required Level 1'))]
        fields=field_columns(rows);sources=[r.box for r in rows]
        texts=['Акетон Ард Скеллиге','Лёгкая броня','32 брони · +2','+30% Сопротивление дробящему урону',
               '+30% Сопротивление рубящему урону','+3% Сопротивление стихиям','Пусто','Мастерский предмет','Требуется уровень 1']
        # Other captions above the item prevent an unrelated floating block.
        blockers=[Box(930,280,500,240)]
        labels,skipped=layout(list(zip(sources,texts)),2560,1440,'above',22,14,measure_text,sources+blockers,fields=fields)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),9)
        self.assertEqual(len({l.box.x for l in labels}),1)
        self.assertEqual(len({l.placement for l in labels}),1)
        self.assertEqual([l.text for l in sorted(labels,key=lambda l:l.box.y)],texts)
        self.assert_safe(labels,sources+blockers,2560,1440)

    def test_group_uses_whole_words_when_one_side_is_too_narrow(self):
        sources=[Box(500,160+i*38,100,23) for i in range(4)]
        entries=list(zip(sources,['Снаряжение','Характеристики','Инвентарь','Настройки']))
        labels,skipped=layout(entries,640,480,'above',22,14,measure_text,sources)
        self.assertEqual(skipped,0);self.assertEqual({l.placement for l in labels},{'group-above'})
        self.assert_safe(labels,sources,640,480)

    def test_no_space_reports_a_group_without_scattering_or_covering_original(self):
        sources=[Box(10,20+i*35,180,25) for i in range(5)]
        labels,skipped=layout([(s,'Длинная характеристика предмета') for s in sources],200,200,'above',22,14,measure_text,sources)
        self.assertEqual(labels,());self.assertEqual(skipped,5)

    def test_late_translation_keeps_existing_group_side_and_position(self):
        sources=[Box(500,160+i*38,100,23) for i in range(4)]
        entries=list(zip(sources,['Снаряжение','Характеристики','Инвентарь','Настройки']))
        first,_=layout(entries[:1],800,600,'above',22,14,measure_text,sources)
        later,_=layout(entries,800,600,'above',22,14,measure_text,sources,previous=first)
        self.assertEqual(first[0],later[0])

    def test_single_label_at_edge_never_turns_into_a_column_of_letters(self):
        source=Box(1880,160,30,25)
        labels,skipped=layout([(source,'История Меган')],1920,1080,'above',22,14,measure_text,[source])
        self.assertEqual(skipped,0);self.assert_safe(labels,[source],1920,1080)

    def test_new_group_does_not_overlap_an_old_pinned_neighbour(self):
        sources=[Box(500,300+i*40,100,25) for i in range(4)]
        neighbour=Box(900,340,100,24)
        entries=[(s,'Снаряжение') for s in sources]+[(neighbour,'Соседняя надпись')]
        previous=[Label(neighbour,Box(630,340,190,36),'Соседняя надпись',22,'left')]
        labels,skipped=layout(entries,1100,700,'above',22,14,measure_text,sources+[neighbour],previous=previous)
        self.assertEqual(skipped,0);self.assert_safe(labels,sources+[neighbour],1100,700)

    def test_numeric_values_and_key_icons_are_protected_without_translating_them(self):
        lines=[Line('24 Armor',Box(10,20,100,25),()),Line('100%',Box(200,200,50,25),()),
               Line('[E]',Box(300,200,30,25),()),Line('293 FPS',Box(600,10,100,20),())]
        self.assertEqual(protected_lines(lines),tuple(lines[1:]))

    def test_story_list_stays_grouped_in_a_small_game_window(self):
        sources=[Box(430,150+i*45,210,30) for i in range(8)]
        labels,skipped=layout([(s,'История Джессики') for s in sources],652,600,'above',22,14,measure_text,sources)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),8)
        self.assertEqual({l.placement for l in labels},{'group-left'})
        self.assertEqual(len({l.box.x for l in labels}),1)
        self.assert_safe(labels,sources,652,600)


if __name__=='__main__':unittest.main()
