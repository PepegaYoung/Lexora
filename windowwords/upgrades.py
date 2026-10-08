import copy
import json
from pathlib import Path
import re
import time
import webbrowser
from PIL import Image
from PySide6.QtCore import QObject,QEvent,Qt,QTimer,QByteArray,QPointF
from PySide6.QtGui import QPixmap,QPainter,QColor,QFont,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QSystemTrayIcon,QMenu,QFileDialog,QMessageBox,
    QInputDialog,QListWidgetItem,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QFormLayout,QComboBox)
from . import native,ocr
from .core import Box,Stability,Generation
from .models import download_model
from .providers import LABELS,CLASSICAL
from .widgets import Freeze,qimage
from .ui import note
from .design import NAME
from .storage import base_dir
from .card_layout import place_card


class SessionFilter(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window = window

    def eventFilter(self,object,event):
        if self.window.session_active and event.type() in (QEvent.Type.KeyPress,QEvent.Type.ShortcutOverride) and event.key()==Qt.Key.Key_Escape:
            event.accept()
            if event.type()==QEvent.Type.KeyPress:self.window.close_session()
            return True
        return False


class Upgrades:
    def init_upgrades(self):
        self.capture_epoch = Generation()
        self.session_active = self.session_closing = False
        self.session_target = None
        self.session_return_main = False
        self.session_filter = SessionFilter(self)
        QApplication.instance().installEventFilter(self.session_filter)
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.card.dismissed.connect(self.close_session)
        self.card.translate_source.connect(lambda:self.analyze_card(False,True))
        self.setWindowIcon(QIcon(str(base_dir()/'assets/logo.png')))
        self.card.setWindowIcon(self.windowIcon())
        self.result_window.setWindowIcon(self.windowIcon())
        self.card.wiktionary.connect(self.open_wiktionary)
        self.card.term.editingFinished.connect(lambda:self.card.dictionary.setPlainText(self.dictionary.lookup(self.card.term.text()) or 'Слово не найдено'))
        native.exclude_capture(self)
        self.tray = QSystemTrayIcon(self.windowIcon(),self)
        self.tray.setToolTip(NAME+' · английский через игры')
        menu = QMenu(self)
        menu.addAction('Открыть '+NAME,self.show_main)
        menu.addAction('Закрыть разбор / карточку',self.close_session)
        menu.addSeparator()
        menu.addAction('Завершить '+NAME,self.close)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.show_main() if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.show()
        self.style_base = QApplication.instance().styleSheet()
        self.apply_appearance(persist=False)
        if self.settings.get('window_geometry'):
            self.restoreGeometry(QByteArray.fromHex(self.settings['window_geometry'].encode()))

    def open_link(self,url):webbrowser.open(url)

    def open_free_site(self,url):
        text = self.manual.toPlainText().strip()
        if not text:
            self.message('Сначала введи или распознай английский текст во вкладке «История».')
            return
        QApplication.clipboard().setText(text)
        self.open_link(url)
        self.message('Английский текст скопирован. Вставь его на сайте через Ctrl+V и выбери русский язык.')

    def show_main(self):
        self.close_session(restore=False)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def begin_session(self):
        if self.session_active:return
        self.session_target = native.foreground()
        self.session_return_main = not self.session_target or native.is_our_window(self.session_target)
        self.session_active = True
        self.keys.set_escape(True)

    def close_session(self,restore=True,closed_window=None):
        if self.session_closing:return
        was_active = self.session_active
        return_target,return_main = self.session_target,self.session_return_main
        active_window = native.foreground()
        if active_window and not native.is_our_window(active_window):
            return_target,return_main = active_window,False
        self.session_closing = True
        self.session_active = False
        self.capture_epoch.next()
        self.card_epoch.next()
        self.keys.set_escape(self.running)
        window,self.freeze = self.freeze,None
        self.card.hide()
        self.auto_translate_timer.stop()
        self.stop_speech()
        if self.card.windowHandle():self.card.windowHandle().setTransientParent(None)
        native.set_owner(self.card)
        if window is not None and window is not closed_window:window.close()
        if was_active and restore and not self.closing:
            if return_main:
                self.showNormal()
                self.raise_()
                self.activateWindow()
            else:
                native.restore_foreground(return_target)
        self.session_closing = False

    def capture_freeze(self,mode):
        if self.session_active:
            self.close_session()
            return
        self.stop()
        self.hover = False
        self.refresh_key_labels()
        self.begin_session()
        revision = self.capture_epoch.next()
        monitor = dict(self.monitor)
        self.card.hide()
        self.showMinimized()
        def capture():
            if not self.capture_epoch.accepts(revision):return
            self.task(lambda:self.capture_image(Box(monitor['x'],monitor['y'],monitor['w'],monitor['h'])),
                      lambda image:self.show_freeze(image,monitor,mode) if self.capture_epoch.accepts(revision) else None,
                      lambda error:self.capture_failure(error,revision))
        QTimer.singleShot(220,capture)

    def capture_failure(self,error,revision):
        if self.capture_epoch.accepts(revision):
            self.close_session()
            self.message(error)

    def show_freeze(self,image,monitor,mode):
        window = Freeze(image,monitor,mode)
        self.freeze = window
        revision = self.capture_epoch.value
        window.closed.connect(lambda:self.freeze_closed(window))
        window.selected.connect(lambda crop,box,term,sentence:self.freeze_selected(window,crop,box,term,sentence))
        if self.external_mode():
            window.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
            window.setWindowTitle(NAME+' · '+('Выбор области' if mode=='region' else 'Разбор кадра'))
            window.show_on_monitor(topmost=False,fullscreen=True)
        else:window.show_on_monitor()
        window.set_auto_card(self.settings.get('auto_card',True))
        window.hovered.connect(lambda term,sentence:self.show_card(term,sentence,activate=False) if self.freeze is window and self.capture_epoch.accepts(revision) else None)
        if mode=='study':
            profile = self.settings['filter']
            def done(lines):
                if self.freeze is window and self.capture_epoch.accepts(revision):window.set_lines(lines)
            def failed(error):
                if self.freeze is window and self.capture_epoch.accepts(revision):
                    window.notice = error
                    window.update()
            self.task(lambda:self.measurements.run('ocr',lambda:ocr.read(image,profile)),done,failed)

    def freeze_closed(self,window):
        if self.freeze is window:self.close_session(closed_window=window)

    def set_auto_card(self,enabled):
        self.settings['auto_card']=bool(enabled)
        self.store.save_settings(self.settings)
        if self.freeze:self.freeze.set_auto_card(enabled)
        self.refresh_key_labels()

    def freeze_selected(self,window,crop,box,term,sentence):
        if window.mode=='region':
            self.region = Box(window.monitor['x']+box.x,window.monitor['y']+box.y,box.w,box.h)
            self.screen_scope.blockSignals(True)
            self.screen_scope.setCurrentIndex(self.screen_scope.findData('region'))
            self.screen_scope.blockSignals(False)
            self.settings.update(region=self.region.json(),monitor=window.monitor['name'],auto_start_region=self.auto_start_region.isChecked(),screen_scope='region')
            self.store.save_settings(self.settings)
            self.stability = Stability(.25)
            self.update_region_label()
            self.close_session()
            if self.auto_start_region.isChecked():self.toggle()
            else:self.message('Область готова. Нажми «Начать перевод области» или '+self.settings['hotkeys']['toggle']+'.')
        elif term:self.show_card(term,sentence or term)
        elif crop:
            revision = self.capture_epoch.value
            window.notice = 'Распознаю выделенное… Escape — вернуться в игру.'
            window.update()
            def done(lines):
                if self.freeze is not window or not self.capture_epoch.accepts(revision):return
                text = '\n'.join(line.text for line in lines)
                if text:self.show_card(text,text)
                else:
                    window.notice = 'Текст не найден. Попробуй профиль OCR или другой участок.'
                    window.update()
            self.task(lambda:self.measurements.run('ocr',lambda:ocr.read(crop,self.settings['filter'])),done)

    def open_image(self):
        path,_ = QFileDialog.getOpenFileName(self,'Открыть игровой кадр','','Изображения (*.png *.jpg *.jpeg *.bmp)')
        if not path:return
        try:image = Image.open(path).convert('RGB')
        except Exception:
            self.message('Не удалось открыть изображение.')
            return
        self.close_session(restore=False)
        self.stop()
        self.begin_session()
        self.showMinimized()
        self.show_freeze(image,dict(self.monitor),'study')

    def show_card(self,term,sentence,activate=True):
        if not term.strip():
            self.message('Выбери или введи слово.')
            return
        self.begin_session()
        self.card_epoch.next()
        self.card.saved_id = self.card.saved_game = None
        # A transient owner keeps the normal card above its fullscreen snapshot,
        # without turning it into a desktop-wide topmost overlay or a QObject child.
        self.card.winId()
        owner=self.freeze.windowHandle() if self.freeze else None
        self.card.windowHandle().setTransientParent(owner)
        self.card.setWindowOpacity(1.0)
        self.card.populate(term,sentence,self.dictionary.lookup(term))
        native.set_owner(self.card,self.freeze)
        explain = self.settings['provider'] in ('subscription','api')
        self.card.explain_button.setEnabled(explain)
        self.card.explain_button.setToolTip('Объяснение через выбранный GPT' if explain else 'Для объяснения выбери ChatGPT или OpenAI API на вкладке «Перевод».')
        x,y = native.cursor()
        monitor = next((m for m in self.monitors if Box(m['x'],m['y'],m['w'],m['h']).contains(x,y)),self.monitor)
        screens = QApplication.screens()
        scale = next((s.devicePixelRatio() for s in screens if s.name()==monitor['name']),self.card.devicePixelRatioF())
        width,height = min(monitor['w']-24,round(self.settings['card_width']*scale)),min(monitor['h']-24,round(self.settings['card_height']*scale))
        anchor=Box(x,y,1,1)
        if self.freeze:
            rect=self.freeze.image_rect()
            px,py=self.freeze.image_point(QPointF((x-monitor['x'])/scale,(y-monitor['y'])/scale))
            word=next((w for line in self.freeze.lines for w in line.words if w.box.contains(px,py)),None)
            if word:
                b=word.box
                sx=rect.width()/self.freeze.image.width*scale
                sy=rect.height()/self.freeze.image.height*scale
                anchor=Box(monitor['x']+rect.x()*scale+b.x*sx,monitor['y']+rect.y()*scale+b.y*sy,b.w*sx,b.h*sy)
        box=place_card(Box(monitor['x'],monitor['y'],monitor['w'],monitor['h']),anchor,width,height)
        native.place(self.card,box,activate=activate,topmost=not self.external_mode())
        self.card.raise_()
        if activate:self.card.activateWindow()
        native.raise_window(self.card,activate=activate)
        if self.settings.get('auto_translate_card'):self.auto_translate_timer.start(350)

    def analyze_card(self,word,whole=False,automatic=False):
        term = self.card.term.text().strip()
        source = self.card.sentence.toPlainText().strip() or term
        text = source if word or whole else term
        if not text:
            self.card.status.setText('Выдели или введи текст.')
            return
        revision = self.card_epoch.next()
        settings = copy.deepcopy(self.settings)
        context = tuple(item[0] for item in self.history[-2:])+(source,)
        self.card.status.setText('Получаю '+('объяснение' if word else 'перевод')+' · '+LABELS[settings['provider']])
        if automatic:self.auto_card_inflight=True
        def finish_auto():
            if not automatic:return
            self.auto_card_inflight=False
            if not self.closing and revision!=self.card_epoch.value and self.card.isVisible():self.auto_translate_timer.start(350)
        def done(result):
            finish_auto()
            if self.card_epoch.accepts(revision) and self.card.isVisible():
                self.card.answer.setPlainText(result[0])
                self.card.status.setText('Готово')
        def fail(error):
            finish_auto()
            if self.card_epoch.accepts(revision):self.card.status.setText(error)
        self.task(lambda:self.measurements.run('translate',lambda:self.translator.translate(settings,text,context,term if word else '',
            cancel=lambda:not self.card_epoch.accepts(revision))),done,fail)

    def select_provider(self):
        self.stop()
        self.card_epoch.next()
        provider = self.provider.currentData()
        if hasattr(self,'model_catalogs'):
            self.display_models(provider)
            self.model_refresh_button.setEnabled(provider not in self.model_requests)
        self.sync_provider_page()
        self.message('Настрой '+LABELS[provider]+' и нажми «Использовать этот переводчик».')
        if hasattr(self,'model_catalogs'):self.get_models(force=False)

    def apply_settings(self):
        bindings = {k:f.text().strip() for k,f in self.hotkey_fields.items()}
        try:
            native.validate_bindings(bindings)
        except ValueError as error:
            self.message(str(error))
            return False
        self.stop()
        self.card_epoch.next()
        provider = self.provider.currentData()
        if provider in ('subscription','api'):
            model=self.model_pick.currentData()
            if not model:
                self.message('Подключи переводчик и выбери модель из списка.')
                self.get_models(force=False)
                return False
            self.settings['models'][provider]=model
        self.settings.update(provider=provider,filter=self.filter_pick.currentData(),game=self.game.text().strip(),
            local_model=self.local_path.text().strip(),model_download_dir=self.download_path.text().strip(),
            yandex_auth=self.yandex_auth.currentData(),yandex_folder=self.yandex_folder.text().strip(),deepl_plan=self.deepl_plan.currentData(),
            libre_url=self.libre_url.currentText().strip(),auto_start_region=self.auto_start_region.isChecked(),
            local_quality=self.local_quality_pick.currentData())
        if bindings!=self.settings['hotkeys']:
            self.keys.stop()
            self.keys.join(timeout=1)
            self.settings['hotkeys'] = bindings
            if not self.hotkey_capture_active:
                self.keys = native.Hotkeys(self.hotkey.emit,self.native_error.emit,bindings,not self.external_mode())
                self.keys.set_escape(self.session_active or self.running)
                self.start_hotkeys()
        self.apply_appearance()
        self.refresh_key_labels()
        self.refresh_account_label()
        self.message('Настройки сохранены · '+LABELS[provider]+'. Постоянный перевод на паузе.')
        return True

    def apply_appearance(self,persist=True):
        self.settings.update(ui_scale=self.ui_scale_pick.value(),theme=self.theme_pick.currentData(),
            card_width=self.card_width_pick.value(),card_height=self.card_height_pick.value(),
            card_opacity=self.card_opacity_pick.value()/100,font_size=self.size_pick.value(),
            opacity=self.opacity_pick.value()/100,offset=self.offset_pick.value(),
            card_background=self.card_background_pick.value()/100,overlay_background=self.overlay_background_pick.value()/100)
        css = self.style_base
        if self.settings['theme']=='light':
            for old,new in {'#111a28':'#f3f6fb','#101821':'#f3f6fb','#e4ebf5':'#17283b','#0c1420':'#f3f6fb','#f6fbff':'#142239',
                '#9cabc0':'#53647b','#20334a':'#e0e9f4','#34506c':'#bbcbe0','#2e4b69':'#d2e1f3','#0b1320':'#ffffff',
                '#33475e':'#b9c9de','#162234':'#e7edf6','#a8b8cd':'#40546e','#76d7ff':'#075a84','#26364b':'#d1dce9',
                '#1d373b':'#dbeee9','#7de0cc':'#247d74'}.items():css = css.replace(old,new)
        scale = self.settings['ui_scale']/100
        css = re.sub(r'font-size:(\d+)px',lambda m:f'font-size:{round(int(m[1])*scale)}px',css)
        css+='\nQPushButton#primary { color:#ffffff; }'
        QApplication.instance().setStyleSheet(css)
        metrics=self.tabs.list.fontMetrics()
        self.tabs.list.setFixedWidth(max(175,max(metrics.horizontalAdvance(self.tabs.list.item(i).text()) for i in range(self.tabs.count()))+72))
        for form in self.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows if scale>1.25 else QFormLayout.RowWrapPolicy.WrapLongRows)
            for row in range(form.rowCount()):
                item=form.itemAt(row,QFormLayout.ItemRole.LabelRole)
                if item and isinstance(item.widget(),QLabel):item.widget().setWordWrap(True)
        for combo in self.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        self.card.resize(self.settings['card_width'],self.settings['card_height'])
        self.card.setWindowOpacity(1.0)
        self.card.apply_background(self.settings['card_background'],self.settings['theme'])
        if self.overlay.isVisible() and self.running:self.draw_screen()
        if persist:
            self.store.save_settings(self.settings)
            self.message('Оформление применено. Размер текста, карточки и прозрачность сохранены.')

    def refresh_account_label(self):
        try:
            records = self.store.vault.read()
            profile = records.get('chatgpt',{})
            from .auth import PLAN_SCOPE
            ready = PLAN_SCOPE in profile.get('scopes',[]) and bool(profile.get('access_token'))
            self.account_label.setText((profile.get('email') or 'Аккаунт ChatGPT')+' · '+('подключён' if ready else 'не подключён'))
            for provider,label in self.cloud_status.items():
                key = 'api_key' if provider=='api' else provider+'_key'
                label.setText('Ключ сохранён и скрыт' if records.get(key) else 'Ключ ещё не добавлен')
            self.connection_banner.setText(LABELS[self.settings['provider']])
        except Exception:self.account_label.setText('Не удалось прочитать защищённое хранилище.')

    def save_cloud_key(self,provider):
        key = self.cloud_keys[provider].text().strip()
        if not key:
            self.message('Введи ключ '+LABELS[provider]+'.')
            return
        self.stop()
        self.card_epoch.next()
        self.store.vault.set(provider+'_key',key)
        self.cloud_keys[provider].clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message('Ключ защищён Windows. Примени настройки подключения.')

    def delete_cloud_key(self,provider):
        self.stop()
        self.card_epoch.next()
        self.store.vault.set(provider+'_key',None)
        self.cloud_keys[provider].clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message('Ключ '+LABELS[provider]+' удалён.')

    def choose_download_folder(self):
        path = QFileDialog.getExistingDirectory(self,'Куда скачать модель en-ru',self.download_path.text())
        if path:self.download_path.setText(path)

    def install_model(self):
        destination = self.download_path.text().strip()
        if not destination:
            self.choose_download_folder()
            destination = self.download_path.text().strip()
        if not destination:return
        self.settings['model_download_dir'] = destination
        self.store.save_settings(self.settings)
        self.download_button.setEnabled(False)
        self.message('Загружаю модель в '+destination+' и проверяю целостность…')
        def done(path):
            self.download_button.setEnabled(True)
            self.local_path.setText(path)
            self.message('Готово: '+path+'. Нажми «Использовать этот переводчик» для офлайн-режима.')
        def fail(error):
            self.download_button.setEnabled(True)
            self.message(error)
        self.task(lambda:download_model(self.store.folder,destination),done,fail)

    def refresh_dictionaries(self):
        self.dictionary_list.clear()
        for source in self.dictionary.sources():
            item = QListWidgetItem(source['name'])
            item.setData(Qt.ItemDataRole.UserRole,source['id'])
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if source['id'] in self.settings['dictionary_enabled'] else Qt.CheckState.Unchecked)
            self.dictionary_list.addItem(item)

    def apply_dictionaries(self):
        self.settings['dictionary_enabled'] = [self.dictionary_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.dictionary_list.count()) if self.dictionary_list.item(i).checkState()==Qt.CheckState.Checked]
        self.store.save_settings(self.settings)
        self.message('Выбор словарей сохранён.')

    def describe_dictionary(self,current,previous=None):
        if not current:return
        descriptions={
            'wiktionary':'Викисловарь · офлайн\nРусские значения английских слов, транскрипция, примеры и формы слов. Подробность зависит от статьи. Источник: ru.wiktionary.org, обработка Kaikki/Wiktextract. CC BY-SA 4.0.',
            'freedict':'FreeDict / WikDict · офлайн\nКороткие переводы английских слов на русский.',
            'wordnet':'WordNet 3.1 · офлайн\nОпределения, синонимы и примеры на английском.',
            'personal':'Мои слова · офлайн\nСохранённые тобой переводы и объяснения.',
        }
        ident=current.data(Qt.ItemDataRole.UserRole)
        self.dictionary_preview.setPlainText(descriptions.get(ident,'Пользовательский словарь · офлайн\nИмпортированные значения.'))

    def open_wiktionary(self):
        from urllib.parse import quote
        term=self.card.term.text().strip()
        if term:self.open_link('https://ru.wiktionary.org/wiki/'+quote(term,safe=''))

    def import_dictionary(self):
        path,_ = QFileDialog.getOpenFileName(self,'Добавить свой словарь','','Словари (*.json *.csv *.tsv)')
        if not path:return
        name,accepted = QInputDialog.getText(self,'Название словаря','Как подписать источник в карточке?',text=Path(path).stem)
        if not accepted:return
        try:
            source = self.dictionary.import_file(path,name)
            self.refresh_dictionaries()
            self.message(f"Добавлен {source['name']}: {source['entries']} записей.")
        except Exception as error:
            from .auth import ServiceError
            self.message(str(error) if isinstance(error,ServiceError) else 'Не удалось импортировать словарь.')

    def preview_ocr(self):
        if not self.region:
            self.message('Сначала выбери область с текстом на вкладке «В игре».')
            return
        self.stop()
        self.hover = False
        self.refresh_key_labels()
        self.begin_session()
        revision = self.capture_epoch.next()
        region,profile = self.region,self.filter_pick.currentData()
        self.showMinimized()
        def capture():
            if self.closing or not self.capture_epoch.accepts(revision):return
            def inspect():
                image = self.capture_image(region)
                start = time.perf_counter()
                lines = ocr.read(image,profile)
                return image,lines,round((time.perf_counter()-start)*1000)
            def done(result):
                if self.closing or not self.capture_epoch.accepts(revision):return
                self.close_session(restore=False)
                self.showNormal()
                image,lines,elapsed = result
                dialog = QDialog(self)
                dialog.setWindowTitle('Предпросмотр OCR · '+self.filter_pick.currentText())
                dialog.resize(950,640)
                layout = QVBoxLayout(dialog)
                row = QHBoxLayout()
                for caption,picture in [('Исходный кадр',image),('После обработки',ocr.prepare(image,profile))]:
                    column = QVBoxLayout()
                    column.addWidget(QLabel(caption))
                    label = QLabel()
                    label.setPixmap(QPixmap.fromImage(qimage(picture)).scaled(430,260,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
                    column.addWidget(label)
                    row.addLayout(column)
                layout.addLayout(row)
                layout.addWidget(note(f'{len(lines)} строк · {elapsed} мс. Проверь, сохранились ли буквы и обводка.'))
                text = QPlainTextEdit('\n'.join(l.text for l in lines) or 'Текст не найден. Попробуй другой профиль.')
                text.setReadOnly(True)
                layout.addWidget(text)
                button = QPushButton('Закрыть предпросмотр')
                button.clicked.connect(dialog.close)
                layout.addWidget(button)
                dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                dialog.show()
            self.task(inspect,done,lambda error:self.capture_failure(error,revision))
        QTimer.singleShot(220,capture)

    def on_hotkey(self,action):
        if self.hotkey_capture_active:return
        if action=='escape':
            if self.session_active:self.close_session()
            else:self.stop();self.message('Экранный перевод закрыт.')
        elif action in ('study','region'):self.capture_freeze(action)
        elif action=='toggle':self.toggle()
        elif action=='hover':self.toggle_hover()
        elif action=='screen':self.translate_screen_once()

    def closeEvent(self,event):
        self.closing = True
        if hasattr(self,'model_timer'):self.model_timer.stop()
        for field in self.hotkey_fields.values():field.finish()
        self.close_features()
        self.close_session(restore=False)
        self.stop()
        self.auth.cancel.set()
        self.keys.stop()
        self.settings['window_geometry'] = bytes(self.saveGeometry().toHex()).decode()
        self.store.save_settings(self.settings)
        self.tray.hide()
        QApplication.instance().removeEventFilter(self.session_filter)
        self.overlay.close()
        self.result_window.close()
        self.card.close()
        QMainWindow.closeEvent(self,event)
        QApplication.instance().quit()
