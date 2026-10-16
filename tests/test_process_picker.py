import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QDialog
from windowwords.process_picker import ProcessPicker
from tests import test_usability as usability

class ProcessPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_processes_grouped_searchable_and_refresh_keeps_selection(self):
        with patch('windowwords.process_picker.process_snapshot',return_value={1:'System',2:'GAME.EXE',3:'game.exe',4:'browser.exe'}) as snapshot:
            dialog=ProcessPicker(None)
            self.assertEqual(dialog.list.count(),2)
            dialog.list.setCurrentRow(1);self.assertTrue(dialog.confirm.isEnabled())
            self.assertEqual(dialog.list.currentItem().data(Qt.ItemDataRole.UserRole),'game.exe')
            dialog.refresh();self.assertEqual(dialog.list.currentItem().data(Qt.ItemDataRole.UserRole),'game.exe')
            dialog.search.setText('browser');self.assertFalse(dialog.confirm.isEnabled())
            dialog.choose();self.assertEqual(dialog.selected_exe,'')
            dialog.list.setCurrentRow(0);dialog.choose();self.assertEqual(dialog.selected_exe,'browser.exe')
            dialog.close()
    def test_snapshot_failure_stays_cancelable_and_file_is_fallback(self):
        with patch('windowwords.process_picker.process_snapshot',side_effect=OSError):
            dialog=ProcessPicker(None);self.assertFalse(dialog.confirm.isEnabled())
            self.assertIn('Не удалось',dialog.status.text())
            with patch('windowwords.process_picker.QFileDialog.getOpenFileName',return_value=(r'Z:\Games\Game.EXE','')):dialog.choose_file()
            self.assertEqual(dialog.selected_exe,'game.exe');dialog.close()

class ProcessBindingUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown
    def test_binding_chosen_process_without_existing_game_name(self):
        dialog=Mock(selected_exe='demo-game.exe');dialog.exec.return_value=QDialog.DialogCode.Accepted
        with patch('windowwords.process_picker.ProcessPicker',return_value=dialog):self.window.bind_game()
        self.assertEqual(self.window.game.text(),'demo-game')
        self.assertEqual(self.window.settings['profile_apps'],{'demo-game.exe':'demo-game'})
        self.assertIn('demo-game',self.window.settings['profiles'])
        self.assertEqual(self.window.store.settings()['game'],'demo-game')
