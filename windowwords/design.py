"""Navigation and contextual help. Explanations stay out of the working view."""
from PySide6.QtCore import Qt,QObject,QEvent,Signal,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QStackedWidget,QLabel,QPushButton,QComboBox,QSizePolicy
from PySide6.QtGui import QPixmap
from .storage import base_dir

NAME='Lexora'
VERSION='0.6.2'

PAGE_HELP={
    'Игровой экран':'Alt+Q — разбор слов на снимке. Для перевода выбери область или весь экран, затем «Перевести кадр» или «Автоперевод».',
    'Перевод':'Выбери переводчик, настрой подключение и нажми «Использовать». Подсказка к каждому полю появляется при выборе.',
    'Распознавание':'Начни с универсального OCR. Проверь кадр в предпросмотре. Для привязки нажми поле и прожми клавишу или сочетание. «+» добавляет вариант, «−» удаляет.',
    'Оформление':'Настрой размер текста, карточки и прозрачность, затем нажми «Применить оформление». Колесо над числом меняет значение.',
    'Словари':'Отметь нужные словари и сохрани выбор. Встроенные словари работают без сети; выбранный источник описан ниже.',
    'Мои слова':'Здесь сохранённые слова. Выбери запись для просмотра, изменения или удаления.',
    'История':'Введи или исправь английский текст и нажми «Перевести». История доступна до закрытия программы.',
    'Повторение':'Вспомни перевод, затем покажи ответ и выбери «Знаю» или «Повторить». Следующая тренировка учитывает твои ответы.',
    'Диагностика':'Время OCR и перевода помогает найти задержку. Здесь можно сохранить технический отчёт или резервную копию слов и настроек.',
}
PROVIDER_HELP={
    'subscription':'Войди в ChatGPT, получи список моделей и нажми «Использовать». Перевод расходует общие лимиты подписки.',
    'api':'Сохрани ключ OpenAI API, выбери модель и нажми «Использовать». API оплачивается отдельно от подписки ChatGPT.',
    'local':'Выбери папку загрузки, скачай модель и нажми «Использовать». Перевод работает на CPU, без интернета.',
    'google_web':'Ключ не нужен: нажми «Использовать». Текст отправляется Google. Подключение неофициальное, возможны ограничения.',
    'yandex_web':'Ключ не нужен: нажми «Использовать». Текст отправляется Яндексу. Подключение неофициальное, возможны ограничения.',
    'mymemory':'Ключ не нужен: нажми «Использовать». Текст отправляется MyMemory; действует суточная квота.',
    'libre':'Укажи адрес своего или публичного сервера LibreTranslate. Ключ и лимиты зависят от сервера.',
    'google':'Сохрани ключ проекта Google Cloud с включённым Cloud Translation API. Квоты и оплата относятся к проекту.',
    'yandex':'Сохрани API-ключ или IAM-токен Яндекс Cloud. Для IAM укажи каталог; нужна роль ai.translate.user.',
    'deepl':'Сохрани ключ DeepL API и выбери тариф. Обычная подписка на сайт DeepL не даёт доступ к API.',
}

STYLE='''
QWidget { background:#101821; color:#e4ebf5; font-family:"Segoe UI"; font-size:13px; }
QMainWindow { background:#0c1420; }
QLabel#title { font-size:27px; font-weight:700; color:#f6fbff; }
QLabel#subtitle { color:#9cabc0; }
QLabel#badge { color:#7de0cc; background:#1d373b; border-radius:8px; padding:5px 10px; }
QPushButton { background:#20334a; border:1px solid #34506c; border-radius:8px; padding:9px 12px; }
QPushButton:hover { background:#2e4b69; border-color:#76d7ff; }
QPushButton:focus { border:1px solid #76d7ff; }
QPushButton:disabled { color:#647487; background:#162234; }
QPushButton#primary { background:#247d74; border-color:#399c8f; color:#f6fbff; font-weight:600; }
QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#0b1320; border:1px solid #33475e; border-radius:6px; padding:7px; selection-background-color:#247d74; }
QComboBox::drop-down { border:0; width:26px; }
QListWidget#navigation { background:#0c1420; border:0; padding:4px; }
QListWidget#navigation::item { padding:12px 14px; margin:3px 0; border-radius:8px; color:#a8b8cd; }
QListWidget#navigation::item:selected { background:#20334a; color:#76d7ff; }
QListWidget#navigation::item:hover { background:#162234; }
QListWidget,QTableWidget { background:#0b1320; border:1px solid #33475e; border-radius:8px; }
QGroupBox { border:1px solid #26364b; border-radius:10px; margin-top:15px; padding:12px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#a8b8cd; }
QHeaderView::section { background:#20334a; border:0; padding:8px; }
QTableWidget { gridline-color:#26364b; }
QScrollArea { border:0; background:transparent; }
QSlider::groove:horizontal { height:5px; background:#33475e; border-radius:2px; }
QSlider::sub-page:horizontal { background:#399c8f; border-radius:2px; }
QSlider::handle:horizontal { width:16px; height:16px; margin:-6px 0; background:#7de0cc; border-radius:8px; }
QToolTip { background:#20334a; color:#e4ebf5; border:1px solid #34506c; padding:8px; }
QLineEdit[recording="true"] { border:2px solid #399c8f; }
'''

class Navigation(QWidget):
    def __init__(self):
        super().__init__()
        row=QHBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(20)
        self.list=QListWidget()
        self.list.setObjectName('navigation')
        self.list.setFixedWidth(175)
        self.stack=QStackedWidget()
        row.addWidget(self.list)
        row.addWidget(self.stack,1)
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)

    def addTab(self,page,title):
        self.list.addItem(title)
        index=self.stack.addWidget(page)
        if index==0:self.list.setCurrentRow(0)
        return index

    def count(self):return self.stack.count()
    def widget(self,index):return self.stack.widget(index)
    def currentWidget(self):return self.stack.currentWidget()
    def setCurrentIndex(self,index):self.list.setCurrentRow(index)
    def currentIndex(self):return self.list.currentRow()

class ContextHelp(QObject):
    def __init__(self,window,panel):
        super().__init__(window)
        self.window,self.panel=window,panel
        self.dismissed_keys=set()
        self.current_key=None
        self.panel.dismissed.connect(self.dismiss)

    def bind(self,widget,text):
        widget.setToolTip('')
        widget.setProperty('helpText',text)
        widget.installEventFilter(self)

    def show(self,text,source=None,force=False):
        if isinstance(source,QComboBox):key=('control',id(source),str(source.currentData()))
        elif source is not None:key=('control',id(source))
        else:key=('page',self.window.tabs.currentIndex())
        if key in self.dismissed_keys and not force:return
        if force:self.dismissed_keys.discard(key)
        self.current_key=key
        self.panel.text.setText(text)
        self.panel.fit_text()
        self.panel.setVisible(bool(text))

    def dismiss(self):
        if self.current_key is not None:self.dismissed_keys.add(self.current_key)
        self.panel.hide()

    def eventFilter(self,object,event):
        if event.type() in (QEvent.Type.FocusIn,QEvent.Type.MouseButtonPress):
            value=object.property('helpText')
            if value:self.show(value,source=object)
        return False

    def page(self,source=None):
        title=self.window.tabs.list.currentItem().text()
        text=PAGE_HELP.get(title,'Выбери настройку, чтобы увидеть пояснение.')
        if title=='Перевод':text=PROVIDER_HELP.get(self.window.provider.currentData(),text)
        self.show(text,source=source,force=source is None)

class HelpPanel(QWidget):
    dismissed=Signal()
    def __init__(self):
        super().__init__()
        self.fit_timer=QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_text)
        row=QHBoxLayout(self)
        row.setContentsMargins(10,8,10,8)
        self.text=QLabel()
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        self.text.setObjectName('subtitle')
        self.text.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        close=QPushButton('×')
        self.close_button=close
        close.setAccessibleName('Скрыть пояснение')
        close.setFixedSize(24,24)
        close.setStyleSheet('QPushButton { padding:0; border-radius:5px; }')
        close.clicked.connect(self.dismissed.emit)
        row.addWidget(self.text,1)
        row.addWidget(close,0,Qt.AlignmentFlag.AlignTop)
        self.hide()

    def fit_text(self):
        margins=self.layout().contentsMargins()
        width=max(1,self.width()-margins.left()-margins.right()-self.close_button.width()-self.layout().spacing())
        height=max(self.close_button.height(),self.text.heightForWidth(width))
        self.setFixedHeight(height+margins.top()+margins.bottom())

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_text()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange) and hasattr(self,'fit_timer'):
            self.fit_timer.start(0)

def header(window,layout):
    row=QHBoxLayout()
    logo=QLabel()
    picture=QPixmap(str(base_dir()/'assets/logo.png'))
    logo.setPixmap(picture.scaled(54,54,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    row.addWidget(logo)
    label=QLabel(NAME)
    label.setObjectName('title')
    row.addWidget(label)
    badge=QLabel('EN → RU')
    badge.setObjectName('badge')
    row.addWidget(badge)
    row.addStretch()
    help_button=QPushButton('?')
    help_button.setFixedWidth(38)
    help_button.setToolTip('Пояснения к этому разделу')
    help_button.clicked.connect(lambda:window.help.page())
    row.addWidget(help_button)
    layout.addLayout(row)
