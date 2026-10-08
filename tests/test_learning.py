import sentencepiece,ctranslate2
import tempfile,unittest,json,zipfile,io
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from windowwords.storage import Store
from windowwords.learning import ReviewPage
from windowwords.diagnostics import Measurements,diagnosis
from windowwords.backup import export_backup,import_backup
from windowwords.speech import Speaker
from windowwords.app import MainWindow
from tests.test_usability import Keys
from installer import install_payload

class StoreLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=Store(self.root/'profile')
        self.store.save_word('sword','меч','A sword.','Witcher')
        self.ident=self.store.words()[0][0]
    def tearDown(self):self.temp.cleanup()
    def test_old_words_are_due_and_answers_schedule_persistently(self):
        self.assertEqual(self.store.due_words(now=1000)[0][0],self.ident)
        self.assertTrue(self.store.review_word(self.ident,True,now=1000))
        self.assertFalse(self.store.due_words(now=1001))
        reopened=Store(self.root/'profile')
        self.assertEqual(len(reopened.due_words(now=87400)),1)
        reopened.review_word(self.ident,False,now=90000)
        self.assertFalse(reopened.due_words(now=90599))
        self.assertEqual(len(reopened.due_words(now=90600)),1)
    def test_delete_and_edit_clean_progress_without_orphans(self):
        self.store.review_word(self.ident,True,now=1000)
        self.store.edit_word(self.ident,'sword','меч','A new sword.','Witcher')
        self.assertEqual(len(self.store.due_words(now=1001)),1)
        self.store.review_word(self.ident,True,now=1000)
        self.store.delete_word(self.ident)
        self.assertFalse(self.store.review_word(self.ident,False))
        with self.store.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],0)
    def test_backup_round_trip_merges_words_and_preserves_credentials_and_progress(self):
        self.store.vault.set('api_key','PRIVATE_TEST_KEY')
        settings=self.store.settings()
        settings['host_id']='PRIVATE_HOST'
        self.store.review_word(self.ident,True)
        path=self.root/'backup.json'
        export_backup(self.store,settings,path)
        raw=path.read_text(encoding='utf-8')
        self.assertNotIn('PRIVATE_TEST_KEY',raw);self.assertNotIn('PRIVATE_HOST',raw)
        destination=Store(self.root/'other')
        destination.vault.set('api_key','ANOTHER_KEY')
        destination.save_word('boot','сапог','A boot.','Witcher')
        import_backup(destination,path);import_backup(destination,path)
        self.assertEqual(len(destination.words()),2)
        self.assertEqual(destination.review_stats()[1],1)
        self.assertEqual(destination.vault.read()['api_key'],'ANOTHER_KEY')
    def test_invalid_backup_never_changes_settings_or_words(self):
        path=self.root/'bad.json'
        export_backup(self.store,self.store.settings(),path)
        data=json.loads(path.read_text(encoding='utf-8'))
        data['settings']['profiles']={'bad':{'game_mode':'overlay'}}
        path.write_text(json.dumps(data),encoding='utf-8')
        before=(self.store.folder/'settings.json').read_bytes()
        with self.assertRaises(ValueError):import_backup(self.store,path)
        self.assertEqual((self.store.folder/'settings.json').read_bytes(),before)
        self.assertEqual(len(self.store.words()),1)

class LearningWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_translation_hidden_until_reveal_and_rating_advances_once(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));store.save_word('jerkin','камзол','His jerkin.','Witcher')
            page=ReviewPage(store)
            page.start()
            self.assertEqual(page.answer.toPlainText(),'')
            self.assertFalse(page.known.isEnabled())
            page.rate(True)
            self.assertEqual(store.review_stats()[1],1)
            page.reveal();self.assertEqual(page.answer.toPlainText(),'камзол')
            page.rate(True);page.rate(True)
            self.assertEqual(page.completed,1)
            self.assertIsNone(page.current)
            self.assertEqual(store.review_stats()[1],0)
            page.close()

class FeaturesUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.keys=patch('windowwords.native.Hotkeys',Keys);self.keys.start()
        self.window=MainWindow(Store(Path(self.temp.name)))
        self.window.timer.stop();self.window.hover_timer.stop();self.window.profile_timer.stop();self.window.diagnostic_timer.stop()
    def tearDown(self):
        self.window.close();self.app.processEvents();self.keys.stop();self.temp.cleanup()
    def test_auto_card_is_explicit_and_avoids_saved_or_already_translated_cards(self):
        self.window.task=Mock()
        self.window.show_card('sword','A sword.')
        self.assertFalse(self.window.auto_translate_timer.isActive())
        self.window.set_feature('auto_translate_card',True)
        self.window.auto_translate_current()
        self.assertTrue(self.window.auto_card_inflight)
        self.assertEqual(self.window.task.call_count,1)
        self.window.auto_translate_current()
        self.assertEqual(self.window.task.call_count,1)
        self.window.auto_card_inflight=False
        self.window.card.answer.setPlainText('меч')
        self.window.auto_translate_current()
        self.assertEqual(self.window.task.call_count,1)
    def test_late_auto_translation_cannot_overwrite_current_card(self):
        pending=[]
        self.window.task=lambda function,done,failed=None:pending.append((done,failed))
        self.window.settings['auto_translate_card']=True
        self.window.show_card('sword','A sword.')
        self.window.auto_translate_current()
        self.window.show_card('boot','A boot.')
        pending[0][0](('меч','test'))
        self.assertEqual(self.window.card.answer.toPlainText(),'')
        self.assertFalse(self.window.auto_card_inflight)
        self.assertTrue(self.window.auto_translate_timer.isActive())
    def test_auto_profile_requires_stable_foreground_and_never_interrupts_translation(self):
        self.window.save_profile()
        game=self.window.game.text()
        self.window.settings.update(auto_profiles=True,profile_apps={'witcher3.exe':game})
        with patch('windowwords.native.foreground_executable',return_value='witcher3.exe'),patch.object(self.window,'apply_profile') as apply:
            self.window.detect_profile();apply.assert_not_called()
            self.window.detect_profile();apply.assert_called_once_with(game)
            self.window.detect_profile();apply.assert_called_once()
            self.window.profile_last='';self.window.running=True
            self.window.detect_profile();apply.assert_called_once()
    def test_editing_english_input_invalidates_pending_auto_translation(self):
        pending=[]
        self.window.task=lambda function,done,failed=None:pending.append(done)
        self.window.settings['auto_translate_card']=True
        self.window.show_card('sword','A sword.')
        self.window.auto_translate_current()
        self.window.card.term.setText('boot')
        self.window.card.term.textEdited.emit('boot')
        pending[0](('меч','test'))
        self.assertEqual(self.window.card.answer.toPlainText(),'')
    def test_profile_restores_card_and_ocr_but_cannot_change_provider_or_hook_mode(self):
        self.window.save_profile()
        name=self.window.game.text()
        profile=self.window.settings['profiles'][name]
        profile.update(card_width=700,filter='yellow',provider='api',game_mode='overlay')
        self.window.apply_profile(name)
        self.assertEqual(self.window.settings['provider'],'google_web')
        self.assertTrue(self.window.external_mode())
        self.assertEqual(self.window.card_width_pick.value(),700)
        self.assertEqual(self.window.settings['filter'],'yellow')
    def test_report_contains_no_texts_credentials_or_executable_paths(self):
        self.window.store.vault.set('api_key','DO_NOT_REPORT')
        self.window.game.setText('PRIVATE_GAME')
        self.window.settings['profile_apps']={'PRIVATE_PATH.exe':'PRIVATE_GAME'}
        self.window.measurements.run('ocr',lambda:'PRIVATE_TEXT')
        report=json.dumps(self.window.report())
        for value in ('DO_NOT_REPORT','PRIVATE_GAME','PRIVATE_TEXT','PRIVATE_PATH'):self.assertNotIn(value,report)

class DiagnosticsTests(unittest.TestCase):
    def test_failures_are_counted_without_recording_messages(self):
        measurements=Measurements()
        with self.assertRaises(RuntimeError):
            measurements.run('translate',lambda:(_ for _ in ()).throw(RuntimeError('429 SECRET_URL')))
        rows=measurements.snapshot()
        self.assertEqual(rows['translate']['errors'],1)
        self.assertNotIn('SECRET_URL',json.dumps(rows))
        self.assertIn('лимита',diagnosis(rows))

class InstallerTests(unittest.TestCase):
    def test_install_is_idempotent_and_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'payload.zip'
            with zipfile.ZipFile(archive,'w') as package:
                package.writestr('Lexora-0.6.1/Lexora.exe',b'fake-exe')
                package.writestr('Lexora-0.6.1/data/dictionary.sqlite3',b'dictionary')
            destination=root/'installed'
            install_payload(archive,destination);install_payload(archive,destination)
            self.assertEqual((destination/'Lexora.exe').read_bytes(),b'fake-exe')
            with zipfile.ZipFile(archive,'w') as package:package.writestr('Lexora-0.6.1/../outside',b'bad')
            with self.assertRaises(ValueError):install_payload(archive,root/'bad')
            self.assertFalse((root/'outside').exists())
