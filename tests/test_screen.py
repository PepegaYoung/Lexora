import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from windowwords.core import Box,Line,Word
from windowwords.screen import Tracker,blocks,intersects
from windowwords.screen_layout import layout
from windowwords.translation import parse_segments,response_body,Translator
from windowwords.auth import ServiceError
from windowwords.storage import Store


def line(text,y=200,x=100,w=300,h=25):return Line(text,Box(x,y,w,h),())
def measure(text,size,width):
    import math
    return len(text)*size*.5,max(size,math.ceil(len(text)*size*.5/max(1,width))*size)


class ScreenTests(unittest.TestCase):
    def test_hud_change_does_not_cancel_stable_dialogue(self):
        tracker=Tracker()
        tracker.update([line('Maybe they missed something.'),line('Gold 20',50)],0)
        tracker.update([line('Maybe they missed something.'),line('Gold 21',50)],.4)
        self.assertEqual(tracker.missing(),['Maybe they missed something.'])
        tracker.remember(tracker.missing(),['Может быть, они что-то упустили.'])
        tracker.update([line('Maybe they missed something.'),line('Gold 22',50)],.8)
        self.assertEqual(len(tracker.ready()),1)
        self.assertEqual(tracker.missing(),[])

    def test_dropouts_and_stale_replies_are_not_drawn(self):
        tracker=Tracker()
        old='old phrase';new='new phrase'
        tracker.update([line(old)],0,True)
        tracker.remember([old],['старое'])
        tracker.update([],.5)
        self.assertEqual(len(tracker.ready()),1)
        tracker.update([line(new)],.6)
        tracker.update([line(new)],1.0)
        self.assertEqual(tracker.ready(),())
        tracker.remember([old],['поздний старый ответ'])
        self.assertEqual(tracker.ready(),())
        tracker.remember([new],['новое'])
        self.assertEqual(tracker.ready()[0][1],'новое')

    def test_duplicate_text_is_requested_once_but_drawn_twice(self):
        tracker=Tracker()
        tracker.update([line('Open',100),line('Open',300)],0,True)
        self.assertEqual(tracker.missing(),['Open'])
        tracker.remember(['Open'],['Открыть'])
        self.assertEqual(len(tracker.ready()),2)

    def test_returning_cached_text_needs_no_second_translation(self):
        tracker=Tracker()
        tracker.update([line('Hello')],0,True)
        tracker.remember(['Hello'],['Привет'])
        tracker.update([],1)
        tracker.update([line('Hello')],2,True)
        self.assertEqual(tracker.missing(),[])
        self.assertEqual(len(tracker.ready()),1)

    def test_numbers_and_wrapped_paragraphs_keep_identity(self):
        self.assertEqual(len(blocks([line('1. First',100),line('2. second',130)])),2)
        wrapped=blocks([line('An unfinished',100),line('sentence continues',130)])
        self.assertEqual(len(wrapped),1)
        self.assertEqual(wrapped[0].box,Box(100,100,300,55))

    def test_distant_columns_split(self):
        words=(Word('Open',Box(0,0,50,20)),Word('Menu',Box(400,0,50,20)))
        self.assertEqual(len(blocks([Line('Open Menu',Box(0,0,450,20),words)])),2)

    def test_above_never_covers_english_or_another_translation(self):
        entries=[(Box(100,180+i*55,280,25),'Вариант ответа номер '+str(i)) for i in range(4)]
        labels,skipped=layout(entries,800,600,'above',22,8,measure)
        self.assertEqual(skipped,0)
        for a in labels:
            self.assertLessEqual(a.box.y+a.box.h,a.source.y)
            self.assertTrue(all(not intersects(a.box,b) for b,t in entries))
            self.assertTrue(all(a is b or not intersects(a.box,b.box) for b in labels))

    def test_top_edge_has_no_fake_above_translation(self):
        labels,skipped=layout([(Box(100,1,100,20),'Привет')],800,600,'above',22,8,measure)
        self.assertEqual(labels,());self.assertEqual(skipped,1)

    def test_monitor_edges_and_replacement_cover_original(self):
        source=Box(720,570,70,20)
        labels,skipped=layout([(source,'Открыть меню')],800,600,'replace',22,8,measure)
        self.assertEqual(skipped,0)
        target=labels[0].box
        self.assertLessEqual(target.x+target.w,800)
        self.assertLessEqual(target.y+target.h,600)
        self.assertLessEqual(target.x,source.x)
        self.assertGreaterEqual(target.x+target.w,source.x+source.w)

    def test_gpt_ids_reordered_safely_and_invalid_rejected(self):
        self.assertEqual(parse_segments(json.dumps({'translations':[{'id':1,'text':'два'},{'id':0,'text':'один'}]}),2),('один','два'))
        for rows in ([{'id':0,'text':'a'},{'id':0,'text':'b'}],[{'id':True,'text':'a'}],[{'id':3,'text':'a'}],[{'id':0,'text':''}]):
            with self.assertRaises(ServiceError):parse_segments(json.dumps({'translations':rows}),len(rows))
        body=response_body('api','gpt-6.1-sol','ignored',[],segments=['Hello','Open'])
        self.assertEqual(json.loads(body['input'][0]['content'])['segments'][1]['id'],1)

    def test_classical_merged_lines_fall_back_to_individual(self):
        translator=Translator(None,None)
        translator.translate=Mock(side_effect=[('merged','mock'),('один','mock'),('два','mock')])
        self.assertEqual(translator.translate_segments({'provider':'libre'},['one','two']),('один','два'))

    def test_old_settings_gain_new_hotkey_and_background(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path))
            (Path(path)/'settings.json').write_text(json.dumps({'hotkeys':{'study':'Ctrl+Q','region':'Alt+W','toggle':'Alt+T','hover':'Alt+H'}}))
            settings=store.settings()
            self.assertEqual(settings['hotkeys']['screen'],'Alt+V')
            self.assertEqual(settings['hotkeys']['study'],'Ctrl+Q')
            self.assertLess(settings['card_background'],1)
