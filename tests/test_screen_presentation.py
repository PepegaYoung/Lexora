import sentencepiece,ctranslate2
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import QPoint,QEvent
from PySide6.QtGui import QImage,QRegion
from PySide6.QtWidgets import QApplication,QWidget
from windowwords.core import Box
from windowwords.screen import intersects
from windowwords.screen_layout import layout,Label
from windowwords.screen_text import measure_text,wrapped_text
from windowwords.screen_overlay import ScreenOverlay
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup
from windowwords.themes import THEMES,OVERLAY_THEMES,overlay_palette
from tests import test_usability as usability


class VerticalPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_dialogue_widens_above_source_instead_of_sitting_beside_it(self):
        name=Box(366,900,128,45);source=Box(403,971,440,40)
        entries=[(name,'Эмма'),(source,'Но не может быть, чтобы всё было так плохо.')]
        labels,skipped=layout(entries,1920,1080,'above',22,14,measure_text,[name,source])
        self.assertEqual(skipped,0);self.assertEqual(len(labels),2)
        for label in labels:
            self.assertEqual(label.placement,'above')
            self.assertLessEqual(label.box.y+label.box.h,label.source.y)
            self.assertTrue(all(not intersects(label.box,b,1) for b in (name,source)))
        self.assertFalse(intersects(labels[0].box,labels[1].box))

    def test_blocked_above_uses_below_even_when_sides_are_available(self):
        source=Box(300,200,150,28);blocker=Box(0,0,800,199)
        labels,skipped=layout([(source,'Открыть дверь')],800,600,'above',22,14,measure_text,[source,blocker])
        self.assertEqual(skipped,0);self.assertEqual(labels[0].placement,'below')
        self.assertGreaterEqual(labels[0].box.y,source.y+source.h)

    def test_side_is_used_only_when_both_vertical_directions_are_blocked(self):
        source=Box(200,200,120,28);blockers=[source,Box(100,0,300,198),Box(100,230,300,370)]
        labels,skipped=layout([(source,'Дверь')],800,600,'above',22,14,measure_text,blockers)
        self.assertEqual(skipped,0);self.assertEqual(labels[0].placement,'right')

    def test_small_top_gap_keeps_text_above_before_choosing_full_size_below(self):
        source=Box(300,28,130,30)
        labels,skipped=layout([(source,'Закрыть')],800,600,'above',22,14,measure_text,[source])
        self.assertEqual(skipped,0);self.assertEqual(labels[0].placement,'above')
        self.assertLess(labels[0].size,22)

    def test_dense_group_prefers_above_and_below_before_a_side_column(self):
        sources=[Box(300,350+i*40,130,24) for i in range(3)]
        entries=[(s,t) for s,t in zip(sources,('Начать','Продолжить','Выход'))]
        first,_=layout(entries,1000,900,'above',22,14,measure_text,sources)
        self.assertEqual({l.placement for l in first},{'group-above'})
        labels,skipped=layout(entries,1000,900,'above',22,14,measure_text,sources+[Box(0,0,1000,349)])
        self.assertEqual(skipped,0);self.assertEqual({l.placement for l in labels},{'group-below'})
        self.assertEqual(len({l.box.x for l in labels}),1)

    def test_new_subtitle_does_not_cover_a_valid_pinned_name(self):
        name=(Box(366,900,128,45),'Эмма');phrase=(Box(403,971,440,40),'Но не может быть, чтобы всё было так плохо.')
        first,_=layout([name],1920,1080,'above',22,14,measure_text,[name[0],phrase[0]])
        labels,skipped=layout([name,phrase],1920,1080,'above',22,14,measure_text,[name[0],phrase[0]],previous=first)
        self.assertEqual(skipped,0);self.assertEqual(labels[0],first[0]);self.assertEqual(labels[1].placement,'above')


class OverlayStylePersistenceTests(unittest.TestCase):
    def test_each_theme_and_follow_app_survive_backup_and_game_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'source');target=Store(root/'target')
            for theme in ('',*OVERLAY_THEMES):
                settings=store.settings();settings.update(overlay_theme=theme,overlay_background=.25,profiles={'Example':{'overlay_theme':theme,'overlay_background':.25}})
                store.save_settings(settings);self.assertEqual(store.settings()['overlay_theme'],theme)
                export_backup(store,settings,root/'backup.json');import_backup(target,root/'backup.json')
                self.assertEqual(target.settings()['overlay_theme'],theme)
                self.assertEqual(target.settings()['profiles']['Example']['overlay_theme'],theme)
            self.assertEqual(overlay_palette('','warm'),THEMES['warm'])

    def test_invalid_local_theme_falls_back_and_invalid_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root);settings=store.settings();settings['overlay_theme']='unknown';store.save_settings(settings)
            self.assertEqual(store.settings()['overlay_theme'],'standard')
            export_backup(store,settings,root/'backup.json')
            with self.assertRaises(ValueError):import_backup(store,root/'backup.json')


class OverlayPaintingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def paint(self,theme,alpha,mode='above'):
        widget=ScreenOverlay();widget.resize(400,180);widget.viewport=Box(0,0,400,180)
        widget.settings={'overlay_theme':theme,'overlay_background':alpha,'screen_mode':mode,'opacity':1.0}
        widget.labels=(Label(Box(20,110,250,35),Box(20,30,250,66),'Пример перевода',22,'field' if mode=='replace' else 'above'),)
        widget.text_layouts=[wrapped_text('Пример перевода',22,242)[0]]
        image=QImage(400,180,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
        try:widget.render(image,QPoint(),QRegion(),QWidget.RenderFlag.DrawChildren)
        finally:widget.close();widget.deleteLater();self.app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        return image

    def test_selected_theme_and_alpha_are_painted_into_the_background(self):
        for key in ('standard','ocean','warm'):
            image=self.paint(key,.25);pixel=image.pixelColor(30,34);expected=overlay_palette(key)
            self.assertAlmostEqual(pixel.alpha(),64,delta=1)
            self.assertAlmostEqual(pixel.red(),int(expected['bg'][1:3],16),delta=3)
            self.assertAlmostEqual(pixel.blue(),int(expected['bg'][5:7],16),delta=3)

    def test_aurora_has_a_gradient_and_zero_background_keeps_the_letters(self):
        gradient=self.paint('aurora',1)
        self.assertNotEqual(gradient.pixelColor(30,34).name(),gradient.pixelColor(255,90).name())
        transparent=self.paint('standard',0)
        self.assertEqual(transparent.pixelColor(30,34).alpha(),0)
        self.assertTrue(any(transparent.pixelColor(x,y).alpha()>0 for x in range(24,220) for y in range(36,62)))

    def test_replacement_keeps_the_selected_theme_opaque_even_at_zero_background(self):
        image=self.paint('warm',0,'replace')
        self.assertEqual(image.pixelColor(30,34).alpha(),255)
        self.assertEqual(image.pixelColor(30,120).alpha(),255)
        self.assertEqual(image.pixelColor(30,120).name(),THEMES['warm']['bg'])


class OverlayStyleUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def test_overlay_theme_is_independent_and_changes_visible_translation_immediately(self):
        window=self.window;window.running=True;window.draw_screen=Mock()
        with patch.object(window.overlay,'isVisible',return_value=True):
            window.overlay_theme_pick.setCurrentIndex(window.overlay_theme_pick.findData('warm'))
            window.overlay_background_pick.setValue(25)
        self.assertEqual(window.store.settings()['overlay_theme'],'warm')
        self.assertEqual(window.store.settings()['overlay_background'],.25)
        self.assertEqual(window.store.settings()['card_theme'],'')
        self.assertGreaterEqual(window.draw_screen.call_count,2)
        window.running=False

    def test_game_profile_restores_its_overlay_style_without_signals_overwriting_it(self):
        window=self.window
        window.settings.update(overlay_theme='ocean',overlay_background=.3)
        window.apply_profile_appearance({'overlay_theme':'ocean','overlay_background':.3})
        self.assertEqual(window.overlay_theme_pick.currentData(),'ocean')
        self.assertEqual(window.settings['overlay_background'],.3)

    def test_appearance_controls_fit_a_small_window_with_large_text(self):
        window=self.window;window.show();self.app.processEvents()
        window.resize(880,580);self.app.processEvents()
        index=next(i for i in range(window.tabs.count()) if window.tabs.list.item(i).text()=='Настройки')
        window.tabs.setCurrentIndex(index);window.settings_tabs.setCurrentIndex(2)
        window.ui_scale_pick.setValue(175);window.apply_appearance();self.app.processEvents();self.app.processEvents()
        self.assertEqual(window.settings_pages.currentWidget().horizontalScrollBar().maximum(),0)


if __name__=='__main__':unittest.main()
