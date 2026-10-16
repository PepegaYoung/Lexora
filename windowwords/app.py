from .i18n import tr,trf
import copy
import os
from pathlib import Path
import sys
import time
import webbrowser
from PIL import Image
import mss
from PySide6.QtCore import QObject,QRunnable,QThreadPool,Signal,QTimer,Qt,QLockFile,QSignalBlocker
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QTabWidget,QComboBox,QLineEdit,QPlainTextEdit,QFormLayout,QSpinBox,QDoubleSpinBox,
    QFileDialog,QMessageBox,QInputDialog,QScrollArea)
from .core import Box,Stability,Generation,normalized
from .storage import Store,Dictionary,base_dir
from .dictionaries import Dictionaries
from .ui import UIBuilder
from .reading_widgets import divider
from .word_list import WordList
from .upgrades import Upgrades
from .auth import ChatGPTAuth,ServiceError,PLAN_SCOPE
from .translation import Translator
from .models import download_model
from .widgets import Freeze,Card
from .screen_overlay import ScreenOverlay
from .screen_mode import ScreenMode
from .design import NAME,VERSION,Navigation,HelpPanel,ContextHelp,header,STYLE
from .game_mode import GameMode,ResultWindow
from .shortcuts import ShortcutCapture
from .features import Features
from .model_catalog import ModelCatalog
from .safety import GameSafety,game_action
from .recording import RecordingMode
from .onboarding import Onboarding
from . import native,ocr

class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            self.signals.done.emit(self.function())
        except (ServiceError,RuntimeError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            # Do not expose request URLs, tokens or callback query strings in UI/logs.
            self.signals.failed.emit(tr('Не удалось выполнить операцию. Проверь настройки и повтори.'))


class MainWindow(Onboarding,RecordingMode,GameSafety,ModelCatalog,ShortcutCapture,Features,GameMode,ScreenMode,Upgrades,UIBuilder,QMainWindow):
    hotkey = Signal(str)
    native_error = Signal(str)
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.settings = self.store.settings()
        from .i18n import set_language
        set_language(self.settings['ui_language'])
        self.auth = ChatGPTAuth(self.store,self.settings['host_id'])
        self.translator = Translator(self.store,self.auth)
        self.dictionary = Dictionaries(self.store,self.settings)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.jobs = set()
        self.monitors = native.monitors()
        self.region = Box(*self.settings['region']) if self.settings.get('region') else None
        primary=next((m for m in self.monitors if m.get('primary')),self.monitors[0])
        self.monitor = next((m for m in self.monitors if m['name']==self.settings.get('monitor')),primary)
        if self.region and not (self.monitor['x']<=self.region.x and self.monitor['y']<=self.region.y and
            self.region.x+self.region.w<=self.monitor['x']+self.monitor['w'] and self.region.y+self.region.h<=self.monitor['y']+self.monitor['h']):
            self.region = None
        self.running = self.ocr_busy = self.cloud_busy = False
        self.epoch = Generation()
        self.card_epoch = Generation()
        self.stability = Stability(.25)
        self.lines,self.history = (),[]
        self.freeze = None
        self.closing = False
        self.init_safety_state()
        self.hotkey_capture_active=False
        self.overlay = ScreenOverlay()
        self.card = Card()
        self.card.preferred_size_changed.connect(self.save_card_size)
        self.result_window=ResultWindow()
        self.result_window.dismissed.connect(self.stop)
        self.card.analyze.connect(lambda:self.analyze_card(True))
        self.card.translate_sentence.connect(lambda:self.analyze_card(False))
        self.card.save.connect(self.save_card)
        self.init_feature_state()
        self.setWindowTitle(f'{NAME} {VERSION}')
        self.resize(1280,720)
        self.setMinimumSize(880,580)
        root = QWidget()
        root.setObjectName('lexoraRoot')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26,20,26,22)
        header(self,layout)
        self.tabs = Navigation()
        layout.addWidget(self.tabs)
        self.build_reading()
        self.build_settings()
        self.build_library()
        self.build_feature_pages()
        self.build_history()
        self.build_preferences()
        self.help_panel=HelpPanel()
        self.help=ContextHelp(self,self.help_panel)
        self.settings_tabs.currentChanged.connect(lambda _:self.help_panel.hide())
        layout.addWidget(self.help_panel)
        layout.addWidget(divider())
        self.status = QLabel(tr('Готово'))
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setObjectName('subtitle')
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.hotkey.connect(self.on_hotkey)
        self.native_error.connect(self.message)
        self.keys = native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
        QApplication.instance().applicationStateChanged.connect(self.update_single_hotkeys)
        QApplication.instance().focusWindowChanged.connect(self.update_single_hotkeys)
        self.init_upgrades()
        self.init_design()
        self.configure_game_windows()
        self.init_recording_mode()
        self.refresh_account_label()
        self.refresh_library()
        self.start_feature_timers()
        self.init_model_catalog()
        self.init_gamepad_input()
        self.start_game_protection()
        self.start_hotkeys()

    def task(self,function,done,failed=None):
        job = Job(function)
        self.jobs.add(job)
        def success(result):
            self.jobs.discard(job)
            done(result)
        def failure(error):
            self.jobs.discard(job)
            (failed or self.message)(error)
        job.signals.done.connect(success)
        job.signals.failed.connect(failure)
        self.pool.start(job)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if (getattr(self,'appearance_ready',False) and not getattr(self,'window_size_applying',False)
                and not self.isMinimized() and (event.size().width(),event.size().height())!=getattr(self,'window_target_size',None)):
            with QSignalBlocker(self.window_size_pick):
                self.window_size_pick.setCurrentIndex(self.window_size_pick.findData('custom'))
            self.settings['window_preset']='custom'

    def message(self,text):
        self.status.setText(tr(text))
        if hasattr(self,'region_status'):
            self.region_status.setTextFormat(Qt.TextFormat.PlainText)
            self.region_status.setText(tr(text))


    def refresh_key_labels(self):
        from .gamepad import display
        keys={}
        for action,value in self.settings['hotkeys'].items():
            pad=self.settings['gamepad_bindings'][action] if self.settings['gamepad_enabled'] else ''
            keys[action]=native.hotkey_label(value) if value else display(pad.split(';')[0]) if pad else tr('Не назначено')
        self.capture_buttons['study'].setText(tr('Выбрать слово'))
        self.capture_buttons['region'].set_shortcut(keys['region'])
        self.start_button.setText(tr('Остановить') if self.running else tr('Запустить'))
        if hasattr(self,'snapshot_button'):self.snapshot_button.setText(tr('Перевести'))
        for action,row in self.action_rows.items():
            if action=='file':continue
            button=self.capture_buttons['study'] if action=='study' else self.snapshot_button if action=='screen' else self.start_button
            button.set_shortcut(keys[action])
        actions=(self.capture_buttons['study'],self.snapshot_button,self.start_button,self.open_image_button)
        width=max(button.sizeHint().width() for button in actions)
        height=max(button.sizeHint().height() for button in actions)
        for button in actions:button.setFixedSize(width,height)
        self.capture_buttons['region'].setMinimumHeight(height)
        self.start_button.setChecked(self.running)


    def build_library(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        heading=QHBoxLayout();title=QLabel(tr('Мои слова'));title.setObjectName('sectionTitle')
        self.word_count=QLabel();self.word_count.setObjectName('subtitle')
        heading.addWidget(title);heading.addWidget(self.word_count);heading.addStretch();layout.addLayout(heading)
        toolbar=QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Найти слово, перевод или фразу'))
        self.search.textChanged.connect(self.refresh_library)
        toolbar.addWidget(self.search,1)
        export=QPushButton(tr('Экспорт'));export.clicked.connect(self.export_words);toolbar.addWidget(export)
        layout.addLayout(toolbar)
        self.word_list=WordList();self.word_list.itemDoubleClicked.connect(lambda *_:self.open_saved())
        layout.addWidget(self.word_list,1)
        self.words_empty=QLabel();self.words_empty.setObjectName('subtitle');self.words_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.words_empty,1)
        row = QHBoxLayout()
        self.word_buttons=[]
        for title,fn in [(tr('Открыть'),self.open_saved),(tr('Удалить'),self.delete_saved)]:
            button = QPushButton(title)
            button.clicked.connect(fn)
            row.addWidget(button);self.word_buttons.append(button)
        self.word_list.currentRowChanged.connect(lambda _:self.update_word_actions())
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        self.tabs.addTab(page,tr('Мои слова'))

    def change_monitor(self,index):
        self.stop()
        self.refresh_key_labels()
        self.monitor = self.monitors[index]
        self.region = None
        self.settings.update(region=None,monitor=self.monitor['name'])
        self.store.save_settings(self.settings)
        self.update_region_label()

    def update_region_label(self):
        self.region_label.setText(tr('Область: ')+(f'{round(self.region.w)} × {round(self.region.h)}' if self.region else tr('не выбрана')))
        if self.region and self.region.h>self.monitor['h']*.25:
            self.region_label.setToolTip(tr('Высокая область: сцена может мешать распознаванию. Для субтитров удобнее узкая полоса.'))
        else:self.region_label.setToolTip(tr('Размер выбранной области в пикселях монитора.'))



    def save_profile(self):
        game = self.game.text().strip()
        if not game:
            self.message(tr('Введи название игры.'))
            return
        keys = ('region','monitor','filter','ocr_engine','ocr_device','font_size','opacity','offset','screen_scope','screen_mode','overlay_background','overlay_theme',
                'card_width','card_height','card_background')
        profile = {k:copy.deepcopy(self.settings.get(k)) for k in keys}
        profile['region'] = self.region.json() if self.region else None
        profile['monitor'] = self.monitor['name']
        self.settings['profiles'][game] = profile
        self.store.save_settings(self.settings)
        self.message(tr('Профиль сохранён: ')+game)

    def load_profile(self):
        names = list(self.settings['profiles'])
        if not names:
            self.message(tr('Сначала сохрани профиль игры.'))
            return
        game,accepted = QInputDialog.getItem(self,tr('Профиль игры'),tr('Выбери игру'),names,0,False)
        if not accepted:
            return
        self.apply_profile(game)

    def apply_profile(self,game):
        profile = self.settings['profiles'][game]
        allowed={'region','monitor','filter','ocr_engine','ocr_device','font_size','opacity','offset','screen_scope','screen_mode','overlay_background','overlay_theme',
                 'card_width','card_height','card_background'}
        profile={k:v for k,v in profile.items() if k in allowed}
        monitor = next((m for m in self.monitors if m['name']==profile.get('monitor')),None)
        self.stop()
        self.close_session(restore=False)
        self.lines = ()
        self.refresh_key_labels()
        self.game.setText(game)
        if monitor is None:
            self.region = None
            self.update_region_label()
            self.message(tr('Монитор профиля не найден. Выбери новый монитор и область.'))
            return
        self.monitor_pick.blockSignals(True)
        self.monitor_pick.setCurrentIndex(self.monitors.index(monitor))
        self.monitor_pick.blockSignals(False)
        self.monitor = monitor
        self.settings.update(profile,game=game)
        from .game_ocr import apply_settings
        apply_settings(self.settings.get('ocr_engine','windows'),self.settings.get('ocr_device','gpu'))
        self.region = Box(*profile['region']) if profile.get('region') else None
        if self.region and not (Box(monitor['x'],monitor['y'],monitor['w'],monitor['h']).contains(self.region.x,self.region.y)
            and self.region.x+self.region.w<=monitor['x']+monitor['w'] and self.region.y+self.region.h<=monitor['y']+monitor['h']):
            self.region = None
            self.settings['region'] = None
        self.screen_scope.blockSignals(True)
        self.screen_render.blockSignals(True)
        self.screen_scope.setCurrentIndex(max(0,self.screen_scope.findData(self.settings['screen_scope'])))
        self.screen_render.setCurrentIndex(max(0,self.screen_render.findData(self.settings['screen_mode'])))
        self.screen_scope.blockSignals(False)
        self.screen_render.blockSignals(False)
        self.filter_pick.setCurrentIndex(max(0,self.filter_pick.findData(self.settings['filter'])))
        self.ocr_engine_pick.setCurrentIndex(max(0,self.ocr_engine_pick.findData(self.settings.get('ocr_engine','windows'))))
        self.ocr_device_pick.setCurrentIndex(max(0,self.ocr_device_pick.findData(self.settings.get('ocr_device','gpu'))))
        self.size_pick.setValue(self.settings['font_size'])
        self.opacity_pick.setValue(round(self.settings['opacity']*100))
        self.offset_pick.setValue(self.settings['offset'])
        self.apply_profile_appearance(profile)
        self.store.save_settings(self.settings)
        self.update_region_label()
        self.message(tr('Профиль загружен: ')+game)


    def login(self,new):
        self.stop()
        self.card_epoch.next()
        for button in (self.login_button,self.new_login_button,self.logout_button):
            button.setEnabled(False)
        self.message(tr('Ожидаю вход в браузере. Разреши использование подписки и вернись в программу.'))
        def finish(profile=None,error=None):
            for button in (self.login_button,self.new_login_button,self.logout_button):
                button.setEnabled(True)
            self.refresh_account_label()
            if error:
                self.message(error)
            elif PLAN_SCOPE not in profile.get('scopes',[]):
                self.message(tr('Вход выполнен, но использование подписки не разрешено. Повтори вход с разрешением.'))
            else:
                self.invalidate_models('subscription')
                self.provider.setCurrentIndex(self.provider.findData('subscription'))
                self.message(tr('Подписка подключена. Список моделей загружается автоматически.'))
                self.get_models()
        self.task(lambda:self.auth.sign_in(new),lambda profile:finish(profile),lambda error:finish(error=error))

    def logout(self):
        self.stop()
        self.card_epoch.next()
        self.message(tr('Отключаю аккаунт…'))
        def done(confirmed):
            self.translator.cache.clear()
            self.invalidate_models('subscription')
            self.refresh_account_label()
            self.message(tr('Аккаунт отключён.') if confirmed else tr('Отключён локально. Отзыв доступа не подтверждён: отключи приложение также в настройках ChatGPT.'))
        self.task(self.auth.sign_out,done)


    def save_api_key(self):
        key = self.api_key.text().strip()
        if not key:
            self.message(tr('Введи ключ в поле API-ключа.'))
            return
        self.stop()
        self.card_epoch.next()
        self.store.vault.set('api_key',key)
        self.api_key.clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.invalidate_models('api')
        self.message(tr('Ключ сохранён. Список моделей загружается автоматически.'))
        self.get_models()

    def delete_api_key(self):
        self.stop()
        self.card_epoch.next()
        self.store.vault.set('api_key',None)
        self.invalidate_models('api')
        self.api_key.clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message(tr('API-ключ удалён. Подключение подписки сохранено.'))

    def save_game_settings(self):
        self.settings['game']=self.game.text().strip()
        self.store.save_settings(self.settings)
        if hasattr(self,'status'):self.message(tr('Настройки экрана и игры сохранены.'))

    def apply_ocr(self):
        self.ocr_preview.clear()
        self.close_session(restore=False)
        self.stop()
        self.settings['filter']=self.filter_pick.currentData()
        self.settings['ocr_engine']=self.ocr_engine_pick.currentData()
        self.settings['ocr_device']=self.ocr_device_pick.currentData()
        from .game_ocr import apply_settings
        apply_settings(self.settings['ocr_engine'],self.settings['ocr_device'],retry=True)
        self.store.save_settings(self.settings)
        self.message(tr('Распознавание сохранено: ')+self.filter_pick.currentText())

    def choose_model(self):
        path = QFileDialog.getExistingDirectory(self,tr('Папка en-ru с sentencepiece.model'))
        if path:
            self.local_path.setText(path)


    def capture_image(self,box):
        if not self.capture_permitted():raise RuntimeError(tr('Захват остановлен защитой игр.'))
        if self.settings.get('recording_visible',False):
            if not getattr(self,'recording_target',None):raise RuntimeError(tr('Переключись в игру и запусти действие горячей клавишей.'))
            return self.recording_capture.grab(self.recording_target,box)
        with mss.mss() as capture:
            frame = capture.grab({'left':round(box.x),'top':round(box.y),'width':round(box.w),'height':round(box.h)})
            return Image.frombytes('RGB',frame.size,frame.rgb)








    def save_card(self):
        term = self.card.term.text().strip()
        answer = self.card.answer.toPlainText().strip()
        if not answer:
            answer = self.dictionary.lookup(term)
        if not term or not answer:
            self.card.status.setText(tr('Заполни слово и перевод перед сохранением.'))
            return
        ident = getattr(self.card,'saved_id',None)
        if ident:
            self.store.edit_word(ident,term,answer,self.card.sentence.toPlainText(),self.card.saved_game or self.game.text())
        else:
            self.store.save_word(term,answer,self.card.sentence.toPlainText(),self.game.text())
        self.card.status.setText(tr('Сохранено в «Мои слова»'))
        self.refresh_library()

    def refresh_library(self):
        if not hasattr(self,'word_list'):
            return
        records = self.store.words(self.search.text())
        self.word_list.set_records(records)
        self.word_count.setText(str(len(records)))
        self.word_list.setVisible(bool(records));self.words_empty.setVisible(not records)
        self.words_empty.setText(tr('Ничего не найдено') if self.search.text().strip() else tr('Сохранённых слов пока нет'))
        self.update_word_actions()
        if hasattr(self,'review_page'):self.review_page.refresh()

    def update_word_actions(self):
        for button in self.word_buttons:button.setEnabled(self.selected_record() is not None)

    def selected_record(self):
        item=self.word_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole)[0] if item else None

    def open_saved(self):
        ident = self.selected_record()
        record = next((r for r in self.store.words() if r[0]==ident),None)
        if record:
            self.show_card(record[1],record[3])
            self.card.saved_id = ident
            self.card.saved_game = record[4]
            self.card.answer.setPlainText(record[2])

    def delete_saved(self):
        ident = self.selected_record()
        if ident and QMessageBox.question(self,tr('Удалить слово'),tr('Удалить выбранную запись?'))==QMessageBox.StandardButton.Yes:
            self.store.delete_word(ident)
            self.refresh_library()

    def export_words(self):
        import json
        path,_ = QFileDialog.getSaveFileName(self,tr('Экспорт слов'),tr('Мои слова.json'),'JSON (*.json)')
        if path:
            values = [dict(zip(('id','term','meaning','sentence','game','created'),row)) for row in self.store.words()]
            Path(path).write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
            self.message(tr('Слова экспортированы.'))

    def stop(self):
        was_running=self.running
        target=getattr(self,'screen_target',None)
        return_from_result=hasattr(self,'result_window') and self.result_window.isActiveWindow()
        self.running = False
        self.screen_suspended=False
        # Release only work owned by this screen session. A late completion
        # must not clear the busy flag of a newer session or block a restart.
        if getattr(self,'screen_ocr_revision',None) is not None:self.ocr_busy=False
        if getattr(self,'screen_cloud_revision',None) is not None:self.cloud_busy=False
        self.screen_ocr_revision=self.screen_cloud_revision=None
        if hasattr(self,'recording_capture'):self.recording_capture.close()
        self.epoch.next()
        self.overlay.hide()
        if hasattr(self,'result_window'):self.result_window.hide()
        if hasattr(self,'keys'):self.keys.set_escape(getattr(self,'session_active',False))
        if hasattr(self,'start_button'):
            self.refresh_key_labels()
        if was_running and target and not self.closing:
            revision=self.epoch.value
            def restore_cursor():
                active=native.foreground()
                if return_from_result and (not active or native.is_our_window(active)):native.restore_foreground(target)
                native.refresh_window_cursor(target)
            self.after_transition_keys(restore_cursor,lambda:not self.closing and not self.running and self.epoch.accepts(revision))

    def manual_translate(self):
        text = self.manual.toPlainText().strip()
        if not text:
            self.message(tr('Введи текст или распознай кадр.'))
            return
        revision = self.card_epoch.next()
        settings = copy.deepcopy(self.settings)
        self.message(tr('Получаю перевод…'))
        def done(result):
            if self.card_epoch.accepts(revision):
                self.read_result.appendPlainText(text+'\n→ '+result[0]+'\n')
                self.message(tr('Перевод готов · ')+result[1])
        self.task(lambda:self.measurements.run('translate',lambda:self.translator.translate(settings,text,cancel=lambda:not self.card_epoch.accepts(revision))),done)





def launch():
    native.dpi_aware()
    app = QApplication(sys.argv)
    app.setApplicationName(NAME)
    app.setStyleSheet(STYLE)
    store = Store()
    lock = QLockFile(str(store.folder/'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,NAME,tr('Программа уже запущена.'))
        return 0
    window = MainWindow(store)
    window.show()
    window.offer_onboarding()
    return app.exec()
