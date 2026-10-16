import sentencepiece,ctranslate2
import unittest
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QPushButton,QDialog,QMenu
from PySide6.QtTest import QTest
from tests import test_usability as usability

class InterfaceCleanupTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def select(self,title):
        self.window.tabs.setCurrentIndex(next(i for i in range(self.window.tabs.count()) if self.window.tabs.list.item(i).text()==title))

    def test_auto_parameters_open_without_unselected_region_capture_or_translation(self):
        window=self.window;window.show();self.app.processEvents()
        self.assertFalse(window.auto_options.content.isHidden())
        self.assertTrue(window.auto_options.toggle.isHidden())
        with patch.object(window,'task') as job:
            QTest.mouseClick(window.start_button,Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertTrue(window.auto_options.toggle.isChecked())
            self.assertFalse(window.auto_options.content.isHidden())
            self.assertFalse(window.running)
            self.assertIn('Выбери область',window.status.text())
            job.assert_not_called()
        self.assertEqual(window.action_rows['screen'].shortcut.text(),'Alt+V')

    def test_navigation_groups_settings_and_separates_bindings(self):
        window=self.window
        self.assertEqual([window.tabs.list.item(i).text() for i in range(window.tabs.count())],
                         ['Игровой экран','Перевод','Привязки','Мои слова','Повторение','История','Настройки'])
        self.assertEqual([window.settings_tabs.tabText(i) for i in range(window.settings_tabs.count())],
                         ['Общие','Распознавание','Оформление','Словари','Диагностика','Защита игр'])
        self.select('Настройки');window.show();self.app.processEvents()
        for i,widget in ((0,window.monitor_pick),(1,window.filter_pick),(2,window.ui_scale_pick),(3,window.dictionary_list),(4,window.diagnostic_text)):
            window.settings_tabs.setCurrentIndex(i);self.app.processEvents()
            self.assertTrue(widget.isVisible())
            self.assertEqual(window.settings_pages.currentWidget(),window.settings_pages.pages[i])
        window.settings_tabs.setCurrentIndex(3);window.help.page()
        self.assertIn('словари',window.help_panel.text.text())
        window.settings_tabs.setCurrentIndex(2);self.assertTrue(window.help_panel.isHidden())
        self.select('Игровой экран');QTest.mouseClick(window.connection_banner,Qt.MouseButton.LeftButton)
        self.assertEqual(window.tabs.list.currentItem().text(),'Перевод')
        self.select('Игровой экран');window.display_buttons['overlay'].click()
        self.assertEqual(window.store.settings()['game_mode'],'overlay')
        self.assertTrue(window.display_buttons['overlay'].isChecked())
        self.assertFalse(window.display_buttons['external'].isChecked())
        window.display_buttons['external'].click()
        self.assertEqual(window.store.settings()['game_mode'],'external')

    def test_binding_icons_and_descriptive_menu_preserve_other_devices(self):
        window=self.window;self.select('Привязки')
        self.assertTrue(all(not icon.pixmap().isNull() for icon in window.binding_icons.values()))
        self.assertFalse(any(b.text() in ('+','−','×') for b in window.device_panels.findChildren(QPushButton)))
        field=window.hotkey_fields['study'];window.record_hotkey('study','Mouse4','mouse')
        actions=[]
        menu=QMenu(field)
        def choose_clear():
            actions.extend(item.text() for item in menu.actions() if not item.isSeparator())
            menu.actions()[-1].trigger()
            menu.close()
        QTimer.singleShot(0,choose_clear)
        with patch('windowwords.ui.QMenu',return_value=menu):window.binding_menu(field,'study','keyboard',field.rect().center())
        self.assertEqual(actions,['Назначить сочетание','Добавить ещё сочетание','Удалить одно сочетание','Очистить привязки'])
        self.assertEqual(window.settings['hotkeys']['study'],'Mouse4')
        self.assertFalse(field.recording)

    def test_protection_action_and_resume_are_latched_until_game_exits(self):
        window=self.window
        self.select('Настройки');window.settings_tabs.setCurrentIndex(5);window.show();self.app.processEvents()
        self.assertTrue(window.safety_resume.isHidden())
        window.safety_action_pick.setCurrentIndex(window.safety_action_pick.findData('pause'))
        self.assertEqual(window.store.settings()['protection_action'],'pause')
        with patch('windowwords.safety.running_executables',return_value={'marvel.exe'}):
            window.check_game_protection();self.app.processEvents()
            self.assertTrue(window.safety_blocked);self.assertTrue(window.safety_resume.isVisible())
            self.assertFalse(window.safety_resume.isEnabled())
            QTest.mouseClick(window.safety_resume,Qt.MouseButton.LeftButton)
            self.assertTrue(window.safety_blocked)
        window.check_game_protection()
        self.assertTrue(window.safety_blocked);self.assertTrue(window.safety_resume.isEnabled())
        QTest.mouseClick(window.safety_resume,Qt.MouseButton.LeftButton)
        self.assertFalse(window.safety_blocked);self.assertFalse(window.running)
        self.assertTrue(window.safety_resume.isHidden())
        window.safety_action_pick.setCurrentIndex(window.safety_action_pick.findData('quit'))
        self.assertEqual(window.store.settings()['protection_action'],'quit')

    def test_protection_game_picker_stores_name_and_deduplicates(self):
        window=self.window
        with patch('windowwords.process_picker.ProcessPicker') as picker:
            picker.return_value.exec.return_value=QDialog.DialogCode.Accepted
            picker.return_value.selected_exe='game.exe'
            window.add_protected_game();window.add_protected_game()
            picker.return_value.confirm.setText.assert_called_with('Добавить')
        names=[window.protected_list.item(i).text() for i in range(window.protected_list.count())]
        self.assertEqual(names.count('game.exe'),1)
        self.assertIn('game.exe',window.store.settings()['protected_games'])
        self.assertFalse(hasattr(window,'safety_pause'))
