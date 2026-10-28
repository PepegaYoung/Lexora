"""Navigation and contextual help. Explanations stay out of the working view."""
from .i18n import tr,trf,original
from PySide6.QtCore import Qt,QObject,QEvent,Signal,QTimer,QSize
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QListWidgetItem,QStackedWidget,QLabel,QPushButton,QComboBox,QSizePolicy,QStyledItemDelegate,QStyle,QMenu
from PySide6.QtGui import QPixmap
from .storage import base_dir
from .ui_icons import device_icon
from .reading_widgets import divider
from .in_app_dialog import InAppHelpMenu,HelpButton

NAME='Lexora'
VERSION='0.6.54'
WINDOW_SIZES={'720p':(1280,720),'1080p':(1920,1080),'1440p':(2560,1440)}

PAGE_HELP={
    'Игровой экран':'Alt+Q — экранный словарь: нажми на слово или выдели фразу на снимке. «Перевести текущий кадр» переводит весь монитор один раз. Для автоперевода выбери область или весь экран.',
    'Настройки':'Монитор, необязательное название игры и профили. «Привязать игру» предлагает запущенные EXE. Для перевода создавать профиль не требуется.',
    'Перевод':'Выбери переводчик, настрой подключение и нажми «Использовать». Подсказка к каждому полю появляется при выборе.',
    'Распознавание':'Выбери профиль OCR, проверь кадр в предпросмотре и сохрани распознавание. Настройки клавиатуры, мыши и геймпада находятся в разделе «Привязки».',
    'Привязки':'Клавиатура, мышь и геймпад показаны вместе. Нажми поле и прожми привязку. Кнопки геймпада зажми и отпусти. Правый клик — добавить вариант или очистить.',
    'Оформление':'Базовые размеры задаются в процентах. «Дополнительно» открывает точные размеры в пикселях и отступ. Колесо над числом меняет значение; «Применить» сохраняет выбор.',
    'Словари':'Отметь нужные словари и сохрани выбор. Встроенные словари работают без сети; выбранный источник описан ниже.',
    'Мои слова':'Здесь сохранённые слова. Выбери запись для просмотра, изменения или удаления.',
    'История':'Введи или исправь английский текст и нажми «Перевести». История доступна до закрытия программы.',
    'Повторение':'Вспомни перевод, затем покажи ответ и выбери «Знаю» или «Повторить». Следующая тренировка учитывает твои ответы.',
    'Диагностика':'Время OCR и перевода помогает найти задержку. Здесь можно сохранить технический отчёт или резервную копию слов и настроек.',
    'Защита игр':'Добавь игру и выбери действие при её запуске: закрыть Lexora или отключить перевод и привязки. После выхода из игры отключённые функции возвращаются кнопкой «Возобновить работу».',
}
PROVIDER_HELP={
    'subscription':'Войди в ChatGPT, получи список моделей и нажми «Использовать». Перевод расходует общие лимиты подписки.',
    'api':'Сохрани ключ OpenAI API, выбери модель и нажми «Использовать». API оплачивается отдельно от подписки ChatGPT.',
    'local':'Выбери папку загрузки, скачай модель и нажми «Использовать». Перевод работает на CPU, без интернета.',
    'yandex_web':'Ключ не нужен: нажми «Использовать». Текст отправляется Яндексу. Подключение неофициальное, возможны ограничения.',
    'mymemory':'Ключ не нужен: нажми «Использовать». Текст отправляется MyMemory; действует суточная квота.',
    'yandex':'Сохрани API-ключ или IAM-токен Яндекс Cloud. Для IAM укажи каталог; нужна роль ai.translate.user.',
    'deepl':'Сохрани ключ DeepL API и выбери тариф. Обычная подписка на сайт DeepL не даёт доступ к API.',
}

STYLE='''
QFrame#surface { background:transparent; border:0; }
QWidget#gamePage QWidget { background:transparent; }
QWidget#gamePage QFrame#divider { background:#33475e; }
QWidget#gamePage QPushButton#providerLink { background:transparent; border:0; }
QWidget#gamePage QLabel#sectionTitle { font-size:26px; font-weight:700; }
QWidget#gamePage QLabel#panelTitle { font-size:20px; font-weight:600; }
QWidget#gamePage QLabel#actionTitle { font-weight:600; }
QWidget#gamePage QLabel#iconTile { background:#203b3d; border:1px solid #26364b; border-radius:10px; padding:8px; }
QWidget#gamePage QPushButton { background:#14212e; }
QWidget#gamePage QPushButton#segment { padding:8px 12px; border-radius:8px; }
QWidget#gamePage QPushButton#segment:checked { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #203b3d,stop:1 #14212e); border:1px solid #399c8f; }
QWidget#gamePage QPushButton#shortcutAction QLabel { color:#e4ebf5; font-size:14px; }
QWidget#gamePage QCheckBox::indicator { width:22px; height:22px; }

QWidget { background:#101821; color:#e4ebf5; font-family:"Segoe UI"; font-size:13px; }
QMainWindow { background:#0c1420; }
QLabel#title { font-size:30px; font-weight:500; color:#f6fbff; }
QPushButton#providerLink { background:transparent; border:0; padding:7px 0; color:#7de0cc; text-align:left; }
QPushButton#providerLink:hover { color:#76d7ff; }
QPushButton#segment:checked { background:#203b3d; border-color:#399c8f; color:#7de0cc; }
QLabel#subtitle { color:#9cabc0; }
QLabel#sectionTitle { font-size:22px; font-weight:500; }
QLabel#actionTitle { font-size:16px; font-weight:500; }
QFrame#divider { background:#33475e; border:0; }
QWidget#bindingRow { border:0; border-bottom:1px solid #33475e; }
QFrame#devicePanel { background:transparent; border:0; }
QFrame#devicePanel QWidget { background:transparent; }
QFrame#devicePanel QLineEdit,QFrame#devicePanel QComboBox { background:#0b1320; }
QFrame#devicePanel QLineEdit { padding:5px 7px; }
QLineEdit#bindingKeycap { background:transparent; border:1px solid transparent; padding:0; }
QLineEdit#bindingKeycap:hover { background:#14212e; border-color:#33475e; }
QLineEdit#bindingKeycap:focus,QLineEdit#bindingKeycap[recording="true"] { background:#14212e; border:1px solid #7de0cc; }
QTableWidget#wordList { border:1px solid #26364b; border-radius:8px; background:#14212e; }
QTableWidget#wordList::item { border:0; border-bottom:1px solid #33475e; padding:6px 8px; }
QTableWidget#wordList::item:selected { background:#203b3d; color:#e4ebf5; }
QTableWidget#wordList QHeaderView::section { background:#14212e; color:#9cabc0; padding:8px; }
QPushButton#shortcutAction { background:#14212e; }
QPushButton#shortcutAction:checked { background:#203b3d; border-color:#399c8f; }
QPushButton#shortcutAction QLabel { color:#7de0cc; }
QPushButton#shortcutAction QLabel:disabled { color:#647487; }
QPushButton QLabel { background:transparent; border:0; padding:0; }
QLabel#buttonShortcut { color:#a8b8cd; font-size:12px; }
QPushButton#primary QLabel { color:#f6fbff; }
QPushButton#quiet { background:transparent; border:0; color:#a8b8cd; padding:7px 0; }
QToolButton { background:transparent; color:#a8b8cd; border:0; padding:7px 0; }
QLabel#badge { color:#7de0cc; background:#1d373b; border-radius:8px; padding:5px 10px; }
QPushButton { background:#14212e; border:1px solid #33475e; border-radius:7px; padding:6px 10px; }
QPushButton:hover { background:#2e4b69; border-color:#76d7ff; }
QPushButton:focus { border:1px solid #76d7ff; }
QPushButton:disabled { color:#647487; background:#162234; }
QPushButton#primary { background:#247d74; border-color:#247d74; color:#f6fbff; font-weight:500; }
QPushButton#primary:disabled { background:#162234; border-color:#33475e; color:#647487; }
QPushButton#primary QLabel:disabled { color:#647487; }
QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#14212e; border:1px solid #33475e; border-radius:6px; padding:7px; selection-background-color:#247d74; }
QComboBox::drop-down { border:0; width:26px; }
QComboBox::down-arrow { image:url(__CHEVRON_ICON__); width:12px; height:12px; }
QListWidget#navigation { background:#0c1420; border:0; padding:4px; }
QListWidget#navigation::item { padding:11px 12px; margin:2px 0; border-radius:7px; color:#a8b8cd; }
QListWidget#navigation::item:selected { background:#203b3d; color:#7de0cc; }
QListWidget#navigation::item:hover { background:#162234; }
QListWidget,QTableWidget { background:#0b1320; border:1px solid #33475e; border-radius:8px; }
QListWidget#dictionaryList,QListWidget#protectedGamesList { background:#14212e; border:1px solid #33475e; border-radius:8px; }
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
QTabBar::tab { background:#101821; color:#a8b8cd; border:0; padding:10px 14px; margin-right:4px; }
QTabBar::tab:selected { background:#20334a; color:#76d7ff; border-radius:6px; }
QTabWidget::pane { border:0; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #647487; border-radius:4px; background:#0b1320; }
QCheckBox::indicator:checked { background:#247d74; border:1px solid #247d74; image:url(__CHECK_ICON__); }
QCheckBox::indicator:disabled { background:#162234; border-color:#33475e; }
QRadioButton { spacing:8px; }
QRadioButton::indicator { width:14px; height:14px; border:1px solid #647487; border-radius:8px; background:#0b1320; }
QRadioButton::indicator:checked { background:#399c8f; border-color:#7de0cc; }
QRadioButton::indicator:disabled { background:#162234; border-color:#33475e; }
'''

from .themes import SCROLLBAR_STYLE
STYLE+=SCROLLBAR_STYLE

class NavigationDelegate(QStyledItemDelegate):
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        # Selection remains visible; the native focus rectangle adds no information.
        option.state &= ~QStyle.StateFlag.State_HasFocus

class Navigation(QWidget):
    def __init__(self):
        super().__init__()
        row=QHBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(20)
        self.list=QListWidget()
        self.list.setObjectName('navigation')
        self.list.setItemDelegate(NavigationDelegate(self.list))
        self.list.setIconSize(QSize(18,18))
        self.list.setFixedWidth(175)
        self.stack=QStackedWidget()
        row.addWidget(self.list)
        row.addWidget(self.stack,1)
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)

    def addTab(self,page,title):
        kinds={tr('Игровой экран'):'game',tr('Перевод'):'translate',tr('Распознавание'):'ocr',tr('Привязки'):'gamepad',
               tr('Мои слова'):'words',tr('Повторение'):'review',tr('Защита игр'):'safety',tr('История'):'history',tr('Настройки'):'settings'}
        kind=kinds.get(title,'settings');item=QListWidgetItem(device_icon(kind),title);item.setData(Qt.ItemDataRole.UserRole,kind);self.list.addItem(item)
        index=self.stack.addWidget(page)
        if index==0:self.list.setCurrentRow(0)
        return index

    def count(self):return self.stack.count()
    def refresh_icons(self,light,accent=None):
        for index in range(self.count()):
            item=self.list.item(index);item.setIcon(device_icon(item.data(Qt.ItemDataRole.UserRole),light,accent))
    def takeTab(self,title):
        index=next(i for i in range(self.count()) if self.list.item(i).text()==title)
        page=self.stack.widget(index)
        self.stack.removeWidget(page);self.list.takeItem(index)
        return page
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
        else:key=('page',self.window.tabs.currentIndex(),self.section_title())
        if key in self.dismissed_keys and not force:return
        if force:self.dismissed_keys.discard(key)
        self.current_key=key
        self.panel.text.setText(tr(text))
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
        title=self.section_title()
        text=PAGE_HELP.get(original(title),tr('Выбери настройку, чтобы увидеть пояснение.'))
        if title==tr('Перевод'):text=PROVIDER_HELP.get(self.window.provider.currentData(),text)
        self.show(text,source=source,force=source is None)

    def section_title(self):
        title=self.window.tabs.list.currentItem().text()
        sections=getattr(self.window,'settings_tabs',None)
        if title==tr('Настройки') and sections is not None:
            selected=sections.tabText(sections.currentIndex())
            if selected!=tr('Общие'):return selected
        return title

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
        close.setAccessibleName(tr('Скрыть пояснение'))
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
    logo=QLabel();logo.setObjectName('brandLogo')
    pixmap=QPixmap(str(base_dir()/'assets/logo.png'))
    if not pixmap.isNull():
        # The distributed artwork has generous transparent margins.
        pixmap=pixmap.copy(300,260,790,640).scaled(44,44,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    logo.setPixmap(pixmap);logo.setFixedSize(44,44)
    row.addWidget(logo)
    label=QLabel(NAME)
    label.setObjectName('title')
    row.addWidget(label)
    row.addStretch()
    help_button=HelpButton('?')
    help_button.setFixedSize(36,36)
    help_button.setStyleSheet('QPushButton { padding:0; border-radius:18px; }')
    help_button.setToolTip(tr('Помощь и обучение'))
    help_button.setAccessibleName(tr('Помощь и обучение'))
    help_menu=InAppHelpMenu(window,help_button)
    help_menu.addAction(tr('Пояснения к этому разделу'),lambda:window.help.page())
    help_menu.addAction(tr('Знакомство с Lexora'),window.show_onboarding)
    help_button.help_menu=help_menu;help_button.clicked.connect(help_menu.toggle);window.help_button=help_button
    row.addWidget(help_button)
    layout.addLayout(row)
    layout.addWidget(divider())
