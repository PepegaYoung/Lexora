"""Offline release smoke test; never reads real account credentials."""
import json
from pathlib import Path
import tempfile
import traceback
import time
from PIL import Image,ImageDraw,ImageFont
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent
from . import native,ocr
from .storage import Store,Dictionary
from .translation import response_body


def run(destination,model=None):
    report = {'live_subscription_tested':False,'live_api_tested':False}
    try:
        native.dpi_aware()
        app = QApplication([])
        def until(predicate):
            deadline=time.monotonic()+3
            while not predicate() and time.monotonic()<deadline:
                app.processEvents();time.sleep(.01)
            assert predicate()
        actions=[];failures=[]
        alternatives=native.Hotkeys(actions.append,failures.append,{'study':'F20; Ctrl+Alt+Shift+F24'},False)
        try:
            alternatives.start()
            assert alternatives.ready.wait(3)
            assert alternatives.registered=={1,2} and not failures
            for ident in (1,2):native.user.PostThreadMessageW(alternatives.thread_id,0x312,ident,0)
            until(lambda:len(actions)==2)
            alternatives.set_single_enabled(False)
            until(lambda:alternatives.registered=={2})
            for ident in (1,2):native.user.PostThreadMessageW(alternatives.thread_id,0x312,ident,0)
            until(lambda:len(actions)==3)
            alternatives.set_single_enabled(True)
            until(lambda:alternatives.registered=={1,2})
            assert actions==['study']*3 and not alternatives.hook_installed
        finally:
            alternatives.stop();alternatives.join(timeout=3)
        assert not alternatives.is_alive() and not alternatives.registered
        report['single_and_alternative_windows_hotkeys']='passed'
        report['monitors'] = native.monitors()
        image = Image.new('RGB',(900,160),'#181818')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',32)
        draw.text((20,12),'Maybe they missed something.',fill='white',font=font)
        draw.text((20,78),'1. Should search his trousers.',fill='#f4d632',font=font)
        lines = ocr.read(image)
        report['ocr'] = [line.text for line in lines]
        assert any('missed something' in line.text for line in lines)
        assert any('trousers' in line.text for line in lines)
        report['dictionary'] = bool(Dictionary().lookup('sword'))
        assert report['dictionary']
        from .storage import base_dir
        wiki=Dictionary(base_dir()/'data/wiktionary.sqlite3')
        report['wiktionary']={'jerkin':bool(wiki.lookup('jerkin')),'went':bool(wiki.lookup('went'))}
        assert all(report['wiktionary'].values())
        with tempfile.TemporaryDirectory(prefix='windowwords-selftest-') as path:
            store = Store(Path(path))
            store.vault.set('test','smoke-test-value')
            assert store.vault.read()['test']=='smoke-test-value'
            assert b'smoke-test-value' not in store.vault.path.read_bytes()
            store.save_word('sword','меч','a sword','Release test')
            assert len(store.words())==1
            from .app import MainWindow,STYLE
            app.setStyleSheet(STYLE)
            window = MainWindow(store)
            assert window.external_mode()
            assert window.keys.ready.wait(2)
            assert not window.keys.hook_installed
            report['external_mode_no_keyboard_hook']=True
            from .design import PAGE_HELP
            from PySide6.QtWidgets import QScrollArea
            window.show()
            window.help.show(max(PAGE_HELP.values(),key=len),force=True)
            app.processEvents()
            assert not window.help_panel.findChildren(QScrollArea)
            label=window.help_panel.text
            assert label.contentsRect().height()>=label.heightForWidth(label.width())
            report['help_without_scroll_or_clipping']='passed'
            window.help.dismiss()
            window.review_page.start()
            assert window.review_page.current
            assert not window.review_page.answer.toPlainText()
            window.review_page.reveal()
            window.review_page.rate(True)
            assert store.review_stats()[1]==0
            report['learning_and_persistent_schedule']='passed'
            from .backup import export_backup,import_backup
            backup=Path(path)/'backup.json'
            export_backup(store,window.settings,backup)
            assert 'smoke-test-value' not in backup.read_text(encoding='utf-8')
            other=Store(Path(path)/'restored')
            import_backup(other,backup)
            assert len(other.words())==1 and other.review_stats()[1]==0
            report['backup_without_credentials']='passed'
            report['english_voice']=window.speaker.speak('',mode='probe')
            assert window.speaker.speak('Maybe they missed something.',mode='verify')=='OK'
            report['offline_speech_silent_synthesis']='passed'
            previous=window.keys
            field=window.hotkey_fields['study']
            field.begin()
            assert window.hotkey_capture_active and not previous.is_alive()
            event=QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_F24,
                Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.ShiftModifier)
            QApplication.sendEvent(field,event)
            assert window.settings['hotkeys']['study']=='Ctrl+Alt+Shift+F24'
            field.finish()
            app.processEvents()
            assert window.keys is not previous and window.keys.ready.wait(2)
            assert not window.keys.hook_installed
            report['hotkey_recording_and_resume']='passed'
            field.begin_add()
            QApplication.sendEvent(field,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_F20,Qt.KeyboardModifier.NoModifier))
            field.finish();app.processEvents()
            assert window.settings['hotkeys']['study']=='Ctrl+Alt+Shift+F24; F20'
            assert window.keys.ready.wait(3)
            window.show();window.activateWindow()
            until(lambda:app.activeWindow() is window)
            until(lambda:not window.keys.single_enabled and 2 not in window.keys.registered)
            report['single_keys_released_in_main_window']='passed'
            window.task=lambda *args:None
            window.begin_session()
            window.show_freeze(image,window.monitor,'study')
            app.processEvents()
            assert window.freeze.isFullScreen()
            until(lambda:app.activeWindow() is window.freeze)
            until(lambda:window.keys.single_enabled and 2 in window.keys.registered)
            report['single_keys_active_on_frame']='passed'
            window.show_card('jerkin','Might be something in his jerkin.',activate=False)
            app.processEvents()
            import ctypes
            from ctypes import wintypes
            native.user.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT]
            native.user.GetWindow.restype=wintypes.HWND
            assert native.user.GetWindow(int(window.card.winId()),4)==int(window.freeze.winId())
            assert not native.user.GetWindowLongW(int(window.card.winId()),-20)&8
            handle=int(window.card.winId())
            for _ in range(1000):
                handle=native.user.GetWindow(handle,2)
                if not handle or handle==int(window.freeze.winId()):break
            assert handle==int(window.freeze.winId())
            report['fullscreen_and_card_native_order']='passed'
            window.close_session(restore=False)
            assert window.grab().save(str(Path(destination).with_suffix('.png')))
            window.close()
            app.processEvents()
            report['interface'] = 'passed'
            if model:
                from .translation import Translator
                report['local_translation'] = Translator(store,None).translate_local(model,'Maybe they missed something.')
                assert 'упустили' in report['local_translation'].lower()
        report['encrypted_storage'] = True
        assert 'max_output_tokens' not in response_body('subscription','test-model','hello',[])
        report['status'] = 'passed'
        app.processEvents()
        code = 0
    except Exception:
        report['status'] = 'failed'
        report['error'] = traceback.format_exc()
        code = 1
    Path(destination).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return code
