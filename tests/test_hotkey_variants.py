import sentencepiece,ctranslate2
import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from windowwords import native
from windowwords.backup import export_backup,import_backup
from windowwords.storage import Store
from tests import test_usability as usability


class NativeVariantsTests(unittest.TestCase):
    def test_single_keys_and_multi_modifier_chords(self):
        for text,key in [('Q',0x51),('7',0x37),('F24',0x87),('Space',0x20),('Enter',0x0D),('PageDown',0x22),('Left',0x25)]:
            self.assertEqual(native.parse_hotkey(text),(0x4000,key))
        self.assertEqual(native.parse_hotkeys('Q; Shift+Q; Ctrl+Alt+Q'),[(0x4000,81),(0x4004,81),(0x4003,81)])
        self.assertEqual(native.hotkey_label('F8; Shift+Q'),'F8 (+1)')

    def test_duplicate_and_invalid_variants_rejected(self):
        for bindings in ({'a':'Q; q'},{'a':'Ctrl+Alt+Q','b':'Alt+Ctrl+Q'},{'a':'Q; F8','b':'F8'}):
            with self.assertRaises(ValueError):native.validate_bindings(bindings)
        for value in ('Escape','Shift','Ctrl+Ctrl+Q','Q;','Q; W; E; R; T; Y; U; I; O'):
            with self.assertRaises(ValueError):native.parse_hotkeys(value)
        self.assertEqual(native.parse_hotkeys(''),[])

    def test_each_alternative_dispatches_same_action_and_single_keys_suspend(self):
        actions=[];failures=[]
        keys=native.Hotkeys(actions.append,failures.append,{'study':'F20; Ctrl+Alt+Shift+F24'},False)
        messages=iter([(0x312,1),(0x312,2),(0x8002,0),(0x312,1),(0x312,2),(0x8002,1),(0x312,1)])
        def get_message(pointer,*args):
            try:message,param=next(messages)
            except StopIteration:return 0
            pointer._obj.message=message;pointer._obj.wParam=param
            return 1
        with patch.object(native.user,'PeekMessageW'),patch.object(native.user,'GetMessageW',side_effect=get_message),\
             patch.object(native.user,'RegisterHotKey',return_value=True) as register,\
             patch.object(native.user,'UnregisterHotKey') as unregister,patch.object(native.user,'TranslateMessage'),\
             patch.object(native.user,'DispatchMessageW'),patch.object(native.user,'SetWindowsHookExW') as hook:
            keys.run()
        self.assertEqual(actions,['study']*4)
        self.assertFalse(failures)
        self.assertEqual(register.call_count,3)
        self.assertEqual(unregister.call_count,3)
        self.assertFalse(keys.registered)
        hook.assert_not_called()

    def test_conflict_names_actual_alternative_and_other_bindings_work(self):
        failures=[]
        keys=native.Hotkeys(lambda _:None,failures.append,{'study':'F20; Shift+Q'},False)
        with patch.object(native.user,'PeekMessageW'),patch.object(native.user,'GetMessageW',return_value=0),\
             patch.object(native.user,'RegisterHotKey',side_effect=[True,False]),patch.object(native.user,'UnregisterHotKey') as unregister,\
             patch.object(native.user,'SetWindowsHookExW',return_value=101),patch.object(native.user,'UnhookWindowsHookEx'):
            keys.run()
        self.assertEqual(len(failures),1)
        self.assertIn('Shift+Q',failures[0]);self.assertNotIn('F20;',failures[0])
        unregister.assert_called_once_with(None,1)

    def test_backup_round_trip_preserves_variants_and_refuses_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'one');settings=store.settings()
            settings['hotkeys']['study']='F8; Shift+Q'
            file=root/'backup.json';export_backup(store,settings,file)
            other=Store(root/'two');import_backup(other,file)
            self.assertEqual(other.settings()['hotkeys']['study'],'F8; Shift+Q')
            data=json.loads(file.read_text(encoding='utf-8'))
            data['settings']['hotkeys']['region']='F8'
            file.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):import_backup(other,file)
            self.assertEqual(other.settings()['hotkeys']['region'],'Alt+W')


class VariantCaptureTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown
    record=usability.UsabilityTests.record
    snapshot=usability.UsabilityTests.snapshot
    def test_onboarding_uses_keyboard_not_mouse(self):
        from windowwords.onboarding import OnboardingDialog
        self.window.settings['hotkeys']['study']='Mouse4; Alt+Q'
        guide=OnboardingDialog(self.window)
        self.assertEqual(guide.shortcut('study'),'Alt+Q')
        self.window.settings['hotkeys']['study']='Mouse4'
        guide.settings=dict(self.window.settings)
        self.assertEqual(guide.shortcut('study'),'Не назначено')
        guide.close()
    def test_restore_each_device_keeps_other_bindings(self):
        self.window.record_hotkey('study','F8','keyboard')
        self.window.record_hotkey('study','Mouse4','mouse')
        self.window.reset_hotkey('study','keyboard')
        self.assertEqual(self.window.settings['hotkeys']['study'],'Alt+Q; Mouse4')
        self.window.reset_hotkey('study','mouse')
        self.assertEqual(self.window.settings['hotkeys']['study'],'Alt+Q')

    def test_reset_inside_field_does_not_start_recording(self):
        self.window.record_hotkey('study','F8','keyboard')
        field=self.window.hotkey_fields['study']
        self.window.show();self.app.processEvents()
        self.assertIs(field.reset_button.parentWidget(),field)
        self.assertEqual(field.reset_button.toolTip(),'Вернуть по умолчанию')
        QTest.mouseClick(field.reset_button,Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(field.recording)
        self.assertEqual(self.window.settings['hotkeys']['study'],'Alt+Q')

    def test_restore_conflict_preserves_current_binding(self):
        self.window.record_hotkey('study','F8','keyboard')
        self.window.record_hotkey('region','Alt+Q','keyboard')
        self.window.reset_hotkey('study','keyboard')
        self.assertEqual(self.window.settings['hotkeys']['study'],'F8')
        self.assertEqual(self.window.hotkey_fields['study'].text(),'F8')
    def test_add_alternative_and_escape_cancel(self):
        field=self.record();QTest.keyClick(field,Qt.Key.Key_F8);self.app.processEvents()
        field.begin_add();QTest.keyClick(field,Qt.Key.Key_Q,Qt.KeyboardModifier.ShiftModifier)
        QTest.keyRelease(field,Qt.Key.Key_Shift);self.app.processEvents()
        self.assertEqual(field.text(),'F8; Shift+Q')
        self.assertEqual(self.window.store.settings()['hotkeys']['study'],'F8; Shift+Q')
        self.assertIn('F8 (+1)',self.window.action_rows['study'].shortcut.text())
        field.begin_add();QTest.keyClick(field,Qt.Key.Key_Escape);self.app.processEvents()
        self.assertEqual(field.text(),'F8; Shift+Q')

    def test_duplicate_append_keeps_existing_alternatives(self):
        field=self.record();QTest.keyClick(field,Qt.Key.Key_F8);self.app.processEvents()
        field.begin_add();QTest.keyClick(field,Qt.Key.Key_F8);self.app.processEvents()
        self.assertEqual(field.text(),'F8')
        self.assertEqual(self.window.settings['hotkeys']['study'],'F8')
        self.assertFalse(self.window.hotkey_capture_active)

    def test_context_menu_starts_append_recording_without_replacing_first_key(self):
        self.window.show();self.app.processEvents()
        self.window.tabs.setCurrentIndex(next(i for i in range(self.window.tabs.count()) if self.window.tabs.list.item(i).text()=='Привязки'))
        field=self.window.hotkey_fields['study']
        from PySide6.QtWidgets import QMenu
        from PySide6.QtCore import QTimer
        menu=QMenu(field)
        def choose_add():menu.actions()[1].trigger();menu.close()
        QTimer.singleShot(0,choose_add)
        with patch('windowwords.ui.QMenu',return_value=menu):
            self.window.binding_menu(field,'study','keyboard',field.rect().center())
        self.assertTrue(field.recording and field.append_mode)
        QTest.keyClick(field,Qt.Key.Key_F8);self.app.processEvents()
        self.assertEqual(field.text(),'Alt+Q; F8')
        self.assertFalse(self.window.hotkey_capture_active)

    def test_remove_one_alternative_restarts_registration(self):
        field=self.window.hotkey_fields['study']
        self.window.record_hotkey('study','F8; Shift+Q');field.setText('F8; Shift+Q')
        previous=self.window.keys
        with patch('windowwords.shortcuts.QInputDialog.getItem',return_value=('F8',True)):
            self.window.remove_hotkey('study')
        self.assertEqual(field.text(),'Shift+Q')
        self.assertEqual(self.window.store.settings()['hotkeys']['study'],'Shift+Q')
        self.assertIsNot(self.window.keys,previous)
        self.assertEqual(previous.stopped,1)

    def test_tab_key_is_recorded_instead_of_moving_focus(self):
        field=self.record();QTest.keyClick(field,Qt.Key.Key_Tab);self.app.processEvents()
        self.assertEqual(field.text(),'Tab')
        self.assertEqual(self.window.settings['hotkeys']['study'],'Tab')

    def test_single_keys_released_in_main_and_card_and_active_on_frame(self):
        keys=Mock();self.window.keys=keys
        with patch.object(self.app,'applicationState',return_value=Qt.ApplicationState.ApplicationActive),\
             patch.object(self.app,'activeWindow',return_value=self.window):
            self.window.update_single_hotkeys();keys.set_single_enabled.assert_called_with(False)
        frame=self.snapshot()
        with patch.object(self.app,'applicationState',return_value=Qt.ApplicationState.ApplicationActive),\
             patch.object(self.app,'activeWindow',return_value=frame):
            self.window.update_single_hotkeys();keys.set_single_enabled.assert_called_with(True)
        with patch.object(self.app,'applicationState',return_value=Qt.ApplicationState.ApplicationActive),\
             patch.object(self.app,'activeWindow',return_value=self.window.card):
            self.window.update_single_hotkeys();keys.set_single_enabled.assert_called_with(False)
        with patch.object(self.app,'applicationState',return_value=Qt.ApplicationState.ApplicationInactive):
            self.window.update_single_hotkeys();keys.set_single_enabled.assert_called_with(True)
