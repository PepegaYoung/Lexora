from .i18n import tr,trf
import copy
import json
from pathlib import Path
import re
import time
import webbrowser
from PIL import Image
from PySide6.QtCore import QObject,QEvent,Qt,QTimer,QByteArray,QPointF,QSignalBlocker
from PySide6.QtGui import QPainter,QColor,QFont,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QSystemTrayIcon,QMenu,QFileDialog,QMessageBox,QWidget,
    QInputDialog,QListWidgetItem,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QFormLayout,QComboBox)
from . import native,ocr
from .core import Box,Stability,Generation
from .models import download_model
from .providers import LABELS,CLASSICAL
from .widgets import Freeze,CARD_DEFAULT,CARD_SIZES
from .ui import note
from .design import NAME,WINDOW_SIZES
from .storage import base_dir,APPEARANCE_DEFAULTS
from .card_layout import place_card
from .safety import game_action


class SessionFilter(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window = window

    def eventFilter(self,object,event):
        if event.type()==QEvent.Type.Wheel and isinstance(object,QComboBox):
            event.ignore()
            return True
        if self.window.session_active and event.type() in (QEvent.Type.KeyPress,QEvent.Type.ShortcutOverride) and event.key()==Qt.Key.Key_Escape:
            help_menu=getattr(getattr(self.window,'help_button',None),'help_menu',None)
            if help_menu is not None and help_menu.isVisible():return False
            previews=getattr(self.window,'appearance_previews',None)
            if getattr(self.window,'onboarding_dialog',None) is not None or (previews and previews.dialogs):return False
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
        self.card.term.editingFinished.connect(lambda:self.card.dictionary.setPlainText(self.dictionary.lookup(self.card.term.text()) or tr('Слово не найдено')))
        native.exclude_capture(self)
        self.tray = QSystemTrayIcon(self.windowIcon(),self)
        self.tray.setToolTip(NAME+tr(' · английский через игры'))
        menu = QMenu(self)
        menu.addAction(tr('Открыть ')+NAME,self.show_main)
        menu.addAction(tr('Закрыть экранный словарь'),self.close_session)
        menu.addSeparator()
        menu.addAction(tr('Завершить ')+NAME,self.close)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.show_main() if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.show()
        self.style_base = QApplication.instance().styleSheet()
        self.apply_appearance(persist=False)
        if self.settings.get('window_geometry'):
            self.setMinimumSize(880,580);self.setMaximumSize(16777215,16777215)
            self.restoreGeometry(QByteArray.fromHex(self.settings['window_geometry'].encode()))
        self.apply_window_size(self.settings['window_preset'])
        self.appearance_ready=True
        self.window_size_pick.currentIndexChanged.connect(self.choose_window_size)
        self.theme_apply_timer=QTimer(self)
        self.theme_apply_timer.setSingleShot(True)
        self.theme_apply_timer.setInterval(250)
        self.theme_apply_timer.timeout.connect(self.apply_appearance)
        self.theme_pick.currentIndexChanged.connect(lambda:self.theme_apply_timer.start())
        self.card_theme_pick.currentIndexChanged.connect(self.choose_card_theme)
        self.overlay_theme_pick.currentIndexChanged.connect(self.choose_overlay_style)
        self.overlay_background_pick.valueChanged.connect(self.choose_overlay_style)
        self.apply_size_locks()

    def change_size_locks(self,*args):
        self.settings.update(window_size_locked=self.window_lock_pick.isChecked(),card_size_locked=self.card_lock_pick.isChecked())
        self.apply_size_locks();self.store.save_settings(self.settings)

    def apply_size_locks(self):
        from .themes import palette
        from .ui_icons import device_icon
        colors=palette(self.settings['theme'])
        for control,key in ((self.window_lock_pick,'window_size_locked'),(self.card_lock_pick,'card_size_locked')):
            locked=self.settings[key];kind='lock' if locked else 'unlock'
            control.setProperty('iconKind',kind);control.setIcon(device_icon(kind,colors['light'],colors['accent']))
            control.setAccessibleName(tr('Запретить изменение размера мышью'))
            control.setToolTip(tr('Размер зафиксирован. Нажми, чтобы разрешить растягивание мышью.') if locked else
                               tr('Размер можно менять мышью. Нажми, чтобы зафиксировать.'))
        if self.settings['window_size_locked']:self.setFixedSize(self.size())
        else:self.setMinimumSize(880,580);self.setMaximumSize(16777215,16777215)
        self.card.set_size_locked(self.settings['card_size_locked'])

    def choose_window_size(self,*args):
        key=self.window_size_pick.currentData()
        if key not in WINDOW_SIZES:return
        self.apply_window_size(key)
        with QSignalBlocker(self.window_size_pick):self.window_size_pick.setCurrentIndex(self.window_size_pick.findData(key))
        self.settings.update(window_preset=key,window_geometry=bytes(self.saveGeometry().toHex()).decode())
        self.store.save_settings(self.settings)

    def choose_card_theme(self,*args):
        self.settings['card_theme']=self.card_theme_pick.currentData()
        self.card.apply_background(self.card_background_pick.value()/100,self.settings['card_theme'] or self.settings['theme'])
        self.store.save_settings(self.settings)

    def choose_overlay_style(self,*args):
        self.settings.update(overlay_theme=self.overlay_theme_pick.currentData(),overlay_background=self.overlay_background_pick.value()/100)
        if self.running and self.overlay.isVisible():self.draw_screen()
        self.store.save_settings(self.settings)

    def reset_appearance(self):
        defaults=APPEARANCE_DEFAULTS
        for control,key in ((self.theme_pick,'theme'),(self.card_theme_pick,'card_theme'),(self.overlay_theme_pick,'overlay_theme'),(self.window_size_pick,'window_preset')):
            with QSignalBlocker(control):control.setCurrentIndex(control.findData(defaults[key]))
        for control in (self.window_lock_pick,self.card_lock_pick):
            with QSignalBlocker(control):control.setChecked(False)
        for control,key,multiplier in ((self.ui_scale_pick,'ui_scale',1),(self.card_width_pick,'card_width',1),
                (self.card_height_pick,'card_height',1),(self.card_opacity_pick,'card_opacity',100),
                (self.size_pick,'font_size',1),(self.opacity_pick,'opacity',100),(self.offset_pick,'offset',1),
                (self.card_background_pick,'card_background',100),(self.overlay_background_pick,'overlay_background',100)):
            control.setValue(round(defaults[key]*multiplier))
        self.apply_appearance()
        self.message(tr('Оформление сброшено к стандартным настройкам.'))

    def apply_window_size(self,key):
        if key not in WINDOW_SIZES:return
        self.setMinimumSize(880,580);self.setMaximumSize(16777215,16777215)
        area=self.screen().availableGeometry();width,height=WINDOW_SIZES[key]
        frame=self.frameGeometry();geometry=self.geometry()
        frame_width=max(16,frame.width()-geometry.width());frame_height=max(38,frame.height()-geometry.height())
        width=min(width,max(self.minimumWidth(),area.width()-frame_width))
        height=min(height,max(self.minimumHeight(),area.height()-frame_height))
        self.window_target_size=(width,height);self.window_size_applying=True
        try:
            if self.isMaximized():self.showNormal()
            self.resize(width,height)
            self.move(max(area.x(),min(self.x(),area.right()+1-width-frame_width)),
                      max(area.y(),min(self.y(),area.bottom()+1-height-frame_height)))
        finally:
            self.window_size_applying=False
            if self.settings['window_size_locked']:self.setFixedSize(self.size())

    def reset_window_size(self):
        with QSignalBlocker(self.window_size_pick):self.window_size_pick.setCurrentIndex(self.window_size_pick.findData('720p'))
        self.settings['window_preset']='720p';self.apply_window_size('720p')
        self.settings['window_geometry']=bytes(self.saveGeometry().toHex()).decode()
        self.store.save_settings(self.settings)

    def choose_card_size(self,*args):
        size=CARD_SIZES.get(self.card_size_pick.currentData())
        if size:
            self.card_width_pick.setValue(size[0]);self.card_height_pick.setValue(size[1])

    def save_card_size(self,width,height):
        width=max(320,min(1000,width));height=max(320,min(1100,height))
        for control,value in ((self.card_width_pick,width),(self.card_height_pick,height),
                              (self.card_scale_pick,round(width/CARD_DEFAULT[0]*100))):
            with QSignalBlocker(control):control.setValue(value)
        key=next((key for key,size in CARD_SIZES.items() if size==(width,height)),'custom')
        with QSignalBlocker(self.card_size_pick):self.card_size_pick.setCurrentIndex(self.card_size_pick.findData(key))
        self.settings.update(card_width=width,card_height=height);self.store.save_settings(self.settings)

    def reset_card_size(self):
        self.save_card_size(*CARD_DEFAULT)
        self.card.set_size_locked(False)
        area=self.card.screen().availableGeometry()
        self.card.resize(min(CARD_DEFAULT[0],area.width()-16),min(CARD_DEFAULT[1],area.height()-16))
        self.card.move(max(area.x()+8,min(self.card.x(),area.right()+1-self.card.width()-8)),
                       max(area.y()+8,min(self.card.y(),area.bottom()+1-self.card.height()-8)))
        self.card.set_size_locked(self.settings['card_size_locked'])

    def open_link(self,url):webbrowser.open(url)

    def save_interface_language(self):
        self.settings['ui_language']=self.language_pick.currentData()
        self.store.save_settings(self.settings)
        self.message(tr('Язык интерфейса сохранён. Перезапусти Lexora, чтобы применить изменение.'))

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
        self.keys.set_escape(self.running and getattr(self,'screen_snapshot',False))
        window,self.freeze = self.freeze,None
        for grabber in (QWidget.mouseGrabber(),QWidget.keyboardGrabber()):
            if grabber and any(owner and (grabber is owner or owner.isAncestorOf(grabber)) for owner in (window,self.card)):
                grabber.releaseMouse();grabber.releaseKeyboard()
        self.card.hide()
        self.auto_translate_timer.stop()
        self.stop_speech()
        if self.card.windowHandle():self.card.windowHandle().setTransientParent(None)
        native.set_owner(self.card)
        if window is not None:
            window.unsetCursor();window.hide()
            if window is not closed_window:window.close()
        if was_active and restore and not self.closing:
            revision=self.capture_epoch.value
            def restore_focus():
                if return_main:
                    self.showNormal();self.raise_();self.activateWindow()
                else:
                    active=native.foreground()
                    if active and not native.is_our_window(active) and active!=return_target:return
                    if native.restore_foreground(return_target):native.refresh_window_cursor(return_target)
            self.after_transition_keys(restore_focus,lambda:not self.closing and not self.session_active and self.capture_epoch.accepts(revision))
        self.session_closing = False

    def after_transition_keys(self,callback,valid):
        def poll():
            if not valid():return
            if native.transition_keys_held():QTimer.singleShot(25,poll)
            else:callback()
        QTimer.singleShot(0,poll)

    @game_action
    def capture_freeze(self,mode):
        if self.session_active:
            self.close_session()
            return
        if self.settings.get('recording_visible',False) and not self.prepare_recording_capture():return
        self.stop()
        self.refresh_key_labels()
        self.begin_session()
        revision = self.capture_epoch.next()
        monitor = dict(self.monitor)
        self.card.hide()
        self.showMinimized()
        def capture():
            if not self.capture_epoch.accepts(revision):return
            self.task(lambda:self.capture_session_image(Box(monitor['x'],monitor['y'],monitor['w'],monitor['h']),revision),
                      lambda image:self.show_freeze(image,monitor,mode) if self.capture_epoch.accepts(revision) else None,
                      lambda error:self.capture_failure(error,revision))
        QTimer.singleShot(220,lambda:self.after_transition_keys(capture,lambda:self.capture_epoch.accepts(revision) and self.session_active and not self.closing))

    def capture_failure(self,error,revision):
        if self.capture_epoch.accepts(revision):
            self.close_session()
            self.message(error)

    @game_action
    def show_freeze(self,image,monitor,mode):
        content_box=None
        if self.settings.get('recording_visible',False) and getattr(self,'recording_target',None):
            from .recording_capture import window_bounds
            from .screen import intersection
            try:
                bounds=intersection(window_bounds(self.recording_target),Box(monitor['x'],monitor['y'],monitor['w'],monitor['h']))
                if bounds.w>0 and bounds.h>0:content_box=Box(bounds.x-monitor['x'],bounds.y-monitor['y'],bounds.w,bounds.h)
            except RuntimeError:pass
        window = Freeze(image,monitor,mode,content_box)
        window.setProperty('captureVisible',self.settings.get('recording_visible',False))
        self.freeze = window
        revision = self.capture_epoch.value
        window.closed.connect(lambda:self.freeze_closed(window))
        window.selected.connect(lambda crop,box,term,sentence:self.freeze_selected(window,crop,box,term,sentence))
        window.selection_started.connect(self.hide_snapshot_card)
        if self.external_mode():
            window.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
            window.setWindowTitle(NAME+' · '+(tr('Выбор области') if mode=='region' else tr('Экранный словарь')))
            window.show_on_monitor(topmost=False,fullscreen=True)
        else:window.show_on_monitor()
        window.set_auto_card(self.settings.get('auto_card',True))
        window.hovered.connect(lambda term,sentence:self.show_card(term,sentence,activate=False) if self.freeze is window and self.capture_epoch.accepts(revision) else None)
        if mode=='study':
            profile = self.settings['filter']
            engine=self.settings.get('ocr_engine','windows')
            device=self.settings.get('ocr_device','gpu')
            def done(lines):
                if self.freeze is window and self.capture_epoch.accepts(revision):window.set_lines(lines)
            def failed(error):
                if self.freeze is window and self.capture_epoch.accepts(revision):
                    window.notice = error
                    window.update()
            self.task(lambda:self.measurements.run('ocr',lambda:ocr.read(image,profile,engine,device)),done,failed)

    def freeze_closed(self,window):
        if self.freeze is window:self.close_session(closed_window=window)

    def hide_snapshot_card(self):
        self.card_epoch.next()
        self.auto_translate_timer.stop()
        self.stop_speech()
        self.card.hide()

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
            self.scope_buttons['region'].setChecked(True)
            self.sync_capture_controls()
            self.settings.update(region=self.region.json(),monitor=window.monitor['name'],screen_scope='region')
            self.store.save_settings(self.settings)
            self.stability = Stability(.25)
            self.update_region_label()
            self.close_session()
            self.message(tr('Область готова. Нажми «Автоперевод» или ')+self.settings['hotkeys']['toggle']+'.')
        elif term:self.show_card(term,sentence or term)
        elif crop:
            revision = self.capture_epoch.value
            window.notice = tr('Распознаю выделенное… Escape — вернуться в игру.')
            window.update()
            def done(lines):
                if self.freeze is not window or not self.capture_epoch.accepts(revision):return
                text = '\n'.join(line.text for line in lines)
                if text:self.show_card(text,text)
                else:
                    window.notice = tr('Текст не найден. Попробуй профиль OCR или другой участок.')
                    window.update()
            profile=self.settings['filter'];engine=self.settings.get('ocr_engine','windows');device=self.settings.get('ocr_device','gpu')
            self.task(lambda:self.measurements.run('ocr',lambda:ocr.read(crop,profile,engine,device)),done)

    @game_action
    def open_image(self):
        path,_ = QFileDialog.getOpenFileName(self,tr('Открыть игровой кадр'),'',tr('Изображения (*.png *.jpg *.jpeg *.bmp)'))
        if not path:return
        try:image = Image.open(path).convert('RGB')
        except Exception:
            self.message(tr('Не удалось открыть изображение.'))
            return
        self.close_session(restore=False)
        self.stop()
        self.begin_session()
        self.showMinimized()
        self.show_freeze(image,dict(self.monitor),'study')

    @game_action
    def show_card(self,term,sentence,activate=True):
        if not term.strip():
            self.message(tr('Выбери или введи слово.'))
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
        self.card.explain_button.setToolTip(tr('Объяснение через выбранный GPT') if explain else tr('Для объяснения выбери ChatGPT или OpenAI API на вкладке «Перевод».'))
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
        self.card.set_size_locked(False)
        native.place(self.card,box,activate=activate,topmost=not self.external_mode())
        self.card.set_size_locked(self.settings['card_size_locked'])
        self.card.raise_()
        if activate:self.card.activateWindow()
        native.raise_window(self.card,activate=activate)
        if self.settings.get('auto_translate_card'):self.auto_translate_timer.start(350)

    @game_action
    def analyze_card(self,word,whole=False,automatic=False):
        term = self.card.term.text().strip()
        source = self.card.sentence.toPlainText().strip() or term
        text = source if word or whole else term
        if not text:
            self.card.status.setText(tr('Выдели или введи текст.'))
            return
        revision = self.card_epoch.next()
        settings = copy.deepcopy(self.settings)
        context = tuple(item[0] for item in self.history[-2:])+(source,)
        self.card.status.setText(tr('Получаю ')+(tr('объяснение') if word else tr('перевод'))+' · '+tr(LABELS[settings['provider']]))
        if automatic:self.auto_card_inflight=True
        def finish_auto():
            if not automatic:return
            self.auto_card_inflight=False
            if not self.closing and revision!=self.card_epoch.value and self.card.isVisible():self.auto_translate_timer.start(350)
        def done(result):
            finish_auto()
            if self.card_epoch.accepts(revision) and self.card.isVisible():
                self.card.answer.setPlainText(result[0])
                self.card.status.setText(tr('Готово'))
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
        self.message(tr('Настрой ')+tr(LABELS[provider])+tr(' и нажми «Использовать».'))
        if hasattr(self,'model_catalogs'):self.get_models(force=False)

    def apply_settings(self):
        bindings = self.current_bindings()
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
                self.message(tr('Подключи переводчик и выбери модель из списка.'))
                self.get_models(force=False)
                return False
            self.settings['models'][provider]=model
        self.settings.update(provider=provider,filter=self.filter_pick.currentData(),ocr_engine=self.ocr_engine_pick.currentData(),ocr_device=self.ocr_device_pick.currentData(),game=self.game.text().strip(),
            local_model=self.local_path.text().strip(),model_download_dir=self.download_path.text().strip(),
            yandex_auth=self.yandex_auth.currentData(),yandex_folder=self.yandex_folder.text().strip(),deepl_plan=self.deepl_plan.currentData(),
            local_quality=self.local_quality_pick.currentData())
        from .game_ocr import apply_settings
        apply_settings(self.settings['ocr_engine'],self.settings['ocr_device'])
        if bindings!=self.settings['hotkeys']:
            self.stop_hotkeys()
            self.settings['hotkeys'] = bindings
            if not self.hotkey_capture_active:
                self.keys = native.Hotkeys(self.hotkey.emit,self.native_error.emit,bindings,not self.external_mode())
                self.keys.set_escape(self.session_active or (self.running and getattr(self,'screen_snapshot',False)))
                self.start_hotkeys()
        self.apply_appearance()
        self.refresh_key_labels()
        self.refresh_account_label()
        self.message(tr('Настройки сохранены · ')+tr(LABELS[provider])+tr('. Постоянный перевод на паузе.'))
        return True

    def apply_appearance(self,persist=True):
        requested_window=self.window_size_pick.currentData()
        self.settings.update(ui_scale=self.ui_scale_pick.value(),theme=self.theme_pick.currentData(),
            window_size_locked=self.window_lock_pick.isChecked(),card_size_locked=self.card_lock_pick.isChecked(),
            card_theme=self.card_theme_pick.currentData(),window_preset=self.window_size_pick.currentData(),
            card_width=self.card_width_pick.value(),card_height=self.card_height_pick.value(),
            card_opacity=self.card_opacity_pick.value()/100,font_size=self.size_pick.value(),
            opacity=self.opacity_pick.value()/100,offset=self.offset_pick.value(),
            card_background=self.card_background_pick.value()/100,overlay_background=self.overlay_background_pick.value()/100,
            overlay_theme=self.overlay_theme_pick.currentData())
        css = self.style_base.replace('__CHECK_ICON__',(base_dir()/'assets/icons/check.png').as_posix())
        css = css.replace('__CHEVRON_ICON__',(base_dir()/'assets/icons/chevron.png').as_posix())
        from .themes import palette,stylesheet
        colors=palette(self.settings['theme']);css=stylesheet(css,self.settings['theme'])
        scale = 1.2*self.settings['ui_scale']/100
        css = re.sub(r'font-size:(\d+)px',lambda m:f'font-size:{round(int(m[1])*scale)}px',css)
        css+='\nQPushButton#primary,QPushButton#primary QLabel { color:#ffffff; }'
        QApplication.instance().setStyleSheet(css)
        from .ui_icons import device_icon
        light=colors['light']
        self.tabs.refresh_icons(light,colors['accent'])
        for widget in self.findChildren(QWidget):
            kind=widget.property('iconKind')
            if kind:
                icon=device_icon(kind,light,colors['accent'])
                if isinstance(widget,QLabel):widget.setPixmap(icon.pixmap(36,36) if widget.objectName()=='iconTile' else icon.pixmap(widget.width(),widget.height()))
                else:widget.setIcon(icon)
        metrics=self.tabs.list.fontMetrics()
        self.tabs.list.setFixedWidth(max(175,max(metrics.horizontalAdvance(self.tabs.list.item(i).text()) for i in range(self.tabs.count()))+90))
        for form in self.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows if scale>1.25 or form.property('alwaysWrap') else QFormLayout.RowWrapPolicy.WrapLongRows)
            for row in range(form.rowCount()):
                item=form.itemAt(row,QFormLayout.ItemRole.LabelRole)
                if item and isinstance(item.widget(),QLabel):item.widget().setWordWrap(True)
        for combo in self.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        # OCR choices wrap at the available width, including after a font or
        # interface-scale change. A fixed minimum based on the longest item
        # would push fields outside small windows instead of making them legible.
        for combo in (self.ocr_engine_pick,self.ocr_device_pick,self.filter_pick):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            combo.setMinimumWidth(0)
            combo.setMaximumWidth(16777215)
            combo.fit_text()
        for combo in (self.theme_pick,self.card_theme_pick,self.overlay_theme_pick,self.window_size_pick,self.card_size_pick):
            # Long theme names determine the popup width, not a minimum that
            # forces the entire appearance page off a small monitor.
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumWidth(0)
        self.card.set_size_locked(False)
        self.card.resize(self.settings['card_width'],self.settings['card_height'])
        self.card.setWindowOpacity(1.0)
        self.card.apply_background(self.settings['card_background'],self.settings['card_theme'] or self.settings['theme'])
        if persist and requested_window in WINDOW_SIZES:
            self.apply_window_size(requested_window)
            with QSignalBlocker(self.window_size_pick):self.window_size_pick.setCurrentIndex(self.window_size_pick.findData(requested_window))
            self.settings.update(window_preset=requested_window,window_geometry=bytes(self.saveGeometry().toHex()).decode())
        self.apply_size_locks()
        self.refresh_key_labels()
        if self.overlay.isVisible() and self.running:self.draw_screen()
        if persist:
            self.store.save_settings(self.settings)
            self.message(tr('Оформление применено. Размер текста, карточки и прозрачность сохранены.'))

    def refresh_account_label(self):
        try:
            records = self.store.vault.read()
            profile = records.get('chatgpt',{})
            from .auth import PLAN_SCOPE
            ready = PLAN_SCOPE in profile.get('scopes',[]) and bool(profile.get('access_token'))
            self.account_label.setText((profile.get('email') or tr('Аккаунт ChatGPT'))+' · '+(tr('подключён') if ready else tr('не подключён')))
            for provider,label in self.cloud_status.items():
                key = 'api_key' if provider=='api' else provider+'_key'
                label.setText(tr('Ключ сохранён и скрыт') if records.get(key) else tr('Ключ ещё не добавлен'))
            self.connection_banner.setText(tr(LABELS[self.settings['provider']]))
        except Exception:self.account_label.setText(tr('Не удалось прочитать защищённое хранилище.'))

    def save_cloud_key(self,provider):
        key = self.cloud_keys[provider].text().strip()
        if not key:
            self.message(tr('Введи ключ ')+tr(LABELS[provider])+'.')
            return
        self.stop()
        self.card_epoch.next()
        self.store.vault.set(provider+'_key',key)
        self.cloud_keys[provider].clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message(tr('Ключ защищён Windows. Примени настройки подключения.'))

    def delete_cloud_key(self,provider):
        self.stop()
        self.card_epoch.next()
        self.store.vault.set(provider+'_key',None)
        self.cloud_keys[provider].clear()
        self.translator.cache.clear()
        self.refresh_account_label()
        self.message(tr('Ключ ')+tr(LABELS[provider])+tr(' удалён.'))

    def choose_download_folder(self):
        path = QFileDialog.getExistingDirectory(self,tr('Куда скачать модель en-ru'),self.download_path.text())
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
        self.message(tr('Загружаю модель в ')+destination+tr(' и проверяю целостность…'))
        def done(path):
            self.download_button.setEnabled(True)
            self.local_path.setText(path)
            self.message(tr('Готово: ')+path+tr('. Нажми «Использовать» для офлайн-режима.'))
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
        self.message(tr('Выбор словарей сохранён.'))

    def describe_dictionary(self,current,previous=None):
        if not current:return
        descriptions={
            'wiktionary':tr('Викисловарь · офлайн\nРусские значения английских слов, транскрипция, примеры и формы слов. Подробность зависит от статьи. Источник: ru.wiktionary.org, обработка Kaikki/Wiktextract. CC BY-SA 4.0.'),
            'freedict':tr('FreeDict / WikDict · офлайн\nКороткие переводы английских слов на русский.'),
            'wordnet':tr('WordNet 3.1 · офлайн\nОпределения, синонимы и примеры на английском.'),
            'personal':tr('Мои слова · офлайн\nСохранённые тобой переводы и объяснения.'),
        }
        ident=current.data(Qt.ItemDataRole.UserRole)
        self.dictionary_preview.setPlainText(descriptions.get(ident,tr('Пользовательский словарь · офлайн\nИмпортированные значения.')))

    def open_wiktionary(self):
        from urllib.parse import quote
        term=self.card.term.text().strip()
        if term:self.open_link('https://ru.wiktionary.org/wiki/'+quote(term,safe=''))

    def import_dictionary(self):
        path,_ = QFileDialog.getOpenFileName(self,tr('Добавить свой словарь'),'',tr('Словари (*.json *.csv *.tsv)'))
        if not path:return
        name,accepted = QInputDialog.getText(self,tr('Название словаря'),tr('Как подписать источник в карточке?'),text=Path(path).stem)
        if not accepted:return
        try:
            source = self.dictionary.import_file(path,name)
            self.refresh_dictionaries()
            self.message(trf('Добавлен {0}: {1} записей.',source['name'],source['entries']))
        except Exception as error:
            from .auth import ServiceError
            self.message(str(error) if isinstance(error,ServiceError) else tr('Не удалось импортировать словарь.'))

    @game_action
    def preview_ocr(self):
        if getattr(self,'ocr_preview_busy',False):return
        if self.settings.get('recording_visible',False) and not self.prepare_recording_capture():return
        self.ocr_preview_busy=True;self.ocr_preview_button.setEnabled(False)
        self.ocr_preview.clear();self.help.dismiss()
        self.stop();self.refresh_key_labels();self.begin_session()
        revision=self.capture_epoch.next()
        monitor=self.monitor;region=self.region or Box(monitor['x'],monitor['y'],monitor['w'],monitor['h'])
        profile=self.filter_pick.currentData();engine=self.ocr_engine_pick.currentData();device=self.ocr_device_pick.currentData();self.showMinimized()
        def finish():
            self.ocr_preview_busy=False
            if not self.closing:self.ocr_preview_button.setEnabled(True)
        def failed(error):
            finish()
            if not self.closing and self.capture_epoch.accepts(revision):self.capture_failure(error,revision)
        def capture():
            if self.closing or not self.capture_epoch.accepts(revision):finish();return
            def inspect():
                from .ocr_preview import inspect_frame
                return inspect_frame(self.capture_preview_image(region),profile,engine,device)
            def done(result):
                finish()
                if self.closing or not self.capture_epoch.accepts(revision):return
                self.close_session(restore=False);self.showNormal()
                self.ocr_preview.display(result)
            self.task(inspect,done,failed)
        QTimer.singleShot(220,capture)

    def on_hotkey(self,action):
        help_menu=getattr(getattr(self,'help_button',None),'help_menu',None)
        if help_menu is not None and help_menu.isVisible():
            if action=='escape':help_menu.hide();self.help_button.setFocus()
            return
        guide=getattr(self,'onboarding_dialog',None)
        previews=getattr(self,'appearance_previews',None)
        demo=guide or (previews.dialogs[-1] if previews and previews.dialogs else None)
        if demo is not None:
            if action=='escape':demo.reject()
            return
        if self.hotkey_capture_active or not self.allow_game_action():return
        if action=='escape':
            if self.session_active:self.close_session()
            elif self.running and getattr(self,'screen_snapshot',False):self.stop();self.message(tr('Экранный перевод закрыт.'))
        elif action in ('study','region'):self.capture_freeze(action)
        elif action=='toggle':self.toggle()
        elif action=='screen':self.translate_screen_once()

    def closeEvent(self,event):
        self.closing = True
        if getattr(self,'onboarding_dialog',None) is not None:self.onboarding_dialog.reject()
        if hasattr(self,'appearance_previews'):
            for dialog in list(self.appearance_previews.dialogs):dialog.reject()
        self.safety_timer.stop()
        if hasattr(self,'model_timer'):self.model_timer.stop()
        for field in self.binding_fields():field.finish()
        self.close_features()
        self.close_session(restore=False)
        self.stop()
        self.auth.cancel.set()
        self.stop_hotkeys()
        self.settings['window_geometry'] = bytes(self.saveGeometry().toHex()).decode()
        self.store.save_settings(self.settings)
        self.tray.hide()
        QApplication.instance().removeEventFilter(self.session_filter)
        self.overlay.close()
        self.result_window.close()
        self.card.close()
        QMainWindow.closeEvent(self,event)
        QApplication.instance().quit()
