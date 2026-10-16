import sentencepiece,ctranslate2
import tempfile,unittest,json
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QRect,QPointF,QPoint,QEvent
from PySide6.QtGui import QMouseEvent,QWheelEvent
from PySide6.QtTest import QTest
from pathlib import Path
from windowwords.storage import Store,APPEARANCE_DEFAULTS
from windowwords.controls import ClickSlider
from windowwords.backup import export_backup,import_backup
from windowwords.themes import THEMES,stylesheet,contrast_ratio
from tests import test_usability as usability

class ThemePersistenceTests(unittest.TestCase):
    def test_all_themes_survive_settings_and_backup_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=Store(root/'source');target=Store(root/'target')
            for theme in THEMES:
                settings=source.settings();settings['theme']=theme;source.save_settings(settings)
                self.assertEqual(source.settings()['theme'],theme)
                export_backup(source,settings,root/'backup.json');import_backup(target,root/'backup.json')
                self.assertEqual(target.settings()['theme'],theme)
    def test_replacement_does_not_recolor_previous_replacement(self):
        self.assertEqual(stylesheet('color:#7de0cc; background:#247d74','light'),'color:#247d74; background:#247d74')
    def test_reference_palettes_keep_text_readable_across_gradients(self):
        for key,colors in THEMES.items():
            if 'gradient' not in colors:continue
            with self.subTest(theme=key):
                for background in colors['gradient']:
                    self.assertGreaterEqual(contrast_ratio(colors['text'],background),4.5)
                    self.assertGreaterEqual(contrast_ratio(colors['muted'],background),4.5)
                    self.assertGreaterEqual(contrast_ratio(colors['accent'],background),4.5)
                self.assertGreaterEqual(contrast_ratio(colors['accent'],colors['selected']),4.5)
                self.assertGreaterEqual(contrast_ratio('#ffffff',colors['primary']),4.5)

class ThemeUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown
    def test_all_palettes_apply_to_main_and_translucent_card(self):
        window=self.window
        self.assertEqual(window.theme_pick.count(),len(THEMES))
        for key,palette in THEMES.items():
            window.theme_pick.setCurrentIndex(window.theme_pick.findData(key));window.apply_appearance()
            self.assertEqual(window.store.settings()['theme'],key)
            self.assertEqual(window.card.card_surface.name(),palette['bg'])
            self.assertEqual(window.card.light,palette['light'])
            self.assertEqual(window.card.background_alpha,window.settings['card_background'])
            self.assertIn(palette['accent'],self.app.styleSheet())

    def test_card_theme_stays_independent_and_can_follow_app_again(self):
        window=self.window
        window.card_theme_pick.setCurrentIndex(window.card_theme_pick.findData('warm'));window.apply_appearance()
        window.theme_pick.setCurrentIndex(window.theme_pick.findData('velvet'));window.apply_appearance()
        self.assertEqual(window.card.theme_key,'warm')
        self.assertEqual(window.store.settings()['card_theme'],'warm')
        window.card_theme_pick.setCurrentIndex(0);window.apply_appearance()
        self.assertEqual(window.card.theme_key,'velvet')

    def test_window_presets_fit_small_monitor_and_reset_to_720p(self):
        window=self.window;window.show();self.app.processEvents()
        area=QRect(0,0,1280,720)
        with patch.object(window,'screen',return_value=Mock(availableGeometry=lambda:area)):
            for key in ('1080p','1440p','720p'):
                window.window_size_pick.setCurrentIndex(window.window_size_pick.findData(key));window.apply_appearance()
                self.app.processEvents()
                self.assertTrue(area.contains(window.frameGeometry()),(key,window.frameGeometry()))
                self.assertEqual(window.store.settings()['window_preset'],key)
            window.resize(1000,620);self.app.processEvents()
            self.assertEqual(window.window_size_pick.currentData(),'custom')
            window.reset_window_size();self.app.processEvents()
            self.assertEqual(window.store.settings()['window_preset'],'720p')

    def test_window_size_selection_applies_immediately_and_survives_reapply(self):
        window=self.window;window.show();self.app.processEvents()
        window.resize(950,620);self.app.processEvents()
        before=window.size()
        window.window_size_pick.setCurrentIndex(window.window_size_pick.findData('1080p'));self.app.processEvents()
        self.assertNotEqual(window.size(),before)
        self.assertEqual(window.store.settings()['window_preset'],'1080p')
        self.assertEqual(window.window_size_pick.currentData(),'1080p')
        applied=window.size();window.apply_appearance();self.app.processEvents()
        self.assertEqual(window.size(),applied)
        window.window_size_pick.setCurrentIndex(window.window_size_pick.findData('720p'));self.app.processEvents()
        self.assertLess(window.width(),applied.width())

    def test_card_aurora_paints_gradient_and_standard_retains_flat_background(self):
        window=self.window;card=window.card
        window.card_background_pick.setValue(100)
        window.card_theme_pick.setCurrentIndex(window.card_theme_pick.findData('ocean'))
        self.assertEqual(card.theme_key,'ocean')
        window.card_theme_pick.setCurrentIndex(window.card_theme_pick.findData('aurora'))
        self.assertEqual(card.theme_key,'aurora')
        self.assertIsNotNone(card.surface_brush.gradient())
        self.assertEqual([color.name() for _,color in card.surface_brush.gradient().stops()],list(THEMES['aurora']['gradient']))
        card.show();self.app.processEvents();image=card.grab().toImage()
        self.assertNotEqual(image.pixelColor(3,80).name(),image.pixelColor(card.width()-4,card.height()-81).name())
        window.card_theme_pick.setCurrentIndex(window.card_theme_pick.findData('standard'))
        self.assertIsNone(card.surface_brush.gradient())
        self.assertEqual(card.card_surface.name(),THEMES['aurora']['bg'])
        self.assertEqual(window.store.settings()['card_theme'],'standard')
        export_backup(window.store,window.settings,window.store.folder/'backup.json')
        target=Store(window.store.folder/'target');import_backup(target,window.store.folder/'backup.json')
        self.assertEqual(target.settings()['card_theme'],'standard')
        self.assertFalse(hasattr(card,'reset_size_button'))

    def test_wheel_changes_number_but_not_slider_and_click_still_works(self):
        window=self.window
        slider=next(item for item in window.findChildren(ClickSlider) if item.minimum()==60 and item.maximum()==175)
        original=window.ui_scale_pick.value()
        def wheel(widget):
            event=QWheelEvent(QPointF(20,10),QPointF(20,10),QPoint(),QPoint(0,120),
                             Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
            self.app.sendEvent(widget,event)
        wheel(slider);self.assertEqual(window.ui_scale_pick.value(),original)
        wheel(window.ui_scale_pick);self.assertEqual(window.ui_scale_pick.value(),original+1)
        slider.show();slider.resize(300,30)
        QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=QPoint(slider.width()-10,slider.height()//2))
        self.assertGreater(window.ui_scale_pick.value(),original+1)

    def test_reset_restores_only_appearance_defaults_and_saves(self):
        window=self.window;provider=window.settings['provider'];hotkeys=dict(window.settings['hotkeys'])
        window.theme_pick.setCurrentIndex(window.theme_pick.findData('warm'))
        window.card_theme_pick.setCurrentIndex(window.card_theme_pick.findData('standard'))
        window.ui_scale_pick.setValue(140);window.card_width_pick.setValue(720);window.card_height_pick.setValue(840)
        window.card_background_pick.setValue(40);window.overlay_background_pick.setValue(20)
        window.size_pick.setValue(30);window.opacity_pick.setValue(50);window.offset_pick.setValue(80)
        window.apply_appearance();window.appearance_reset_button.click();self.app.processEvents()
        saved=window.store.settings()
        for key,value in APPEARANCE_DEFAULTS.items():self.assertEqual(saved[key],value,key)
        self.assertEqual(saved['provider'],provider);self.assertEqual(saved['hotkeys'],hotkeys)
        self.assertEqual(window.card.theme_key,'aurora')
        self.assertIsNotNone(window.card.surface_brush.gradient())
        self.assertEqual(window.card_size_pick.currentData(),'default')
        self.assertEqual(window.card_scale_pick.value(),100)
        self.assertEqual(window.text_scale_pick.value(),100)

    def test_edge_resize_persists_sizes_and_card_reset_restores_default(self):
        window=self.window;card=window.card;card.show();self.app.processEvents()
        def drag(handle,dx,dy):
            origin=QPointF(handle.mapToGlobal(handle.rect().center()))
            local=QPointF(handle.rect().center())
            for kind,offset,buttons in ((QEvent.Type.MouseButtonPress,QPointF(),Qt.MouseButton.LeftButton),
                    (QEvent.Type.MouseMove,QPointF(dx,dy),Qt.MouseButton.LeftButton),
                    (QEvent.Type.MouseButtonRelease,QPointF(dx,dy),Qt.MouseButton.NoButton)):
                button=Qt.MouseButton.NoButton if kind==QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
                self.app.sendEvent(handle,QMouseEvent(kind,local+offset,origin+offset,button,buttons,Qt.KeyboardModifier.NoModifier))
            self.app.processEvents()
        drag(card.resize_handles[7],70,40)
        self.assertEqual((card.width(),card.height()),(670,740))
        self.assertEqual((window.store.settings()['card_width'],window.store.settings()['card_height']),(670,740))
        self.assertEqual(window.card_size_pick.currentData(),'custom')
        right=card.geometry().right();bottom=card.geometry().bottom()
        drag(card.resize_handles[4],-40,-20)
        self.assertEqual((card.geometry().right(),card.geometry().bottom()),(right,bottom))
        self.assertEqual((card.width(),card.height()),(710,760))
        drag(card.resize_handles[7],-2000,-2000)
        self.assertEqual((card.width(),card.height()),(320,320))
        window.reset_card_size();self.app.processEvents()
        self.assertEqual((card.width(),card.height()),(600,700))
        self.assertEqual(window.card_size_pick.currentData(),'default')


class AppearanceMigrationTests(unittest.TestCase):
    def test_old_defaults_update_once_and_custom_choices_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));settings=store.settings()
            self.assertEqual((settings['theme'],settings['card_width'],settings['card_height']),('aurora',600,700))
            legacy={'theme':'dark','card_width':440,'card_height':440}
            (store.folder/'settings.json').write_text(json.dumps(legacy),encoding='utf-8')
            migrated=store.settings();self.assertEqual((migrated['theme'],migrated['card_width'],migrated['card_height']),('aurora',600,700))
            migrated.update(theme='dark',card_width=710,card_height=760,card_theme='warm',window_preset='1080p')
            store.save_settings(migrated);self.assertEqual(store.settings()['theme'],'dark')
            export_backup(store,migrated,store.folder/'backup.json')
            target=Store(store.folder/'target');import_backup(target,store.folder/'backup.json')
            self.assertEqual((target.settings()['card_theme'],target.settings()['card_width'],target.settings()['window_preset']),('warm',710,'1080p'))
