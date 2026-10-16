import sentencepiece,ctranslate2
import unittest,tempfile,sqlite3
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from windowwords import native
from windowwords.storage import Store,Dictionary,base_dir
from windowwords.app import MainWindow,STYLE
from windowwords.core import Box,Line
from windowwords.screen import Tracker
from build_wiktionary import convert

class FakeKeys:
    def __init__(self,callback,failure,bindings=None,allow=True):self.allow=allow;self.escape=False
    def start(self):pass
    def stop(self):pass
    def join(self,**kwargs):pass
    def set_escape(self,value):self.escape=value and self.allow

class GameModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch('windowwords.native.Hotkeys',FakeKeys)
        self.patch.start()
        self.process_patch=patch('windowwords.safety.running_executables',return_value=set())
        self.process_patch.start()
        self.app.setStyleSheet(STYLE)
        self.window=MainWindow(Store(Path(self.temp.name)))
        self.window.timer.stop()

    def tearDown(self):
        self.window.close();self.app.processEvents()
        self.patch.stop();self.temp.cleanup()
        self.process_patch.stop()

    def test_new_profile_defaults_to_external_window_without_hook(self):
        self.assertEqual(self.window.settings['game_mode'],'external')
        self.assertFalse(self.window.keys.allow)
        self.window.begin_session()
        self.assertFalse(self.window.keys.escape)
        self.assertFalse(self.window.card.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertFalse(self.window.screen_render.isEnabled())
        self.assertFalse(self.window.render_settings_group.isHidden())

    def test_external_translation_does_not_render_overlay(self):
        self.window.region=Box(0,0,900,300)
        self.window.running=True
        self.window.screen_tracks=Tracker()
        self.window.screen_tracks.update([Line('Open',Box(10,20,50,20),())],0,instant=True)
        self.window.screen_tracks.remember(['Open'],['Открыть'])
        self.window.overlay.display_segments=Mock()
        with patch('windowwords.native.exclude_capture',return_value=True):self.window.draw_screen()
        self.window.overlay.display_segments.assert_not_called()
        self.assertTrue(self.window.result_window.isVisible())
        self.assertIn('Открыть',self.window.result_window.content.toPlainText())
        self.assertFalse(self.window.result_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_mode_switch_closes_windows_and_replaces_hook_policy(self):
        self.window.game_mode_pick.setCurrentIndex(self.window.game_mode_pick.findData('overlay'))
        self.assertTrue(self.window.keys.allow)
        self.assertFalse(self.window.render_settings_group.isHidden())
        self.window.begin_session()
        self.window.game_mode_pick.setCurrentIndex(self.window.game_mode_pick.findData('external'))
        self.assertFalse(self.window.session_active)
        self.assertFalse(self.window.keys.allow)
        self.assertFalse(self.window.overlay.isVisible())

    def test_external_capture_opens_normal_window(self):
        from PIL import Image
        self.window.begin_session()
        self.window.show_freeze(Image.new('RGB',(500,300)),self.window.monitor,'region')
        flags=self.window.freeze.windowFlags()
        self.assertFalse(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(flags & Qt.WindowType.WindowType_Mask,Qt.WindowType.Window)

    def test_resized_capture_preserves_aspect_and_maps_selection_to_pixels(self):
        from PIL import Image
        from PySide6.QtCore import QPointF
        from windowwords.widgets import Freeze
        frame=Freeze(Image.new('RGB',(1000,500)),self.window.monitor,'region')
        frame.resize(600,600)
        rect=frame.image_rect()
        self.assertEqual((rect.x(),rect.y(),rect.width(),rect.height()),(0,150,600,300))
        self.assertEqual(frame.image_point(QPointF(60,180)),(100,50))
        frame.close()

    def test_help_starts_hidden_and_shows_when_selected(self):
        self.assertFalse(self.window.help_panel.isVisible())
        self.window.show()
        self.window.tabs.setCurrentIndex(next(i for i in range(self.window.tabs.count()) if self.window.tabs.list.item(i).text()=='Настройки'))
        self.window.settings_tabs.setCurrentIndex(2)
        self.window.ui_scale_pick.setFocus()
        self.app.processEvents()
        self.assertFalse(self.window.help_panel.isHidden())
        self.assertIn('размер',self.window.help_panel.text.text())

class NativePolicyTests(unittest.TestCase):
    def test_stopped_worker_cannot_install_hook_after_mode_switch(self):
        keys=native.Hotkeys(lambda _:None,lambda _:None,{'study':'Ctrl+Alt+Shift+F24'},True)
        keys.stop()
        with patch.object(native.user,'SetWindowsHookExW') as hook,patch.object(native.user,'RegisterHotKey') as register:
            keys.run()
        hook.assert_not_called()
        register.assert_not_called()
        self.assertTrue(keys.ready.is_set())

    def test_external_hotkeys_never_install_global_keyboard_hook(self):
        keys=native.Hotkeys(lambda _:None,lambda _:None,{'study':'Ctrl+Alt+Shift+F24'},False)
        with patch.object(native.user,'PeekMessageW'),patch.object(native.user,'RegisterHotKey',return_value=True),\
             patch.object(native.user,'GetMessageW',return_value=0),patch.object(native.user,'UnregisterHotKey'),\
             patch.object(native.user,'SetWindowsHookExW') as hook:
            keys.run()
            keys.set_escape(True)
        hook.assert_not_called()
        self.assertFalse(keys.hook_installed)
        self.assertFalse(keys.escape_gate.enabled)

class WiktionaryTests(unittest.TestCase):
    def test_default_dictionary_update_preserves_words_and_subsequent_choices(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));settings=store.settings()
            self.assertEqual(settings['dictionary_enabled'],['wiktionary','personal'])
            store.save_word('sword','меч','','')
            settings.update(dictionary_revision=1,dictionary_enabled=['wiktionary','freedict','wordnet','personal'])
            store.save_settings(settings)
            migrated=store.settings()
            self.assertEqual(migrated['dictionary_enabled'],['wiktionary','personal'])
            self.assertEqual(store.words()[0][1:3],('sword','меч'))
            migrated['dictionary_enabled']=['wiktionary','freedict','wordnet','personal']
            store.save_settings(migrated)
            self.assertEqual(store.settings()['dictionary_enabled'],migrated['dictionary_enabled'])

    def test_custom_dictionary_selection_survives_default_update(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));settings=store.settings()
            settings.update(dictionary_revision=1,dictionary_enabled=['wordnet','personal','custom-example'])
            store.save_settings(settings)
            self.assertEqual(store.settings()['dictionary_enabled'],settings['dictionary_enabled'])

    def test_actual_offline_dictionary_handles_inflected_form_and_game_term(self):
        wiki=Dictionary(base_dir()/'data/wiktionary.sqlite3')
        self.assertIn('камзол',wiki.lookup('jerkin'))
        self.assertIn('идти',wiki.lookup('went'))
        self.assertIn('Источник:',wiki.lookup('sword'))
        self.assertEqual(wiki.lookup("' OR 1=1 --"),'')

    def test_parser_keeps_russian_meaning_and_example_but_no_other_language(self):
        item={'lang_code':'en','word':'jerkin','pos':'noun','senses':[{'glosses':['камзол'],
              'examples':[{'text':'A leather jerkin.','translation':'Кожаный камзол.'}]}],'forms':[{'form':'jerkins'}]}
        term,meaning,forms=convert(item)
        self.assertIn('Кожаный камзол.',meaning)
        self.assertIn('jerkins',forms)
        self.assertIsNone(convert(dict(item,lang_code='ru')))

    def test_migration_preserves_disabled_dictionary_after_first_upgrade(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder))
            settings=store.settings()
            settings.pop('dictionary_revision')
            settings['dictionary_enabled']=['personal']
            store.save_settings(settings)
            upgraded=store.settings()
            self.assertEqual(upgraded['dictionary_enabled'],['wiktionary','personal'])
            upgraded['dictionary_enabled']=['personal']
            store.save_settings(upgraded)
            self.assertEqual(store.settings()['dictionary_enabled'],['personal'])
