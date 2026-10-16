import sentencepiece,ctranslate2
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from tests import test_usability as usability


class CompactListTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def words_page(self):
        window=self.window
        window.tabs.setCurrentIndex(next(i for i in range(window.tabs.count()) if window.tabs.list.item(i).text()=='Мои слова'))
        window.show();self.app.processEvents()

    def test_search_by_translation_preserves_id_and_opens_full_record(self):
        window=self.window
        window.store.save_word('sword','меч','He drew his sword.','Example')
        ident=window.store.words()[0][0]
        window.store.save_word('quest','задание','A new quest awaits.','')
        window.refresh_library();self.words_page()
        window.search.setText('меч');self.app.processEvents()
        self.assertEqual(window.word_list.count(),1)
        self.assertEqual(window.selected_record(),ident)
        with patch.object(window,'show_card') as show:
            window.open_saved();show.assert_called_once_with('sword','He drew his sword.')
        self.assertEqual(window.card.saved_id,ident)
        self.assertEqual(window.card.answer.toPlainText(),'меч')
        self.assertEqual(window.card.saved_game,'Example')
        window.search.clear();window.refresh_library()
        self.assertEqual(window.selected_record(),ident)
        self.assertEqual(window.word_count.text(),'2')

    def test_table_cell_selection_preserves_record_and_delete_clears_empty_actions(self):
        window=self.window
        for term in ('sword','quest'):window.store.save_word(term,'перевод','A short example sentence.','')
        window.refresh_library();self.words_page()
        view=window.word_list
        self.assertEqual([view.horizontalHeaderItem(i).text() for i in range(5)],
                         ['Слово','Перевод','Контекст','Игра','Дата'])
        self.assertEqual(view.item(0,2).text(),'A short example sentence.')
        view.setCurrentCell(1,3);self.app.processEvents()
        self.assertEqual(window.selected_record(),view.item(1,0).data(Qt.ItemDataRole.UserRole)[0])
        self.assertEqual(view.rowHeight(0),view.rowHeight(1))
        self.assertEqual(view.horizontalScrollBar().maximum(),0)
        with patch('windowwords.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
            window.delete_saved();window.delete_saved()
        self.assertFalse(window.store.words())
        self.assertIsNone(window.selected_record())
        self.assertTrue(window.words_empty.isVisible())
        self.assertTrue(all(not button.isEnabled() for button in window.word_buttons))

    def test_shortcut_buttons_remain_equal_after_bind_and_scale_change(self):
        window=self.window
        window.record_hotkey('study','Ctrl+Shift+F12','keyboard')
        window.ui_scale_pick.setValue(150);window.apply_appearance();window.show();self.app.processEvents()
        buttons=(window.capture_buttons['study'],window.snapshot_button,window.start_button)
        self.assertEqual(len({(b.width(),b.height()) for b in buttons}),1)
        self.assertTrue(all(b.caption.isHidden() for b in buttons))
        self.assertEqual(window.capture_buttons['study'].shortcut.text(),'Ctrl+Shift+F12')
        self.assertIn('Выбрать слово',window.capture_buttons['study'].accessibleName())
        with patch.object(window,'task') as task:
            QTest.mouseClick(window.start_button,Qt.MouseButton.LeftButton)
            self.app.processEvents();task.assert_not_called()
        self.assertFalse(window.running)
        self.assertFalse(window.start_button.isChecked())
