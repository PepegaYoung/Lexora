import copy
import os
from pathlib import Path
import sys
import time
import webbrowser
from PIL import Image
import mss
from PySide6.QtCore import QObject,QRunnable,QThreadPool,Signal,QTimer,Qt,QLockFile
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QTabWidget,QComboBox,QLineEdit,QPlainTextEdit,QFormLayout,QSpinBox,QDoubleSpinBox,
    QFileDialog,QMessageBox,QTableWidget,QTableWidgetItem,QHeaderView,QInputDialog,QScrollArea)
from .core import Box,Stability,Generation,normalized
from .storage import Store,Dictionary,base_dir
from .dictionaries import Dictionaries
from .ui import UIBuilder
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
            self.signals.failed.emit('Не удалось выполнить операцию. Проверь настройки и повтори.')


class MainWindow(ShortcutCapture,Features,GameMode,ScreenMode,Upgrades,UIBuilder,QMainWindow):
    hotkey = Signal(str)
    native_error = Signal(str)
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.settings = self.store.settings()
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
        self.running = self.hover = self.ocr_busy = self.cloud_busy = False
        self.epoch = Generation()
        self.card_epoch = Generation()
        self.stability = Stability(.25)
        self.lines,self.history = (),[]
        self.pending_hover,self.hover_since,self.last_hover = None,0,None
        self.freeze = None
        self.closing = False
        self.hotkey_capture_active=False
        self.overlay = ScreenOverlay()
        self.card = Card()
        self.result_window=ResultWindow()
        self.result_window.dismissed.connect(self.stop)
        self.card.analyze.connect(lambda:self.analyze_card(True))
        self.card.translate_sentence.connect(lambda:self.analyze_card(False))
        self.card.save.connect(self.save_card)
        self.init_feature_state()
        self.setWindowTitle(f'{NAME} {VERSION}')
        self.resize(1120,830)
        self.setMinimumSize(880,580)
        root = QWidget()
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
        self.help_panel=HelpPanel()
        self.help=ContextHelp(self,self.help_panel)
        layout.addWidget(self.help_panel)
        self.status = QLabel('Готово')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(80)
        self.hover_timer.timeout.connect(self.hover_tick)
        self.hover_timer.start()
        self.hotkey.connect(self.on_hotkey)
        self.native_error.connect(self.message)
        self.keys = native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
        self.start_hotkeys()
        QApplication.instance().applicationStateChanged.connect(self.update_single_hotkeys)
        QApplication.instance().focusWindowChanged.connect(self.update_single_hotkeys)
        self.init_upgrades()
        self.init_design()
        self.configure_game_windows()
        self.refresh_account_label()
        self.refresh_library()
        self.start_feature_timers()

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

    def message(self,text):
        self.status.setText(text)
        if hasattr(self,'region_status'):self.region_status.setText(text)


    def refresh_key_labels(self):
        keys = {action:native.hotkey_label(value) for action,value in self.settings['hotkeys'].items()}
        self.capture_buttons['study'].setText('Выбрать слово · '+keys['study'])
        self.capture_buttons['region'].setText('Область · '+keys['region'])
        self.start_button.setText(('Остановить' if self.running else 'Автоперевод')+' · '+keys['toggle'])
        if hasattr(self,'snapshot_button'):self.snapshot_button.setText('Кадр · '+keys['screen'])
        state=self.settings.get('auto_card',True) if self.external_mode() else self.hover
        self.hover_button.setText(('Автокарточка: ' if self.external_mode() else 'Наведение: ')+('вкл.' if state else 'выкл.')+' · '+keys['hover'])


    def build_library(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Найти слово или исходную фразу')
        self.search.textChanged.connect(self.refresh_library)
        layout.addWidget(self.search)
        self.table = QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(['Слово','Перевод','Контекст','Игра','Дата'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for title,fn in [('Открыть запись',self.open_saved),('Удалить',self.delete_saved),('Экспорт JSON',self.export_words)]:
            button = QPushButton(title)
            button.clicked.connect(fn)
            row.addWidget(button)
        layout.addLayout(row)
        self.tabs.addTab(page,'Мои слова')

    def change_monitor(self,index):
        self.stop()
        self.hover = False
        self.refresh_key_labels()
        self.monitor = self.monitors[index]
        self.region = None
        self.settings.update(region=None,monitor=self.monitor['name'])
        self.store.save_settings(self.settings)
        self.update_region_label()

    def update_region_label(self):
        self.region_label.setText('Область: '+(f'{round(self.region.w)} × {round(self.region.h)}' if self.region else 'не выбрана'))
        if self.region and self.region.h>self.monitor['h']*.25:
            self.region_label.setToolTip('Высокая область: сцена может мешать распознаванию. Для субтитров удобнее узкая полоса.')
        else:self.region_label.setToolTip('Размер выбранной области в пикселях монитора.')



    def save_profile(self):
        game = self.game.text().strip()
        if not game:
            self.message('Введи название игры.')
            return
        keys = ('region','monitor','filter','font_size','opacity','offset','screen_scope','screen_mode','overlay_background',
                'card_width','card_height','card_background')
        profile = {k:copy.deepcopy(self.settings.get(k)) for k in keys}
        profile['region'] = self.region.json() if self.region else None
        profile['monitor'] = self.monitor['name']
        self.settings['profiles'][game] = profile
        self.store.save_settings(self.settings)
        self.message('Профиль сохранён: '+game)

    def load_profile(self):
        names = list(self.settings['profiles'])
        if not names:
            self.message('Сначала сохрани профиль игры.')
            return
        game,accepted = QInputDialog.getItem(self,'Профиль игры','Выбери игру',names,0,False)
        if not accepted:
            return
        self.apply_profile(game)

    def apply_profile(self,game):
        profile = self.settings['profiles'][game]
        allowed={'region','monitor','filter','font_size','opacity','offset','screen_scope','screen_mode','overlay_background',
                 'card_width','card_height','card_background'}
        profile={k:v for k,v in profile.items() if k in allowed}
        monitor = next((m for m in self.monitors if m['name']==profile.get('monitor')),None)
        self.stop()
        self.close_session(restore=False)
        self.hover = False
        self.lines = ()
        self.refresh_key_labels()
        self.game.setText(game)
        if monitor is None:
            self.region = None
            self.update_region_label()
            self.message('Монитор профиля не найден. Выбери новый монитор и область.')
            return
        self.monitor_pick.blockSignals(True)
        self.monitor_pick.setCurrentIndex(self.monitors.index(monitor))
        self.monitor_pick.blockSignals(False)
        self.monitor = monitor
        self.settings.update(profile,game=game)
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
        self.size_pick.setValue(self.settings['font_size'])
        self.opacity_pick.setValue(round(self.settings['opacity']*100))
        self.offset_pick.setValue(self.settings['offset'])
        self.apply_profile_appearance(profile)
        self.store.save_settings(self.settings)
        self.update_region_label()
        self.message('Профиль загружен: '+game)


    def login(self,new):
        self.stop()
        self.card_epoch.next()
        for button in (self.login_button,self.new_login_button,self.logout_button):
            button.setEnabled(False)
        self.message('Ожидаю вход в браузере. Разреши использование подписки и вернись в программу.')
        def finish(profile=None,error=None):
            for button in (self.login_button,self.new_login_button,self.logout_button):
                button.setEnabled(True)
            self.refresh_account_label()
            if error:
                self.message(error)
            elif PLAN_SCOPE not in profile.get('scopes',[]):
                self.message('Вход выполнен, но использование подписки не разрешено. Повтори вход с разрешением.')
            else:
                self.provider.setCurrentIndex(self.provider.findData('subscription'))
                self.message('Подписка подключена. Получи список моделей, выбери модель и примени настройки.')
                self.get_models()
        self.task(lambda:self.auth.sign_in(new),lambda profile:finish(profile),lambda error:finish(error=error))

    def logout(self):
        self.stop()
        self.card_epoch.next()
        self.message('Отключаю аккаунт…')
        def done(confirmed):
            self.translator.cache.clear()
            self.refresh_account_label()
            self.message('Аккаунт отключён.' if confirmed else 'Отключён локально. Отзыв доступа не подтверждён: отключи приложение также в настройках ChatGPT.')
        self.task(self.auth.sign_out,done)


    def save_api_key(self):
        key = self.api_key.text().strip()
        if not key:
            self.message('Введи ключ в поле API-ключа.')
            return
        self.stop()
        self.card_epoch.next()
        self.store.vault.set('api_key',key)
        self.api_key.clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message('Ключ сохранён с защитой Windows. Теперь можно получить список моделей.')

    def delete_api_key(self):
        self.stop()
        self.card_epoch.next()
        self.store.vault.set('api_key',None)
        self.api_key.clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message('API-ключ удалён. Подключение подписки сохранено.')

    def check_connection(self):
        if not self.apply_settings():
            return
        settings = copy.deepcopy(self.settings)
        self.task(lambda:self.translator.translate(settings,'Hello, world!',fresh=True),
                  lambda result:self.message('Проверка завершена: '+result[0]))

    def choose_model(self):
        path = QFileDialog.getExistingDirectory(self,'Папка en-ru с sentencepiece.model')
        if path:
            self.local_path.setText(path)


    @staticmethod
    def capture_image(box):
        with mss.mss() as capture:
            frame = capture.grab({'left':round(box.x),'top':round(box.y),'width':round(box.w),'height':round(box.h)})
            return Image.frombytes('RGB',frame.size,frame.rgb)








    def save_card(self):
        term = self.card.term.text().strip()
        answer = self.card.answer.toPlainText().strip()
        if not answer:
            answer = self.dictionary.lookup(term)
        if not term or not answer:
            self.card.status.setText('Заполни слово и перевод перед сохранением.')
            return
        ident = getattr(self.card,'saved_id',None)
        if ident:
            self.store.edit_word(ident,term,answer,self.card.sentence.toPlainText(),self.card.saved_game or self.game.text())
        else:
            self.store.save_word(term,answer,self.card.sentence.toPlainText(),self.game.text())
        self.card.status.setText('Сохранено в «Мои слова»')
        self.refresh_library()

    def refresh_library(self):
        if not hasattr(self,'table'):
            return
        records = self.store.words(self.search.text())
        self.table.setRowCount(len(records))
        for row,record in enumerate(records):
            for col,value in enumerate(record[1:]):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole,record[0])
                self.table.setItem(row,col,item)
        if hasattr(self,'review_page'):self.review_page.refresh()

    def selected_record(self):
        row = self.table.currentRow()
        return None if row<0 else self.table.item(row,0).data(Qt.ItemDataRole.UserRole)

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
        if ident and QMessageBox.question(self,'Удалить слово','Удалить выбранную запись?')==QMessageBox.StandardButton.Yes:
            self.store.delete_word(ident)
            self.refresh_library()

    def export_words(self):
        import json
        path,_ = QFileDialog.getSaveFileName(self,'Экспорт слов','Мои слова.json','JSON (*.json)')
        if path:
            values = [dict(zip(('id','term','meaning','sentence','game','created'),row)) for row in self.store.words()]
            Path(path).write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
            self.message('Слова экспортированы.')

    def stop(self):
        self.running = False
        self.epoch.next()
        self.overlay.hide()
        if hasattr(self,'result_window'):self.result_window.hide()
        if hasattr(self,'keys'):self.keys.set_escape(getattr(self,'session_active',False))
        if hasattr(self,'start_button'):
            self.refresh_key_labels()

    def toggle_hover(self):
        if self.external_mode():
            self.auto_card_pick.setChecked(not self.auto_card_pick.isChecked())
            self.refresh_key_labels()
            return
        if not self.region:
            self.message('Для наведения сначала выбери область с текстом.')
            return
        self.hover = not self.hover
        self.refresh_key_labels()
        self.message('Наведение работает со свободным курсором. Для управления камерой используй '+self.settings['hotkeys']['study']+'.')

    def manual_translate(self):
        text = self.manual.toPlainText().strip()
        if not text:
            self.message('Введи текст или распознай кадр.')
            return
        revision = self.card_epoch.next()
        settings = copy.deepcopy(self.settings)
        self.message('Получаю перевод…')
        def done(result):
            if self.card_epoch.accepts(revision):
                self.read_result.appendPlainText(text+'\n→ '+result[0]+'\n')
                self.message('Перевод готов · '+result[1])
        self.task(lambda:self.measurements.run('translate',lambda:self.translator.translate(settings,text,cancel=lambda:not self.card_epoch.accepts(revision))),done)

    def hover_tick(self):
        if not self.hover or not self.region or self.freeze:
            return
        x,y = native.cursor()
        source_box=getattr(self,'ocr_box',self.region)
        point = x-source_box.x,y-source_box.y
        found = next(((word,line) for line in self.lines for word in line.words if word.box.contains(*point)),None)
        identity = (found[0].text,found[1].text) if found else None
        if identity is None:
            self.last_hover = None
        if identity!=self.pending_hover:
            self.pending_hover,self.hover_since = identity,time.monotonic()
        if identity and identity!=self.last_hover and time.monotonic()-self.hover_since>.45:
            self.last_hover = identity
            self.show_card(*identity,activate=False)




def launch():
    native.dpi_aware()
    app = QApplication(sys.argv)
    app.setApplicationName(NAME)
    app.setStyleSheet(STYLE)
    store = Store()
    lock = QLockFile(str(store.folder/'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,NAME,'Программа уже запущена.')
        return 0
    window = MainWindow(store)
    window.show()
    return app.exec()
