from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QPushButton,QLabel,QApplication
from .core import Box
from . import native
from .design import NAME

class ResultWindow(QWidget):
    dismissed=Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle(NAME+' · перевод')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(620,360)
        layout=QVBoxLayout(self)
        self.content=QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setPlaceholderText('Перевод появится здесь')
        layout.addWidget(self.content)
        close=QPushButton('Остановить перевод')
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
        self.screen_render.setVisible(not self.external_mode())
        self.render_label.setVisible(not self.external_mode())
        self.hover_button.setEnabled(True)
        self.refresh_key_labels()

    def change_game_mode(self):
        mode=self.game_mode_pick.currentData()
        if mode==self.settings.get('game_mode'):return
        self.close_session(restore=False)
        self.stop()
        self.hover=False
        self.settings['game_mode']=mode
        self.keys.stop()
        self.keys.join(timeout=2)
        if not self.hotkey_capture_active:
            self.keys=native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
            self.start_hotkeys()
        self.configure_game_windows()
        if hasattr(self,'help'):self.help.bind(self.game_mode_pick,self.game_mode_description())
        self.store.save_settings(self.settings)
        self.message('Выбран режим: '+self.game_mode_pick.currentText())
        if hasattr(self,'help'):self.help.show(self.game_mode_description(),source=self.game_mode_pick)

    def game_mode_description(self):
        if self.external_mode():
            return 'Полноэкранное окно вне игры. Escape действует в активном окне; остановка перевода — Alt+T. Допуск античита проверяй по правилам игры.'
        return 'Перевод поверх игры; Escape закрывает его. Используй только там, где разрешены внешние оверлеи.'

    def init_design(self):
        from PySide6.QtWidgets import QComboBox,QLineEdit,QAbstractButton
        descriptions={
            self.monitor_pick:'Монитор с игрой. Координаты области относятся к этому монитору.',
            self.game:'Название для профиля и сохранённых слов.',
            self.provider:'Выбери сервис, настрой подключение и нажми «Использовать». Онлайн-сервису отправляется распознанный текст.',
            self.filter_pick:'Подготовка кадра для Windows OCR. «Универсальный» подходит для белого и жёлтого текста.',
            self.game_mode_pick:self.game_mode_description(),
            self.screen_scope:'Область переводит выбранный участок. Весь экран — все найденные строки на выбранном мониторе.',
            self.screen_render:'«Над оригиналом» сохраняет английский текст. «Вместо оригинала» закрывает его подложкой.',
            self.dictionary_list:'Отметь словари для карточки. Все встроенные словари работают без сети.',
            self.model_pick:'Модели доступны выбранному аккаунту. API и подписка ChatGPT имеют разные лимиты.',
        }
        for widget in self.tabs.findChildren(QWidget):
            value=descriptions.get(widget) or widget.property('helpText') or widget.toolTip()
            if value:self.help.bind(widget,value)
        self.tabs.list.currentRowChanged.connect(lambda _:self.help_panel.hide())
        self.provider.currentIndexChanged.connect(lambda _:self.help.page(source=self.provider))
        from .ocr import PROFILES
        self.filter_pick.currentIndexChanged.connect(lambda _:self.help.show(next(p[2] for p in PROFILES if p[0]==self.filter_pick.currentData()),source=self.filter_pick))
        self.screen_scope.currentIndexChanged.connect(lambda _:self.help.show(descriptions[self.screen_scope],source=self.screen_scope))
        self.screen_render.currentIndexChanged.connect(lambda _:self.help.show(descriptions[self.screen_render],source=self.screen_render))
