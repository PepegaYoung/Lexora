import sentencepiece,ctranslate2
import threading,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image
from windowwords.core import Box,Generation,Line
from windowwords.screen import Tracker
from windowwords.screen_mode import ScreenMode
from windowwords.recording import RecordingMode
from windowwords.recording_capture import CleanCapture
from windowwords.app import MainWindow


class ScreenHarness(ScreenMode,RecordingMode):
    def __init__(self):
        self.settings={'recording_visible':False,'screen_scope':'monitor','filter':'raw','provider':'yandex_web'}
        self.running=True;self.closing=False;self.safety_blocked=False;self.freeze=None
        self.ocr_busy=self.cloud_busy=False;self.epoch=Generation();self.capture_epoch=Generation()
        self.monitor={'x':0,'y':0,'w':800,'h':600};self.screen_snapshot=False
        self.screen_target=None;self.screen_tracks=Tracker();self.history=[]
        self.overlay=Mock();self.recording_capture=Mock();self.region_ocr=Mock();self.read_result=Mock()
        self.capture_image=Mock(return_value='desktop');self.measurements=SimpleNamespace(run=lambda name,fn:fn())
        self.draw_screen=Mock();self.message=Mock();self.jobs=[];self.capture_permitted=lambda:not self.safety_blocked
        self.task=lambda fn,done,failed:self.jobs.append((fn,done,failed))
        self.stop=lambda:MainWindow.stop(self)


class CaptureSessionTests(unittest.TestCase):
    def test_fullscreen_normal_auto_and_snapshot_never_start_wgc(self):
        w=ScreenHarness();w.session_target=w.screen_target=123;box=Box(0,0,800,600)
        with patch('windowwords.recording.CleanCapture') as factory:
            self.assertEqual(w.capture_screen_image(box),'desktop')
            self.assertEqual(w.capture_session_image(box),'desktop')
            factory.assert_not_called();w.recording_capture.grab.assert_not_called()

    def test_recording_auto_request_cancels_on_stop_and_cannot_reopen(self):
        w=ScreenHarness();w.settings['recording_visible']=True;w.recording_target=123
        w.capture_screen_image(Box(0,0,800,600))
        cancel=w.recording_capture.grab.call_args.kwargs['cancel'];self.assertFalse(cancel())
        w.stop();self.assertTrue(cancel())
        w.running=True;self.assertTrue(cancel())

    def test_stop_releases_owned_busy_flags_before_restart(self):
        w=ScreenHarness();w.ocr_busy=w.cloud_busy=True;w.screen_ocr_revision=w.screen_cloud_revision=w.epoch.value
        w.stop();self.assertFalse(w.ocr_busy);self.assertFalse(w.cloud_busy)

    def test_stop_does_not_clear_an_independent_card_translation(self):
        w=ScreenHarness();w.cloud_busy=True;w.stop();self.assertTrue(w.cloud_busy)

    def test_queued_ocr_after_stop_does_not_capture(self):
        w=ScreenHarness();w.tick();fn,done,failed=w.jobs.pop();w.stop()
        self.assertEqual(fn(),());w.capture_image.assert_not_called()

    def test_old_ocr_success_and_error_cannot_clear_new_request(self):
        w=ScreenHarness();w.tick();old=w.jobs[-1];w.stop();w.running=True;w.tick();new=w.jobs[-1]
        old[1](());old[2]('obsolete error');self.assertTrue(w.ocr_busy);self.assertTrue(w.running)
        new[1]((Line('New text',Box(10,10,80,20),()),));self.assertFalse(w.ocr_busy)
        self.assertEqual(w.lines[0].text,'New text');w.message.assert_not_called()

    def test_old_translation_success_and_error_cannot_clear_new_request(self):
        w=ScreenHarness();w.pump_screen=ScreenMode.pump_screen.__get__(w)
        w.screen_tracks.update((Line('Open',Box(10,10,80,20),()),),0,instant=True)
        w.pump_screen();old=w.jobs[-1];w.stop();w.running=True;w.pump_screen();new=w.jobs[-1]
        old[1](['Old']);old[2]('obsolete error');self.assertTrue(w.cloud_busy);self.assertTrue(w.running)
        new[1](['Открыть']);self.assertFalse(w.cloud_busy);self.assertEqual(w.history,[('Open','Открыть')])


class Pool:
    def __init__(self,frames=()):self.frames=list(frames);self.closed=False
    def try_get_next_frame(self):return self.frames.pop(0) if self.frames else None
    def close(self):self.closed=True


class TestCapture(CleanCapture):
    def __init__(self):
        super().__init__();self.starts=0;self.next_frames=[]
    def _start(self,hwnd):
        self._close();self.starts+=1;self.hwnd=hwnd;self.pool=Pool(self.next_frames)
        self.session=Mock();self.next_frames=[]


class RecordingStreamTests(unittest.TestCase):
    def setUp(self):
        self.box=Box(0,0,80,60);self.bounds=patch('windowwords.recording_capture.window_bounds',return_value=self.box)
        self.bounds.start();self.addCleanup(self.bounds.stop)

    def test_already_cancelled_request_does_not_open_capture(self):
        c=TestCapture()
        with self.assertRaises(RuntimeError):c.grab(123,self.box,cancel=lambda:True)
        self.assertEqual(c.starts,0)

    def test_cancel_while_waiting_closes_the_session(self):
        c=TestCapture();checks=iter((False,False,False,True))
        with self.assertRaises(RuntimeError):c.grab(123,self.box,cancel=lambda:next(checks,True))
        self.assertIsNone(c.session);self.assertIsNone(c.pool);self.assertIsNone(c.hwnd)

    def test_close_cancels_inflight_capture_and_releases_without_shutdown(self):
        c=TestCapture();started=threading.Event();errors=[]
        def start(hwnd):TestCapture._start(c,hwnd);started.set()
        c._start=start
        def grab():
            try:c.grab(123,self.box)
            except RuntimeError as e:errors.append(str(e))
        worker=threading.Thread(target=grab);worker.start();self.assertTrue(started.wait(1));c.close();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertIsNone(c.session)

    def test_recent_static_frame_can_be_reused(self):
        c=TestCapture();c.hwnd=123;c.pool=Pool();c.image=Image.new('RGB',(80,60),'blue');c.frame_time=time.monotonic()
        self.assertEqual(c.grab(123,self.box).getpixel((0,0)),(0,0,255));self.assertEqual(c.starts,0)

    def test_stale_frame_reopens_stream_and_reads_new_frame(self):
        c=TestCapture();c.hwnd=123;c.pool=Pool();old_pool=c.pool
        c.image=Image.new('RGB',(80,60),'blue');c.frame_time=time.monotonic()-10
        frame=Mock();c.next_frames=[frame]
        async def red(f):return Image.new('RGB',(80,60),'red')
        with patch('windowwords.recording_capture.frame_image',side_effect=red):
            self.assertEqual(c.grab(123,self.box).getpixel((0,0)),(255,0,0))
        self.assertEqual(c.starts,1);self.assertTrue(old_pool.closed);frame.close.assert_called_once();c.close()

    def test_stale_stream_cannot_return_old_frame_forever(self):
        c=TestCapture();c.hwnd=123;c.pool=Pool();c.image=Image.new('RGB',(80,60));c.frame_time=-10
        ticks=iter((0,1,2,5))
        with patch('windowwords.recording_capture.time.monotonic',side_effect=lambda:next(ticks,5)),patch('windowwords.recording_capture.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'Нет кадра'):c.grab(123,self.box)
        self.assertEqual(c.starts,1);self.assertIsNone(c.session);self.assertIsNone(c.image)
