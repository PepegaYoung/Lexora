import sentencepiece,ctranslate2
import tempfile,unittest,ctypes,threading
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from windowwords.app import MainWindow,STYLE
from windowwords.storage import Store
from windowwords.core import Box
from windowwords.safety import DEFAULT_PROTECTED,executable_name,protected_match
from windowwords.processes import ProcessEntry,running_executables
from windowwords import native

class SafetyPolicyTests(unittest.TestCase):
    def test_match_is_exact_case_insensitive_and_includes_background_games(self):
        settings={'protected_games':['Marvel-Win64-Shipping.exe']}
        self.assertEqual(protected_match(settings,{'explorer.exe','MARVEL-WIN64-SHIPPING.EXE'}),'marvel-win64-shipping.exe')
        self.assertFalse(protected_match(settings,{'marvel-win64-shipping.exe.backup.exe'}))
        self.assertFalse(protected_match(dict(settings,game_protection=False),{'marvel-win64-shipping.exe'}))
    def test_selected_path_stores_only_basename_and_rejects_wildcards(self):
        self.assertEqual(executable_name(r'Z:\Games\Example\Game.EXE'),'game.exe')
        for invalid in ('*game.exe','game.dll','game?.exe',''):
            with self.assertRaises(ValueError):executable_name(invalid)
    def test_existing_profile_receives_protection_defaults_and_persists_choices(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));store.save_settings({'game':'Example'})
            settings=store.settings()
            self.assertTrue(settings['game_protection']);self.assertEqual(settings['protection_action'],'quit')
            self.assertEqual(settings['protected_games'],list(DEFAULT_PROTECTED))
            settings.update(protection_action='pause',protected_games=['game.exe'])
            store.save_settings(settings)
            self.assertEqual(store.settings()['protected_games'],['game.exe'])
    def test_snapshot_closes_handle_and_does_not_open_process(self):
        kernel=Mock();rows=iter([(0,'System'),(1234,'game.exe')])
        def next_entry(handle,pointer):
            try:
                pid,name=next(rows);entry=ctypes.cast(pointer,ctypes.POINTER(ProcessEntry)).contents
                entry.th32ProcessID=pid;entry.szExeFile=name;return True
            except StopIteration:return False
        kernel.CreateToolhelp32Snapshot.return_value=123
        kernel.Process32FirstW.side_effect=next_entry;kernel.Process32NextW.side_effect=next_entry
        with patch('windowwords.processes.ctypes.WinDLL',return_value=kernel),patch('windowwords.processes.ctypes.get_last_error',return_value=18):
            self.assertEqual(running_executables(),{'system','game.exe'})
        kernel.CloseHandle.assert_called_once_with(123);kernel.OpenProcess.assert_not_called()
    def test_incomplete_or_failed_snapshot_is_an_error_not_an_empty_success(self):
        kernel=Mock();kernel.CreateToolhelp32Snapshot.return_value=123;kernel.Process32FirstW.return_value=False
        with patch('windowwords.processes.ctypes.WinDLL',return_value=kernel),patch('windowwords.processes.ctypes.get_last_error',return_value=5):
            with self.assertRaises(OSError):running_executables()
        kernel.CloseHandle.assert_called_once_with(123)
        kernel.CreateToolhelp32Snapshot.return_value=ctypes.c_void_p(-1).value
        with patch('windowwords.processes.ctypes.WinDLL',return_value=kernel):
            with self.assertRaises(OSError):running_executables()
    def test_foreground_profile_reads_pid_snapshot_without_opening_game(self):
        def pid(handle,pointer):ctypes.cast(pointer,ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value=987654
        with patch('windowwords.native.foreground',return_value=123),patch('windowwords.native.user.GetWindowThreadProcessId',side_effect=pid),\
             patch('windowwords.processes.process_snapshot',return_value={987654:'game.exe'}) as snapshot:
            self.assertEqual(native.foreground_executable(),'game.exe');snapshot.assert_called_once()
            snapshot.side_effect=OSError('unavailable');self.assertEqual(native.foreground_executable(),'')

class Keys:
    def __init__(self,*args):self.started=0;self.stopped=0
    def start(self):self.started+=1
    def stop(self):self.stopped+=1
    def join(self,**kwargs):pass
    def set_escape(self,*args):pass

class SafetyUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name));self.window=None
        self.patches=[patch('windowwords.native.Hotkeys',Keys),patch('windowwords.safety.running_executables',return_value=set()),
                      patch('windowwords.safety.GameSafety.exit_for_protection'),patch('windowwords.controls.InputCapture')]
        self.keys,self.processes,self.quit,self.recorder=[p.start() for p in self.patches]
        self.app.setStyleSheet(STYLE)
    def tearDown(self):
        if self.window:self.window.close();self.app.processEvents()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()
    def create(self,mode='pause'):
        settings=self.store.settings();settings['protection_action']=mode;self.store.save_settings(settings)
        self.window=MainWindow(self.store);self.window.safety_timer.stop()
        return self.window
    def protect(self):
        self.processes.return_value={'marvel-win64-shipping.exe','explorer.exe'}
        return self.window.check_game_protection()
    def test_startup_game_blocks_hotkeys_before_registration_and_schedules_quit_once(self):
        self.processes.return_value={'marvel.exe'}
        window=self.create('quit')
        self.assertEqual(window.keys.started,0);self.assertTrue(window.safety_blocked)
        window.check_game_protection();self.app.processEvents()
        self.quit.assert_called_once()
    def test_pause_closes_windows_cancels_generations_and_stops_every_input_path(self):
        window=self.create();window.task=Mock()
        window.show_freeze(Image.new('RGB',(100,100)),window.monitor,'region')
        window.show_card('sword','A sword');window.result_window.show();window.overlay.show()
        window.running=True
        epochs=(window.epoch.value,window.card_epoch.value,window.capture_epoch.value)
        self.assertFalse(self.protect())
        self.assertFalse(window.running or window.card.isVisible() or window.overlay.isVisible() or window.result_window.isVisible())
        self.assertIsNone(window.freeze);self.assertGreaterEqual(window.keys.stopped,1)
        self.assertFalse(window.timer.isActive() or window.auto_translate_timer.isActive())
        self.assertTrue(all(now>old for now,old in zip((window.epoch.value,window.card_epoch.value,window.capture_epoch.value),epochs)))
        self.quit.assert_not_called()
    def test_latched_pause_never_resumes_on_alt_tab_or_process_disappearance(self):
        window=self.create();self.protect();keys=window.keys
        self.processes.return_value=set();window.check_game_protection()
        window.on_hotkey('study');window.start_screen();window.capture_freeze('region')
        self.assertTrue(window.safety_blocked);self.assertIsNone(window.freeze);self.assertEqual(keys.started,1)
        window.resume_game_protection()
        self.assertFalse(window.safety_blocked);self.assertIsNot(window.keys,keys);self.assertEqual(window.keys.started,1)
        self.assertFalse(window.running)
    def test_resume_requires_game_exit_and_fresh_successful_observation(self):
        window=self.create();self.protect();keys=window.keys;window.resume_game_protection()
        self.assertIs(window.keys,keys);self.assertTrue(window.safety_blocked)
        self.processes.side_effect=OSError('unavailable');window.resume_game_protection()
        self.assertTrue(window.safety_blocked);self.assertIs(window.keys,keys)
    def test_snapshot_error_is_fail_closed_without_quitting_or_starting_hooks(self):
        self.processes.side_effect=OSError('unavailable');window=self.create('quit')
        self.assertTrue(window.safety_blocked);self.assertEqual(window.keys.started,0)
        self.app.processEvents();self.quit.assert_not_called()
    def test_settings_changes_with_real_unstarted_thread_do_not_register_hooks(self):
        self.processes.return_value={'marvel.exe'}
        with patch('windowwords.native.Hotkeys',original_hotkeys),patch('windowwords.native.user.SetWindowsHookExW') as hooks,patch('windowwords.native.user.RegisterHotKey') as register:
            window=self.create()
            self.assertFalse(window.keys.is_alive())
            window.game_mode_pick.setCurrentIndex(window.game_mode_pick.findData('overlay'))
            window.apply_settings()
            self.assertFalse(window.keys.is_alive())
            hooks.assert_not_called();register.assert_not_called()
    def test_capture_worker_checks_current_processes_without_qt_or_screen_capture(self):
        window=self.create();self.processes.return_value={'marvel.exe'}
        with patch('windowwords.app.mss.mss') as grab:
            with self.assertRaises(RuntimeError):window.capture_image(Box(0,0,20,20))
            grab.assert_not_called()
        self.assertFalse(window.safety_blocked) # worker only rejects; GUI poll handles state
    def test_hotkey_recording_and_settings_cannot_reinstall_inputs_while_paused(self):
        window=self.create();self.protect()
        field=window.hotkey_fields['study'];field.begin();self.recorder.assert_not_called()
        self.assertFalse(field.recording)
        window.game_mode_pick.setCurrentIndex(window.game_mode_pick.findData('overlay'))
        self.assertEqual(window.keys.started,0)
        window.apply_settings();self.assertEqual(window.keys.started,0)
    def test_game_appearing_between_polls_blocks_explicit_ui_action(self):
        window=self.create();self.processes.return_value={'marvel.exe'}
        window.capture_freeze('study')
        self.assertTrue(window.safety_blocked);self.assertIsNone(window.freeze)
    def test_queued_job_cleanup_is_not_lost_when_pausing(self):
        window=self.create();window.pool.setMaxThreadCount(1)
        started=threading.Event();release=threading.Event();completed=[]
        def busy():started.set();release.wait(3)
        window.task(busy,lambda _:None);self.assertTrue(started.wait(1))
        window.ocr_busy=True
        def cleaned(_):window.ocr_busy=False;completed.append(True)
        window.task(lambda:'stale-result',cleaned)
        self.protect();release.set()
        self.assertTrue(window.pool.waitForDone(1500));self.app.processEvents()
        self.assertFalse(window.ocr_busy);self.assertEqual(completed,[True])
        self.assertFalse(window.running);self.assertIsNone(window.freeze)
    def test_disabled_automatic_protection_keeps_manual_pause_effective(self):
        window=self.create();window.safety_enabled.setChecked(False);self.processes.return_value={'marvel.exe'}
        self.assertTrue(window.allow_game_action())
        window.suspend_game_activity('Manual');self.assertFalse(window.allow_game_action())
    def test_exit_uses_own_normal_close_before_ending_own_workers(self):
        from windowwords.safety import GameSafety
        # Invoke the real method through its unpatched definition saved below.
        with patch('windowwords.safety.os._exit') as exit_process:
            real_exit(self.create())
            self.assertTrue(self.window.closing);exit_process.assert_called_once_with(0)

from windowwords.safety import GameSafety
real_exit=GameSafety.exit_for_protection
original_hotkeys=native.Hotkeys
