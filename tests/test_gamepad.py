import sentencepiece,ctranslate2
import tempfile,json,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from winrt.windows.gaming.input import GameControllerButtonLabel as Label,GamepadButtons as Buttons
from windowwords.gamepad import ACTIONS,Controller,RawControllerSource,ChordCycle,parse_chord,display,validate_bindings
from windowwords.shortcuts import device_bindings
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup
from windowwords.input_capture import InputCapture,mouse_key
from tests import test_usability as usability

def bindings(**values):return dict.fromkeys(ACTIONS,'')|values

class GamepadLogicTests(unittest.TestCase):
    def test_order_independent_combinations_and_invalid_bindings(self):
        self.assertEqual(parse_chord('LB+South'),parse_chord('South+LB'))
        for value in ('','South+South','A','LB+','Button137','South+East+West+North+LB+RB+LT'):
            with self.assertRaises(ValueError):parse_chord(value)
        with self.assertRaises(ValueError):validate_bindings(bindings(study='South+LB',screen='LB+South'))
        validate_bindings(bindings(study='South; LB+South'))
        self.assertIn('×',display('South+LB','playstation'))
        self.assertIn('A',display('South+LB','xbox'))
        self.assertEqual(display('Button15','generic'),'Кнопка 15')
    def test_cycle_ignores_held_at_start_and_fires_only_once_after_release(self):
        cycle=ChordCycle()
        for state in ({'South'},{'South'},set(),set()):self.assertIsNone(cycle.feed(state))
        for state in ({'LB'},{'LB','South'},{'LB','South'},{'LB'}):self.assertIsNone(cycle.feed(state))
        self.assertEqual(cycle.feed(set()),frozenset({'LB','South'}))
        self.assertIsNone(cycle.feed(set()))
    def test_disconnected_controller_never_fires_or_merges_buttons_with_other_pad(self):
        from windowwords.gamepad_input import GamepadHotkeys
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        keys=GamepadHotkeys(None,lambda:True);calls=[];keys.action.connect(calls.append)
        keys.source=Mock();keys.start(bindings(study='South+LB'),True)
        keys.source.poll.side_effect=[{'one':set(),'two':set()},{'one':{'South'},'two':{'LB'}},{'two':set()},
                                     {'one':{'South','LB'}},{'one':set()},{'one':{'South','LB'}},{'one':set()}]
        for _ in range(7):keys.poll()
        self.assertEqual(calls,['study']);keys.stop()
    def test_stopped_or_blocked_input_does_not_read_devices(self):
        from windowwords.gamepad_input import GamepadHotkeys
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        allowed=[True];keys=GamepadHotkeys(None,lambda:allowed[0]);keys.source=Mock()
        keys.start(bindings(study='South'),False);keys.poll();keys.source.poll.assert_not_called()
        keys.start(bindings(study='South'),True);allowed[0]=False;keys.poll()
        keys.source.poll.assert_not_called();self.assertFalse(keys.timer.isActive())
    def test_physical_and_virtual_copy_do_not_dispatch_twice(self):
        from windowwords.gamepad_input import GamepadHotkeys
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        keys=GamepadHotkeys(None,lambda:True);calls=[];keys.action.connect(calls.append)
        keys.source=Mock();keys.start(bindings(study='South'),True)
        keys.source.poll.side_effect=[
            {'physical':set(),'virtual':set()},
            {'physical':{'South'},'virtual':{'South'}},
            {'physical':set(),'virtual':{'South'}},
            {'physical':set(),'virtual':set()},
            {'physical':{'South'},'virtual':{'South'}},
            {'physical':set(),'virtual':set()},
        ]
        with patch('windowwords.gamepad_input.time.monotonic',side_effect=[1.0,1.04,1.2,1.2]):
            for _ in range(6):keys.poll()
        self.assertEqual(calls,['study','study']);keys.stop()
    def test_raw_sony_and_generic_hid_buttons_switches_and_hotplug(self):
        raw=Mock(non_roamable_id='temporary-pad',display_name='Demo DualSense',hardware_vendor_id=0x054C,
                 hardware_product_id=0x0CE6,button_count=14,switch_count=1,axis_count=6)
        raw.get_button_label.return_value=Label.NONE
        def read(buttons,switches,axes):
            for i in range(len(buttons)):buttons[i]=i in (1,4)
            switches[0]=2
        raw.get_current_reading.side_effect=read
        with patch('winrt.windows.gaming.input.RawGameController') as cls,patch('winrt.windows.gaming.input.Gamepad') as pad:
            cls.raw_game_controllers=[raw];pad.from_game_controller.return_value=None
            source=RawControllerSource();self.assertEqual(source.discover()[0].family,'playstation')
            self.assertEqual(source.poll()['temporary-pad'],frozenset({'South','LB','Up','Right'}))
            raw.hardware_vendor_id=0x9999;source.reset()
            self.assertEqual(source.poll()['temporary-pad'],frozenset({'Button2','Button5','Up','Right'}))
            cls.raw_game_controllers=[];source.discover(force=True);self.assertFalse(source.poll())
    def test_xbox_normalized_buttons_and_triggers(self):
        raw=Mock(non_roamable_id='temporary-xbox',display_name='Demo Xbox',hardware_vendor_id=0x045E,
                 hardware_product_id=0,button_count=0,switch_count=0,axis_count=0)
        state=Mock(buttons=Buttons.A|Buttons.RIGHT_SHOULDER,left_trigger=.8,right_trigger=.1)
        with patch('winrt.windows.gaming.input.RawGameController') as cls,patch('winrt.windows.gaming.input.Gamepad') as pad:
            cls.raw_game_controllers=[raw];pad.from_game_controller.return_value.get_current_reading.return_value=state
            self.assertEqual(RawControllerSource().poll()['temporary-xbox'],frozenset({'South','RB','LT'}))
    def test_native_keyboard_and_mouse_capture_are_separate(self):
        self.assertEqual(device_bindings('Alt+Q; Mouse4; Ctrl+Mouse5','keyboard'),'Alt+Q')
        self.assertEqual(device_bindings('Alt+Q; Mouse4; Ctrl+Mouse5','mouse'),'Mouse4; Ctrl+Mouse5')
        recorded=Mock();capture=InputCapture(recorded,Mock(),Mock(),device='keyboard')
        self.assertFalse(capture.process(5,True,0));recorded.assert_not_called()
        capture=InputCapture(recorded,Mock(),Mock(),device='mouse')
        self.assertFalse(capture.process(0x51,True,0));recorded.assert_not_called()
        self.assertTrue(capture.process(4,True,0));recorded.assert_called_once_with('Mouse3')
        self.assertEqual(mouse_key(0x207,0),4)
    def test_legacy_bindings_and_new_backup_preserve_independent_devices(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'one');store.save_settings({'hotkeys':{'study':'Alt+Q; Mouse4'}})
            settings=store.settings();self.assertFalse(settings['gamepad_enabled'])
            settings.update(gamepad_bindings=bindings(study='LB+South'),gamepad_enabled=True)
            file=root/'backup.json';export_backup(store,settings,file)
            other=Store(root/'two');import_backup(other,file)
            self.assertEqual(other.settings()['hotkeys']['study'],'Alt+Q; Mouse4')
            self.assertEqual(other.settings()['gamepad_bindings']['study'],'LB+South')
            data=json.loads(file.read_text());data['settings']['gamepad_bindings']['screen']='South+LB'
            file.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):import_backup(other,file)
            self.assertEqual(other.settings()['gamepad_bindings']['screen'],'')

class DeviceBindingUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown
    def test_visible_device_panels_and_recording_preserve_other_devices(self):
        self.window.tabs.setCurrentIndex(next(i for i in range(self.window.tabs.count()) if self.window.tabs.list.item(i).text()=='Привязки'))
        self.window.show();self.app.processEvents()
        self.assertTrue(all(panel.isVisible() for panel in self.window.binding_panels.values()))
        mouse=self.window.mouse_hotkey_fields['study'];mouse.begin();QTest.mouseClick(mouse,Qt.MouseButton.MiddleButton);self.app.processEvents()
        self.assertEqual(self.window.hotkey_fields['study'].text(),'Alt+Q')
        self.assertEqual(self.window.settings['hotkeys']['study'],'Mouse3; Alt+Q')
        key=self.window.hotkey_fields['study'];key.begin();QTest.keyClick(key,Qt.Key.Key_F8);self.app.processEvents()
        self.assertEqual(self.window.settings['hotkeys']['study'],'F8; Mouse3')
        self.window.clear_hotkey('study','keyboard')
        self.assertEqual(self.window.settings['hotkeys']['study'],'Mouse3')
        self.window.clear_hotkey('study','mouse')
        self.assertEqual(self.window.settings['hotkeys']['study'],'')
    def test_pad_recording_waits_for_release_persists_and_resumes_runtime(self):
        field=self.window.gamepad_hotkey_fields['study'];field.source=Mock();field.begin()
        self.assertTrue(self.window.hotkey_capture_active)
        field.source.poll.side_effect=[{'one':set()},{'one':{'LB'}},{'one':{'LB','South'}},{'one':{'South'}},{'one':set()}]
        for _ in range(4):field.poll()
        self.assertEqual(self.window.settings['gamepad_bindings']['study'],'')
        field.poll();self.app.processEvents()
        self.assertEqual(parse_chord(self.window.store.settings()['gamepad_bindings']['study']),frozenset({'LB','South'}))
        self.assertFalse(field.recording);self.assertFalse(self.window.hotkey_capture_active)
        self.assertTrue(self.window.gamepad_keys.timer.isActive())
        self.assertTrue(self.window.settings['gamepad_enabled'])
    def test_pad_cancel_duplicate_and_protection_stop_all_input(self):
        field=self.window.gamepad_hotkey_fields['study'];field.source=Mock()
        field.begin();QTest.keyClick(field,Qt.Key.Key_Escape);self.app.processEvents()
        self.assertFalse(field.recording);self.assertEqual(field.value,'')
        self.window.record_hotkey('study','South','gamepad')
        self.window.record_hotkey('screen','South','gamepad')
        self.assertEqual(self.window.settings['gamepad_bindings']['screen'],'')
        field.begin();self.window.suspend_game_activity('Test protected game')
        self.assertFalse(field.recording);self.assertFalse(field.timer.isActive())
        self.assertFalse(self.window.gamepad_keys.timer.isActive())
        self.assertFalse(self.window.allow_game_action())
    def test_controller_choice_has_ephemeral_ids_not_saved_in_settings(self):
        devices=[Controller('temporary-sony','Demo PlayStation','playstation'),Controller('temporary-xbox','Demo Xbox','xbox')]
        with patch('windowwords.gamepad.RawControllerSource.discover',return_value=devices):self.window.refresh_gamepads()
        self.window.gamepad_device_pick.setCurrentIndex(1)
        self.assertEqual(self.window.gamepad_hotkey_fields['study'].family,'playstation')
        self.window.store.save_settings(self.window.settings)
        self.assertNotIn('temporary-sony',(self.window.store.folder/'settings.json').read_text())
