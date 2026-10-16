import tempfile,unittest
from pathlib import Path
from windowwords.i18n import tr,trf,set_language
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup


class LanguageSettingsTests(unittest.TestCase):
    def tearDown(self):set_language('ru')

    def test_default_validation_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=Store(root/'source');target=Store(root/'target')
            settings=source.settings();self.assertEqual(settings['ui_language'],'ru')
            settings['ui_language']='en';source.save_settings(settings)
            export_backup(source,source.settings(),root/'backup.json');import_backup(target,root/'backup.json')
            self.assertEqual(target.settings()['ui_language'],'en')
            settings['ui_language']='unsupported';source.save_settings(settings)
            self.assertEqual(source.settings()['ui_language'],'ru')

    def test_translation_templates_and_user_content(self):
        from string import Formatter
        from windowwords.i18n_en import TRANSLATIONS
        set_language('en')
        self.assertEqual(tr('Настройки'),'Settings')
        self.assertEqual(tr('меч'),'меч')
        self.assertEqual(trf('Список обновлён · моделей: {0}',12),'Models refreshed: 12')
        for source,target in TRANSLATIONS.items():
            self.assertEqual(sorted(field for _,field,_,_ in Formatter().parse(source) if field is not None),
                             sorted(field for _,field,_,_ in Formatter().parse(target) if field is not None),source)

    def test_english_errors_keep_diagnostic_classification(self):
        from windowwords.diagnostics import Measurements
        set_language('en');metrics=Measurements()
        def fail(text):raise RuntimeError(tr(text))
        with self.assertRaises(RuntimeError):metrics.run('translate',lambda:fail('Достигнут лимит запросов.'))
        self.assertEqual(metrics.snapshot()['translate']['error_kind'],'limit')
        with self.assertRaises(RuntimeError):metrics.run('ocr',lambda:fail('Запрос больше не актуален.'))
        self.assertEqual(metrics.snapshot()['ocr']['errors'],0)


class LanguageUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_usability import UsabilityTests
        UsabilityTests.setUpClass();cls.app=UsabilityTests.app

    def test_english_navigation_help_and_content_after_restart(self):
        from unittest.mock import patch
        from tests.test_usability import Keys
        from windowwords.app import MainWindow
        from PySide6.QtWidgets import QLabel,QPushButton
        with tempfile.TemporaryDirectory() as folder,patch('windowwords.native.Hotkeys',Keys),patch('windowwords.controls.InputCapture'),patch('windowwords.safety.running_executables',return_value=set()):
            store=Store(Path(folder));window=MainWindow(store)
            try:
                for timer in (window.timer,window.profile_timer,window.diagnostic_timer,window.model_timer,window.safety_timer):timer.stop()
                self.assertEqual(window.tabs.list.item(0).text(),'Игровой экран')
                window.language_pick.setCurrentIndex(window.language_pick.findData('en'))
                self.assertEqual(store.settings()['ui_language'],'en')
                self.assertEqual(window.tabs.list.item(0).text(),'Игровой экран')
                store.save_word('sword','меч','He drew his sword.','')
            finally:window.close();window.deleteLater();self.app.processEvents()
            english=MainWindow(store)
            try:
                for timer in (english.timer,english.profile_timer,english.diagnostic_timer,english.model_timer,english.safety_timer):timer.stop()
                titles=[english.tabs.list.item(i).text() for i in range(english.tabs.count())]
                self.assertIn('Settings',titles);self.assertIn('Game screen',titles);self.assertIn('My words',titles)
                self.assertEqual(english.settings_tabs.tabText(0),'General')
                self.assertEqual(english.filter_pick.itemText(0),'Universal')
                self.assertEqual(english.theme_pick.itemText(0),'Aurora')
                english.tabs.setCurrentIndex(titles.index('Settings'));english.help.page()
                self.assertNotIn('Монитор',english.help.panel.text.text())
                self.assertIn('Monitor',english.help.panel.text.text())
                english.card.populate('sword','He drew his sword.','меч')
                self.assertEqual(english.card.term.text(),'sword')
                self.assertIn('меч',english.card.dictionary.toPlainText())
                self.assertEqual(english.settings['provider'],'yandex_web')
                self.assertEqual(english.settings['filter'],'raw')
                self.assertEqual(store.words()[0][2],'меч')
                english.language_pick.setCurrentIndex(english.language_pick.findData('ru'))
                self.assertEqual(store.settings()['ui_language'],'ru')
            finally:english.close();english.deleteLater();self.app.processEvents();set_language('ru')
