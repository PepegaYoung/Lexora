import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtTest import QTest
from tests import test_usability as usability
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup


class StableGameScreenTests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_modes_keep_controls_visible_and_keep_their_geometry(self):
        w=self.window;w.show();w.help.dismiss();QTest.qWait(80)
        widgets=[w.capture_buttons['region'],w.card_options,w.auto_options,w.render_settings_group,
                 *w.scope_buttons.values(),*w.render_buttons.values(),*w.display_buttons.values()]
        def bounds():return [(item.mapTo(w,item.rect().topLeft()).toTuple(),item.size().toTuple()) for item in widgets]
        initial=bounds()
        for scope in ('monitor','region'):
            for render in ('above','replace'):
                for display in ('overlay','external'):
                    w.scope_buttons[scope].click();w.render_buttons[render].click();w.display_buttons[display].click();QTest.qWait(40)
                    self.assertTrue(all(item.isVisible() for item in widgets))
                    self.assertEqual(bounds(),initial)
                    self.assertEqual(w.store.settings()['screen_scope'],scope)
                    self.assertEqual(w.store.settings()['screen_mode'],render)
                    self.assertEqual(w.store.settings()['game_mode'],display)
        self.assertFalse(hasattr(w,'auto_start_region'))


class ScaleMigrationTests(unittest.TestCase):
    def test_legacy_autostart_is_ignored_in_settings_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=Store(root/'source');target=Store(root/'target')
            settings=source.settings();settings['auto_start_region']=True
            (source.folder/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
            self.assertNotIn('auto_start_region',source.settings())
            export_backup(source,source.settings(),root/'backup.json')
            data=json.loads((root/'backup.json').read_text());data['settings']['auto_start_region']=True
            (root/'backup.json').write_text(json.dumps(data),encoding='utf-8')
            imported,_=import_backup(target,root/'backup.json')
            self.assertNotIn('auto_start_region',imported)
            self.assertNotIn('auto_start_region',target.settings())

    def test_legacy_120_becomes_100_once_and_keeps_words(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory));store.save_word('sword','меч','','')
            settings=store.settings();settings.pop('ui_scale_revision');settings['ui_scale']=120
            store.save_settings(settings)
            migrated=store.settings();self.assertEqual(migrated['ui_scale'],100)
            self.assertEqual(migrated['ui_scale_revision'],1)
            store.save_settings(migrated)
            self.assertEqual(store.settings()['ui_scale'],100)
            self.assertEqual(store.words()[0][1],'sword')

    def test_new_backup_round_trip_keeps_new_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=Store(root/'source');target=Store(root/'target')
            settings=source.settings();settings['ui_scale']=130
            export_backup(source,settings,root/'backup.json');import_backup(target,root/'backup.json')
            self.assertEqual(target.settings()['ui_scale'],130)

    def test_legacy_backup_uses_new_scale_without_changing_other_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=Store(root/'source');target=Store(root/'target')
            settings=source.settings();export_backup(source,settings,root/'backup.json')
            data=json.loads((root/'backup.json').read_text());data['settings'].pop('ui_scale_revision');data['settings']['ui_scale']=120
            (root/'backup.json').write_text(json.dumps(data),encoding='utf-8')
            import_backup(target,root/'backup.json')
            self.assertEqual(target.settings()['ui_scale'],100)
            self.assertEqual(target.settings()['provider'],settings['provider'])
