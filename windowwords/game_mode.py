from .i18n import tr,trf
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QPushButton,QLabel,QApplication
from .core import Box
from . import native
from .design import NAME

class ResultWindow(QWidget):
    dismissed=Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle(NAME+tr(' · перевод'))
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(620,360)
        layout=QVBoxLayout(self)
        self.content=QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setPlaceholderText(tr('Перевод появится здесь'))
        layout.addWidget(self.content)
        close=QPushButton(tr('Остановить перевод'))
        close.clicked.connect(self.dismissed.emit)
        layout.addWidget(close)
        self.last=''

    def display(self,entries,size,monitor=None):
        text='\n\n'.join(line.text+'\n'+target for line,target in entries)
        if text!=self.last:
            self.content.setPlainText(text)
            self.last=text
        self.content.setStyleSheet(f'QPlainTextEdit {{ font-size:{size}px; }}')
        if not self.isVisible():
            self.winId()
            if monitor:
                screen=next((s for s in QApplication.screens() if s.name()==monitor['name']),None)
                if screen:self.windowHandle().setScreen(screen)
            self.showFullScreen()
            if monitor:native.place(self,Box(monitor['x'],monitor['y'],monitor['w'],monitor['h']),topmost=False)
            if not native.exclude_capture(self):
                self.hide()
                return False
        return True

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.dismissed.emit();event.accept()
        else:super().keyPressEvent(event)

    def closeEvent(self,event):
        self.dismissed.emit()
        super().closeEvent(event)

class GameMode:
    def external_mode(self):return self.settings.get('game_mode','external')=='external'

    def configure_game_windows(self):
        self.card.hide()
        flags=Qt.WindowType.FramelessWindowHint
        if self.external_mode():flags|=Qt.WindowType.Window
        else:flags|=Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint
        self.card.setWindowFlags(flags)
        self.screen_render.setEnabled(not self.external_mode())
        self.screen_render.hide()
        self.render_label.show()
        self.render_settings_group.show()
        self.refresh_key_labels()

    def change_game_mode(self):
        mode=self.game_mode_pick.currentData()
        if mode==self.settings.get('game_mode'):return
        self.close_session(restore=False)
        self.stop()
        self.settings['game_mode']=mode
        self.stop_hotkeys()
        if not self.hotkey_capture_active:
            self.keys=native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
            self.start_hotkeys()
        self.configure_game_windows()
        if hasattr(self,'help'):self.help.bind(self.game_mode_pick,self.game_mode_description())
        self.store.save_settings(self.settings)
        self.message(tr('Выбран режим: ')+self.game_mode_pick.currentText())

    def game_mode_description(self):
        if self.external_mode():
            return tr('Полноэкранное окно вне игры. Escape действует в активном окне; остановка перевода — Alt+T. Допуск античита проверяй по правилам игры.')
        return tr('Перевод поверх игры. Автоперевод включается и выключается назначенной привязкой; Escape остаётся игре.')

    def init_design(self):
        from PySide6.QtWidgets import QComboBox,QLineEdit,QAbstractButton,QPushButton,QSizePolicy,QHBoxLayout
        from .reading_widgets import ActionButton
        from .reading_widgets import CompactFieldSizer
        for control,width in ((self.language_pick,180),(self.monitor_pick,260),(self.game,240),
                              (self.gamepad_device_pick,220),
                              (self.theme_pick,280),(self.card_theme_pick,280),(self.overlay_theme_pick,280),
                              (self.window_size_pick,260),(self.card_size_pick,260),(self.safety_action_pick,280)):
            control.compact_sizer=CompactFieldSizer(control,width)
        for control in self.tabs.findChildren(QPushButton):
            if not isinstance(control,ActionButton):control.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
        for row in self.tabs.findChildren(QHBoxLayout):
            # Compact action bars align to the left; input fields keep their space.
            items=[row.itemAt(i) for i in range(row.count())]
            if items and all(isinstance(item.widget(),QPushButton) for item in items):row.addStretch()
        descriptions={
            self.monitor_pick:tr('Монитор с игрой. Координаты области относятся к этому монитору.'),
            self.game:tr('Название для профиля и сохранённых слов.'),
            self.provider:tr('Выбери сервис, настрой подключение и нажми «Использовать». Онлайн-сервису отправляется распознанный текст.'),
            self.filter_pick:tr('Подготовка кадра для Windows OCR. «Универсальный» подходит для белого и жёлтого текста.'),
            self.game_mode_pick:self.game_mode_description(),
            self.screen_scope:tr('Захват для автоперевода: область или весь выбранный монитор. «Перевести текущий кадр» всегда переводит весь выбранный монитор.'),
            self.screen_render:tr('«Над оригиналом» сохраняет английский текст. «Вместо оригинала» закрывает его подложкой.'),
            self.dictionary_list:tr('Отметь словари для карточки. Все встроенные словари работают без сети.'),
            self.model_pick:tr('Модели доступны выбранному аккаунту. API и подписка ChatGPT имеют разные лимиты.'),
        }
        for widget in self.tabs.findChildren(QWidget):
            # Reset buttons use a small native hover tooltip, not the large
            # section-help panel bound to other settings controls.
            from .binding_widgets import ResetBindingButton
            if isinstance(widget,ResetBindingButton):continue
            value=descriptions.get(widget) or widget.property('helpText') or widget.toolTip()
            if value:self.help.bind(widget,value)
        self.tabs.list.currentRowChanged.connect(lambda _:self.help_panel.hide())
        self.provider.currentIndexChanged.connect(lambda _:self.help.page(source=self.provider))
        from .ocr import PROFILES
        self.filter_pick.currentIndexChanged.connect(lambda _:self.help.show(next(p[2] for p in PROFILES if p[0]==self.filter_pick.currentData()),source=self.filter_pick))
