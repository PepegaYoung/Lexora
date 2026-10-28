import sentencepiece,ctranslate2
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt,QEvent
from PySide6.QtTest import QTest
from windowwords.storage import Store
from windowwords.backup import export_backup,import_backup
from windowwords.i18n import tr,set_language
from tests import test_usability as usability


class OnboardingPersistenceTests(unittest.TestCase):
    def test_new_profile_is_offered_onboarding_and_completion_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));settings=store.settings();self.assertFalse(settings['onboarding_completed'])
            settings['onboarding_completed']=True;store.save_settings(settings)
            self.assertTrue(Store(Path(folder)).settings()['onboarding_completed'])

    def test_existing_profiles_are_not_interrupted_by_an_update(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'settings.json').write_text(json.dumps({'provider':'local','font_size':27}),encoding='utf-8')
            settings=Store(root).settings()
            self.assertTrue(settings['onboarding_completed']);self.assertEqual(settings['provider'],'local');self.assertEqual(settings['font_size'],27)

    def test_completion_is_local_and_not_copied_in_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=Store(root/'source');target=Store(root/'target');settings=source.settings()
            settings['onboarding_completed']=True;source.save_settings(settings);export_backup(source,settings,root/'backup.json')
            data=json.loads((root/'backup.json').read_text(encoding='utf-8'));self.assertNotIn('onboarding_completed',data['settings'])
            import_backup(target,root/'backup.json');self.assertFalse(target.settings()['onboarding_completed'])


class OnboardingAndPreviewUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown

    def appearance(self):
        window=self.window;window.show();self.app.processEvents()
        index=next(i for i in range(window.tabs.count()) if window.tabs.list.item(i).text()==tr('Настройки'))
        window.tabs.setCurrentIndex(index);window.settings_tabs.setCurrentIndex(2)
        self.app.processEvents();self.app.processEvents()
        return window.appearance_previews

    def test_guide_does_not_open_while_constructing_or_when_profile_is_complete(self):
        window=self.window;self.assertIsNone(getattr(window,'onboarding_dialog',None))
        window.settings['onboarding_completed']=True;window.show();window.offer_onboarding();self.app.processEvents()
        self.assertIsNone(getattr(window,'onboarding_dialog',None))

    def test_first_visible_launch_offers_guide_once_and_skip_is_remembered(self):
        window=self.window;window.show();window.offer_onboarding();self.app.processEvents()
        dialog=window.onboarding_dialog;self.assertTrue(dialog.isVisible());self.assertEqual(dialog.step,0)
        dialog.skip_button.click();self.app.processEvents()
        self.assertIsNone(window.onboarding_dialog);self.assertTrue(window.store.settings()['onboarding_completed'])
        window.offer_onboarding();self.app.processEvents();self.assertIsNone(window.onboarding_dialog)

    def test_all_steps_demo_and_shortcuts_are_safe_without_a_game_or_service(self):
        window=self.window;window.show();window.task=Mock();window.capture_freeze=Mock();window.translate_screen_once=Mock();window.toggle=Mock()
        settings={k:window.settings[k] for k in ('provider','screen_mode','hotkeys')};window.show_onboarding();dialog=window.onboarding_dialog
        dialog.next_button.click();dialog.word_button.click();self.assertIn('меч',dialog.word_result.text())
        dialog.next_button.click();dialog.choose_mode('replace');self.app.processEvents()
        self.assertEqual(dialog.screen_preview.settings['screen_mode'],'replace')
        for command in ('study','screen','toggle'):window.on_hotkey(command)
        window.capture_freeze.assert_not_called();window.translate_screen_once.assert_not_called();window.toggle.assert_not_called();window.task.assert_not_called()
        dialog.next_button.click();self.assertEqual(dialog.step,3);dialog.back_button.click();self.assertEqual(dialog.step,2)
        dialog.next_button.click();dialog.next_button.click();self.app.processEvents()
        self.assertTrue(window.store.settings()['onboarding_completed'])
        self.assertEqual(settings,{k:window.settings[k] for k in settings})

    def test_escape_closes_guide_and_help_menu_can_open_it_again(self):
        window=self.window;window.show();window.show_onboarding();self.app.processEvents()
        QTest.keyClick(window.onboarding_dialog,Qt.Key.Key_Escape);self.app.processEvents();self.assertIsNone(window.onboarding_dialog)
        action=next(a for a in window.help_button.menu().actions() if a.text()==tr('Знакомство с Lexora'))
        action.trigger();self.app.processEvents();self.assertEqual(window.onboarding_dialog.step,0)

    def test_setup_link_navigates_to_translation_without_changing_provider(self):
        window=self.window;provider=window.settings['provider'];window.show();window.show_onboarding();dialog=window.onboarding_dialog
        dialog.set_step(3);dialog.setup_button.click();self.app.processEvents()
        self.assertEqual(window.tabs.list.currentItem().text(),tr('Перевод'));self.assertEqual(window.settings['provider'],provider)
        self.assertTrue(window.store.settings()['onboarding_completed'])

    def test_demo_escape_takes_priority_over_an_existing_capture_session(self):
        window=self.window;window.show();window.session_active=True;window.close_session=Mock()
        window.show_onboarding();self.app.processEvents()
        QTest.keyClick(window.onboarding_dialog,Qt.Key.Key_Escape);self.app.processEvents()
        self.assertIsNone(window.onboarding_dialog);window.close_session.assert_not_called()
        window.show_onboarding();window.on_hotkey('escape');self.app.processEvents()
        self.assertIsNone(window.onboarding_dialog);window.close_session.assert_not_called()
        window.session_active=False

    def test_live_preview_uses_draft_theme_size_and_opacity_without_requests(self):
        window=self.window;previews=self.appearance();window.task=Mock();window.show_card=Mock()
        window.card_theme_pick.setCurrentIndex(window.card_theme_pick.findData('warm'));window.card_width_pick.setValue(720)
        window.card_background_pick.setValue(45);window.overlay_theme_pick.setCurrentIndex(window.overlay_theme_pick.findData('ocean'));window.overlay_background_pick.setValue(20)
        self.app.processEvents();self.app.processEvents()
        previews.select('screen');self.app.processEvents();self.app.processEvents()
        card=previews.canvases['card'];screen=previews.canvases['screen']
        self.assertEqual(card.sample.theme_key,'warm');self.assertEqual(card.settings['card_width'],720);self.assertEqual(card.sample.background_alpha,.45)
        self.assertEqual(screen.sample.settings['overlay_theme'],'ocean');self.assertEqual(screen.sample.settings['overlay_background'],.2)
        self.assertIsNotNone(card.image);self.assertIsNotNone(screen.image)
        self.assertFalse(card.sample.isVisible());self.assertFalse(screen.sample.isVisible())
        window.task.assert_not_called();window.show_card.assert_not_called();self.assertFalse(window.running)

    def test_previews_wrap_and_do_not_render_again_when_nothing_changed(self):
        window=self.window;previews=self.appearance();previews.resize(1200,previews.height());previews.fit();self.assertFalse(previews.stacked)
        previews.resize(200,previews.height());previews.fit();self.assertTrue(previews.stacked)
        canvas=previews.canvases['card'];canvas.refresh();image=canvas.image
        canvas.refresh();self.assertIs(canvas.image,image)

    def test_open_examples_are_local_and_close_without_affecting_the_game(self):
        window=self.window;previews=self.appearance();window.task=Mock();window.capture_freeze=Mock()
        for kind in ('card','screen'):
            previews.open_example(kind);self.app.processEvents();dialog=previews.dialogs[-1]
            self.assertTrue(dialog.isVisible());QTest.keyClick(dialog,Qt.Key.Key_Escape);self.app.processEvents()
            self.assertEqual(previews.dialogs,[])
        self.assertFalse(window.session_active);self.assertFalse(window.running)
        window.task.assert_not_called();window.capture_freeze.assert_not_called()

    def test_demo_windows_follow_the_apps_recording_visibility(self):
        window=self.window;previews=self.appearance()
        for visible in (False,True):
            window.settings['recording_visible']=visible
            with patch('windowwords.appearance_preview.native.exclude_capture',return_value=True) as affinity:
                window.show_onboarding();guide=window.onboarding_dialog
                self.assertIs(guide.property('captureVisible'),visible);affinity.assert_called_with(window)
                guide.reject();self.app.processEvents()
                previews.open_example('screen');dialog=previews.dialogs[-1]
                self.assertIs(dialog.property('captureVisible'),visible);affinity.assert_called_with(window)
                dialog.reject();self.app.processEvents()

    def test_help_menu_and_guide_stay_inside_the_resized_main_window(self):
        window=self.window;window.show();self.app.processEvents()
        for width,height in ((1280,850),(880,580)):
            window.resize(width,height);self.app.processEvents()
            menu=window.help_button.menu();window.help_button.click();self.app.processEvents()
            self.assertTrue(menu.isVisible());self.assertFalse(menu.isWindow())
            self.assertTrue(window.rect().contains(menu.geometry()))
            action=next(a for a in menu.actions() if a.text()==tr('Знакомство с Lexora'));action.trigger();self.app.processEvents()
            guide=window.onboarding_dialog;self.assertFalse(menu.isVisible());self.assertFalse(guide.isWindow())
            self.assertIs(guide.window(),window);self.assertTrue(window.rect().contains(guide.geometry()))
            self.assertTrue(guide.rect().contains(guide.panel.geometry()))
            # Resizing an open guide must keep every panel edge inside the host.
            window.resize(width+40,height+30);self.app.processEvents()
            self.assertEqual(guide.geometry(),window.rect());self.assertTrue(guide.rect().contains(guide.panel.geometry()))
            QTest.keyClick(guide,Qt.Key.Key_Escape);self.app.processEvents();self.assertIsNone(window.onboarding_dialog)

    def test_complete_card_preview_has_room_for_readable_text_and_actions(self):
        previews=self.appearance();canvas=previews.canvases['card'];canvas.refresh()
        scale=min(1,(canvas.width()-24)/canvas.image.width(),(canvas.height()-20)/canvas.image.height())
        self.assertGreaterEqual(17*scale,12)
        self.assertNotIn(tr('Фрагмент'),previews.captions['card'].text())
        # The full source image includes the bottom actions, not just the fields.
        self.assertEqual(canvas.image.height(),canvas.sample.height())
        self.assertGreater(canvas.height(),320)

    def test_top_choices_switch_one_preview_without_resizing_or_rendering_the_hidden_one(self):
        previews=self.appearance();self.assertEqual(previews.current_kind,'card')
        card=previews.canvases['card'];screen=previews.canvases['screen']
        self.assertIsNone(screen.sample);size=previews.pages.size();outer=previews.size();card_image=card.image
        self.assertLess(previews.choices.y(),previews.viewer.y())
        self.assertEqual(previews.buttons['card'].y(),previews.buttons['screen'].y())
        for kind,button in previews.buttons.items():
            label=previews.titles[kind]
            self.assertTrue(button.rect().contains(label.mapTo(button,label.rect().topLeft())))
            self.assertGreaterEqual(label.width(),label.fontMetrics().horizontalAdvance(label.text()))
        previews.buttons['screen'].click();self.app.processEvents();self.app.processEvents()
        self.assertEqual(previews.current_kind,'screen');self.assertEqual(previews.pages.size(),size);self.assertEqual(previews.size(),outer)
        self.assertTrue(screen.isVisible());self.assertFalse(card.isVisible());self.assertIsNotNone(screen.image)
        screen_image=screen.image;previews.buttons['card'].click();self.app.processEvents();self.app.processEvents()
        self.assertEqual(previews.pages.size(),size);self.assertIs(screen.image,screen_image)
        self.assertIs(card.image,card_image);self.assertTrue(previews.buttons['card'].isChecked());self.assertFalse(previews.buttons['screen'].isChecked())

    def test_help_rows_fit_their_text_and_share_alignment_across_themes_and_scales(self):
        window=self.window;window.show();self.app.processEvents();menu=window.help_button.menu()
        for theme in ('aurora','light','dark'):
            window.theme_pick.setCurrentIndex(window.theme_pick.findData(theme))
            for scale in (100,175):
                window.ui_scale_pick.setValue(scale);window.apply_appearance();self.app.processEvents()
                window.help_button.click();self.app.processEvents()
                self.assertTrue(window.rect().contains(menu.geometry()))
                self.assertEqual(len(menu.rows),2)
                self.assertEqual(menu.rows[0].x(),menu.rows[1].x())
                self.assertEqual(menu.rows[0].width(),menu.rows[1].width())
                for row in menu.rows:
                    self.assertGreaterEqual(row.width(),row.fontMetrics().horizontalAdvance(row.text())+row.iconSize().width()+28)
                    self.assertGreaterEqual(row.height(),row.fontMetrics().height()+18)
                    self.assertTrue(menu.rect().contains(row.geometry()))
                menu.hide()

    def test_help_keyboard_navigation_and_escape_do_not_close_the_game_session(self):
        window=self.window;window.show();self.app.processEvents();window.session_active=True;window.close_session=Mock()
        menu=window.help_button.menu();window.help_button.click();self.app.processEvents()
        QTest.keyClick(menu.rows[0],Qt.Key.Key_Down);self.app.processEvents()
        QTest.keyClick(menu.rows[1],Qt.Key.Key_Return);self.app.processEvents()
        self.assertFalse(menu.isVisible());self.assertIsNotNone(window.onboarding_dialog)
        window.onboarding_dialog.reject();self.app.processEvents()
        window.help_button.click();self.app.processEvents();QTest.keyClick(menu.rows[0],Qt.Key.Key_Escape);self.app.processEvents()
        self.assertFalse(menu.isVisible());window.close_session.assert_not_called()
        window.help_button.click();self.app.processEvents();window.on_hotkey('escape')
        self.assertFalse(menu.isVisible());window.close_session.assert_not_called();window.session_active=False

    def test_help_opens_onboarding_with_mouse_events_routed_through_the_native_window(self):
        window=self.window;window.show();window.raise_();window.activateWindow();self.app.processEvents()
        menu=window.help_button.menu()
        def click(widget):
            point=widget.mapTo(window,widget.rect().center())
            QTest.mouseClick(window.windowHandle(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            self.app.processEvents()
        click(window.help_button);self.assertTrue(menu.isVisible())
        click(menu.rows[1]);self.assertIsNotNone(getattr(window,'onboarding_dialog',None))
        self.assertTrue(window.onboarding_dialog.isVisible());self.assertFalse(menu.isVisible())
        guide=window.onboarding_dialog;click(guide.next_button);self.assertEqual(guide.step,1)
        click(guide.word_button);self.assertIn('меч',guide.word_result.text())
        click(guide.next_button);self.assertEqual(guide.step,2)
        click(guide.mode_buttons[1][1]);self.assertEqual(guide.screen_preview.settings['screen_mode'],'replace')
        click(guide.next_button);self.assertEqual(guide.step,3)
        click(guide.next_button);self.assertIsNone(window.onboarding_dialog)
        self.assertTrue(window.store.settings()['onboarding_completed'])
        click(window.help_button);click(menu.rows[1]);self.assertEqual(window.onboarding_dialog.step,0)
        click(window.onboarding_dialog.skip_button);self.assertIsNone(window.onboarding_dialog)
        click(window.help_button);click(menu.rows[0])
        self.assertFalse(menu.isVisible());self.assertTrue(window.help_panel.isVisible())


if __name__=='__main__':unittest.main()
