"""Imported content remains text at each rich-text-capable UI boundary."""
import json,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QTextDocument
from PySide6.QtWidgets import QLabel
from windowwords.backup import import_backup
from windowwords.i18n import tr
from tests import test_usability as usability


class ResourceProbe(QTextDocument):
    def __init__(self):
        super().__init__();self.requests=[]

    def loadResource(self,kind,url):
        self.requests.append(url.toString())
        return QImage(1,1,QImage.Format.Format_ARGB32)


class LiteralTextTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def restore(self,settings=None,words=None):
        path=self.window.store.folder/'literal-text-backup.json'
        path.write_text(json.dumps({'format':'lexora-backup','version':1,
            'settings':settings or {},'words':words or [],'reviews':[]}),encoding='utf-8')
        settings,_=import_backup(self.window.store,path)
        self.window.settings=settings
        self.window.refresh_library()
        return settings

    def tooltip_document(self,text):
        doc=ResourceProbe();doc.setHtml(text);doc.documentLayout().documentSize()
        return doc

    def test_imported_tooltips_are_literal_in_every_column(self):
        fields=['<img src="literal-image.png">','<b>меч & "щит"</b>',
                'First line\nВторая строка <img src="literal&#45;image.png">',
                '<i>Game</i>','<img src="literal-date.png">']
        self.restore(words=[[1,*fields]])
        record=self.window.store.words()[0]
        self.assertEqual(list(record[1:]),fields)
        for column,value in enumerate(fields):
            with self.subTest(column=column):
                item=self.window.word_list.item(0,column)
                self.assertEqual(item.data(Qt.ItemDataRole.UserRole),record)
                doc=self.tooltip_document(item.toolTip())
                self.assertEqual(doc.toPlainText(),value)
                self.assertEqual(doc.requests,[])
        # Check that the probe really detects an image request, without opening a file.
        control=self.tooltip_document('<img src="literal-control.png">')
        self.assertTrue(control.requests)

    def test_imported_binding_is_literal_even_with_encoded_separators(self):
        exe='<img src="literal&#47;image.png">.exe'
        game='Game <b>one & two</b>'
        self.restore({'game':game,'profiles':{game:{}},'profile_apps':{exe:game}})
        self.window.game.setText(game)
        self.assertEqual(self.window.profile_binding.textFormat(),Qt.TextFormat.PlainText)
        self.assertEqual(self.window.profile_binding.text(),tr('Привязка: ')+exe)
        self.assertEqual(self.window.store.settings()['profile_apps'],{exe:game})

    def test_imported_profile_save_load_and_bind_messages_remain_literal(self):
        game='<img src="literal-profile.png"> & "Игра"'
        settings=self.restore({'game':game})
        self.window.game.setText(settings['game'])
        self.window.save_profile()
        self.assertEqual(self.window.status.textFormat(),Qt.TextFormat.PlainText)
        self.assertEqual(self.window.status.text(),tr('Профиль сохранён: ')+game)
        self.window.apply_profile(game)
        self.assertEqual(self.window.status.text(),tr('Профиль загружен: ')+game)
        from PySide6.QtWidgets import QDialog
        with patch('windowwords.process_picker.ProcessPicker') as picker:
            picker.return_value.exec.return_value=QDialog.DialogCode.Accepted
            picker.return_value.selected_exe='example.exe'
            self.window.bind_game()
        self.assertEqual(self.window.status.textFormat(),Qt.TextFormat.PlainText)
        self.assertEqual(self.window.status.text(),tr('Профиль привязан: ')+'example.exe → '+game)

    def test_shared_message_copy_and_normal_multiline_words_are_preserved(self):
        self.window.region_status=QLabel()
        text='Ready <b>literally</b> & "готово"'
        self.window.message(text)
        for label in (self.window.status,self.window.region_status):
            self.assertEqual(label.textFormat(),Qt.TextFormat.PlainText)
            self.assertEqual(label.text(),tr(text))
        fields=['sword','меч & щит','He drew his sword.\nОн достал меч.','Example','2026-10-16T12:00:00']
        self.restore(words=[[1,*fields]])
        self.assertEqual(self.window.word_list.item(0,0).text(),'sword')
        self.assertEqual(self.tooltip_document(self.window.word_list.item(0,2).toolTip()).toPlainText(),fields[2])
        self.assertEqual(self.window.word_list.item(0,4).text(),'16.10.2026')
