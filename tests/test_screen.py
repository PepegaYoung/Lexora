import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from windowwords.core import Box,Line,Word
from windowwords.screen import Tracker,blocks,intersects
from windowwords.screen_layout import layout
from windowwords.translation import parse_segments,response_body,Translator
from windowwords.auth import ServiceError
from windowwords.storage import Store
from windowwords.core import Generation
from windowwords.screen_mode import ScreenMode


def line(text,y=200,x=100,w=300,h=25):return Line(text,Box(x,y,w,h),())
def measure(text,size,width):
    import math
    return len(text)*size*.5,max(size,math.ceil(len(text)*size*.5/max(1,width))*size)


class CaptureHarness(ScreenMode):
    def __init__(self,region=None):
        self.settings={'screen_scope':'region','filter':'raw','provider':'local'}
        self.monitor={'x':-2560,'y':120,'w':2560,'h':1440}
        self.region=region;self.running=False;self.session_active=False
        self.closing=self.safety_blocked=self.ocr_busy=False;self.freeze=None
        self.epoch=Generation();self.jobs=[]
        self.allow_game_action=lambda:True
        self.game=Mock();self.game.text.return_value='Test'
        self.keys=Mock();self.refresh_key_labels=Mock();self.message=Mock();self.showMinimized=Mock()
        self.region_ocr=Mock();self.capture_image=Mock(return_value=Image.new('RGB',(100,60)));self.measurements=Mock()
        self.measurements.run.side_effect=lambda _,fn:fn()
        self.draw_screen=Mock();self.pump_screen=Mock()
    def stop(self):self.running=False;self.epoch.next()
    def task(self,fn,done,failed):self.jobs.append((fn,done,failed))


class CaptureScopeTests(unittest.TestCase):
    def start(self,window,once=True):
        with patch('windowwords.screen_mode.QTimer.singleShot'):
            window.start_screen(once)
    def test_current_frame_uses_selected_full_monitor_without_region(self):
        window=CaptureHarness();self.start(window)
        self.assertTrue(window.running)
        self.assertEqual(window.screen_box(),Box(-2560,120,2560,1440))
        self.assertIsNone(window.region)
        self.assertEqual(window.settings['screen_scope'],'region')
    def test_current_frame_captures_full_monitor_despite_saved_region(self):
        region=Box(-2300,900,700,150);window=CaptureHarness(region);self.start(window)
        window.tick()
        with patch('windowwords.screen_mode.ocr.read',return_value=()):window.jobs[0][0]()
        window.capture_image.assert_called_once_with(Box(-2560,120,2560,1440))
        self.assertEqual(window.region,region)
    def test_current_frame_stays_one_capture_after_ocr_completes(self):
        window=CaptureHarness();self.start(window);window.tick()
        window.jobs[0][1](())
        window.tick()
        self.assertEqual(len(window.jobs),1)
    def test_auto_translation_still_uses_region_after_current_frame(self):
        region=Box(-2300,900,700,150);window=CaptureHarness(region)
        self.start(window);self.start(window,once=False)
        self.assertFalse(window.screen_snapshot)
        self.assertEqual(window.screen_box(),region)
        window.tick()
        with patch('windowwords.screen_mode.ocr.read',return_value=()):window.jobs[0][0]()
        window.capture_image.assert_called_once_with(region)
    def test_auto_translation_requires_region_or_monitor_scope(self):
        window=CaptureHarness();self.start(window,once=False)
        self.assertFalse(window.running)
        window.settings['screen_scope']='monitor';self.start(window,once=False)
        self.assertTrue(window.running)
        self.assertEqual(window.screen_box(),Box(-2560,120,2560,1440))


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

    def test_top_edge_uses_nearby_space_instead_of_leaving_screen(self):
        labels,skipped=layout([(Box(100,1,100,20),'Привет')],800,600,'above',22,8,measure)
        self.assertEqual(skipped,0);self.assertEqual(len(labels),1)
        self.assertEqual(labels[0].placement,'below')
        self.assertGreaterEqual(labels[0].box.y,0)
        self.assertFalse(intersects(labels[0].source,labels[0].box))

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
        self.assertEqual(translator.translate_segments({'provider':'mymemory'},['one','two']),('один','два'))

    def test_old_settings_gain_new_hotkey_and_background(self):
        with tempfile.TemporaryDirectory() as path:
            store=Store(Path(path))
            (Path(path)/'settings.json').write_text(json.dumps({'hotkeys':{'study':'Ctrl+Q','region':'Alt+W','toggle':'Alt+T','hover':'Alt+H'}}))
            settings=store.settings()
            self.assertEqual(settings['hotkeys']['screen'],'Alt+V')
            self.assertEqual(settings['hotkeys']['study'],'Ctrl+Q')
            self.assertNotIn('hover',settings['hotkeys'])
            self.assertLess(settings['card_background'],1)
