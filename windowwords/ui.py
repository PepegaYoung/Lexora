from .i18n import tr,trf
from PySide6.QtCore import Qt,QSignalBlocker,QSize
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,
    QFormLayout,QSpinBox,QDoubleSpinBox,QScrollArea,QGroupBox,QPlainTextEdit,QListWidget,QTabWidget,
    QListWidgetItem,QSplitter,QCheckBox,QSizePolicy,QTabBar,QMenu,QFrame,QGridLayout,QRadioButton,QButtonGroup)
from . import ocr
from .providers import LABELS
from .controls import AdjustSpinBox,adjustment
from .model_catalog import ModelPicker
from .shortcuts import device_bindings
from .ui_icons import device_icon,theme_swatch
from .reading_widgets import StableModeRow,ActionButton,ActionRow,Foldout,CompactRow,CompactFieldSizer,divider
from .themes import THEMES,CARD_THEMES,OVERLAY_THEMES
from .visual_shell import Surface,ToggleSwitch,ProviderLink,WrappingCheckBox,ReadableCombo
from .binding_widgets import BindingTable,BindingKeyEdit,BindingGamepadEdit
from .widgets import CARD_DEFAULT,CARD_SIZES
from .appearance_preview import PreviewBlocks


def button(title,action,primary=False):
    item = QPushButton(title)
    item.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
    item.clicked.connect(action)
    if primary:item.setObjectName('primary')
    return item


def note(text):
    item = QLabel(text)
    item.setWordWrap(True)
    item.setObjectName('subtitle')
    if text:
        item.setProperty('contextNote',True)
        item.hide()
    return item


def scroll(page):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(page)
    return area


def section(layout,title):
    group = QGroupBox(title)
    body = QVBoxLayout(group)
    layout.addWidget(group)
    return body


class ProviderPages(QWidget):
    """Reserve space for the selected connection instead of the largest page."""
    def __init__(self):
        super().__init__()
        self.pages=[]
        self.selected=0
        self.body=QVBoxLayout(self)
        self.body.setContentsMargins(0,0,0,0)

    def addWidget(self,page):
        self.pages.append(page)
        self.body.addWidget(page)
        page.hide()
        return len(self.pages)-1

    def setCurrentIndex(self,index):
        self.selected=index
        for i,page in enumerate(self.pages):page.setVisible(i==index)

    def currentWidget(self):return self.pages[self.selected]


class UIBuilder:
    def build_preferences(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0)
        self.settings_tabs=QTabBar();self.settings_tabs.setExpanding(False)
        self.settings_tabs.setUsesScrollButtons(True)
        layout.addWidget(self.settings_tabs)
        self.settings_pages=ProviderPages();layout.addWidget(self.settings_pages,1)
        self.settings_pages.addWidget(scroll(self.game_settings_page));self.settings_tabs.addTab(tr('Общие'))
        for title in (tr('Распознавание'),tr('Оформление'),tr('Словари'),tr('Диагностика'),tr('Защита игр')):
            content=self.tabs.takeTab(title)
            self.settings_pages.addWidget(scroll(content) if title==tr('Защита игр') else content);self.settings_tabs.addTab(title)
        self.settings_tabs.currentChanged.connect(self.settings_pages.setCurrentIndex)
        self.settings_pages.setCurrentIndex(0)
        self.tabs.addTab(page,tr('Настройки'))

    def binding_menu(self,field,action,device,position):
        field.finish()
        menu=QMenu(field)
        menu.addAction(tr('Назначить сочетание'),lambda:field.begin())
        menu.addAction(tr('Добавить ещё сочетание'),field.begin_add)
        menu.addSeparator()
        menu.addAction(tr('Удалить одно сочетание'),lambda:self.remove_hotkey(action,device))
        menu.addAction(tr('Очистить привязки'),lambda:self.clear_hotkey(action,device))
        menu.exec(field.mapToGlobal(position))

    def build_reading(self):
        page=QWidget();page.setObjectName('gamePage')
        layout=QVBoxLayout(page);layout.setContentsMargins(4,0,4,4);layout.setSpacing(12)
        title=QLabel(tr('Игровой экран'));title.setObjectName('sectionTitle');title.setWordWrap(True)
        self.connection_banner=ProviderLink();self.connection_banner.clicked.connect(self.open_translation_settings)
        self.connection_banner.setObjectName('providerLink');self.connection_banner.setToolTip(tr('Открыть выбор переводчика'))
        provider=QWidget();provider_row=QHBoxLayout(provider);provider_row.setContentsMargins(0,0,0,0)
        provider_title=QLabel(tr('Переводчик')+':');provider_title.setObjectName('subtitle')
        provider_row.addWidget(provider_title);provider_row.addWidget(self.connection_banner)
        top=CompactRow();top.setObjectName('pageHeading');top.addWidget(title);top.addWidget(provider);layout.addWidget(top)
        self.game_mode_pick=QComboBox(page);self.game_mode_pick.hide()
        for caption,value in [('Отдельное окно','external'),('Поверх игры','overlay')]:self.game_mode_pick.addItem(tr(caption),value)
        self.game_mode_pick.setCurrentIndex(max(0,self.game_mode_pick.findData(self.settings['game_mode'])))
        self.game_mode_pick.currentIndexChanged.connect(self.change_game_mode)
        self.screen_render=QComboBox(page);self.screen_render.hide()
        for caption,value in [('Над оригиналом','above'),('Вместо оригинала','replace')]:self.screen_render.addItem(tr(caption),value)
        self.screen_render.setCurrentIndex(max(0,self.screen_render.findData(self.settings['screen_mode'])))
        self.screen_render.currentIndexChanged.connect(self.screen_options)
        self.capture_buttons={};self.action_rows={}
        self.capture_buttons['study']=ActionButton(tr('Выбрать слово'),lambda:self.capture_freeze('study'),True)
        self.snapshot_button=ActionButton(tr('Перевести'),self.translate_screen_once)
        self.open_image_button=ActionButton(tr('Открыть'),self.open_image)
        self.start_button=ActionButton(tr('Запустить'),self.toggle);self.start_button.setCheckable(True)
        for control in (self.capture_buttons['study'],self.snapshot_button,self.open_image_button,self.start_button):control.set_shortcut_only()
        self.open_image_button.set_shortcut(tr('Открыть'))
        actions=Surface();body=QVBoxLayout(actions);body.setContentsMargins(20,16,20,12);body.setSpacing(0)
        heading=QLabel(tr('Основные действия'));heading.setObjectName('panelTitle');heading.setWordWrap(True);body.addWidget(heading)
        entries=[('study','Экранный словарь','Показать перевод слова под курсором в игре','dictionary',self.capture_buttons['study']),
                 ('screen','Текущий кадр','Распознать и перевести текст на экране игры','frame',self.snapshot_button),
                 ('file','Снимок из файла','Выбрать изображение и перевести текст','image',self.open_image_button)]
        for index,(key,caption,description,icon,control) in enumerate(entries):
            item=ActionRow(tr(caption),tr(description),icon,control);item.icon.setObjectName('iconTile');item.icon.setFixedSize(60,56);item.icon.setAlignment(Qt.AlignmentFlag.AlignCenter);self.action_rows[key]=item
            if index:body.addWidget(divider())
            body.addWidget(item)
        layout.addWidget(actions)
        auto=Surface();auto_body=QVBoxLayout(auto);auto_body.setContentsMargins(20,8,20,16);auto_body.setSpacing(8)
        self.action_rows['toggle']=ActionRow(tr('Автоперевод'),tr('Автоматически распознавать и переводить текст в игре'),'auto',self.start_button)
        toggle_row=self.action_rows['toggle'];toggle_row.icon.hide();toggle_row.title.setObjectName('panelTitle')
        controls=toggle_row.controls.layout();controls.removeWidget(self.start_button)
        buttons=QHBoxLayout();buttons.addWidget(self.start_button);self.auto_switch=ToggleSwitch();buttons.addWidget(self.auto_switch);controls.addLayout(buttons)
        self.auto_switch.clicked.connect(lambda _:self.start_button.click());self.start_button.toggled.connect(self.auto_switch.setChecked)
        auto_body.addWidget(toggle_row)
        self.auto_options=Foldout(tr('Параметры автоперевода'));self.auto_options.set_expanded(True);self.auto_options.toggle.hide()
        self.auto_options.body.setContentsMargins(0,0,0,0);self.auto_options.body.setSpacing(8);modes=self.auto_options.body
        self.screen_scope=QComboBox(self.auto_options.content);self.screen_scope.hide()
        self.screen_scope.addItem(tr('Область'),'region');self.screen_scope.addItem(tr('Весь экран'),'monitor')
        self.screen_scope.setCurrentIndex(max(0,self.screen_scope.findData(self.settings['screen_scope'])))
        self.screen_scope.currentIndexChanged.connect(self.screen_options)
        def mode_row(label,entries,picker):
            row=StableModeRow();caption=QLabel(tr(label));caption.setObjectName('subtitle');row.addWidget(caption)
            group=QButtonGroup(self);choices={}
            for value,text,kind in entries:
                choice=button(tr(text),lambda:None);choice.setObjectName('segment');choice.setCheckable(True)
                choice.setProperty('iconKind',kind);choice.setIcon(device_icon(kind));choice.setIconSize(QSize(22,22))
                group.addButton(choice);choices[value]=choice;choice.setChecked(picker.currentData()==value)
                choice.clicked.connect(lambda checked=False,key=value:picker.setCurrentIndex(picker.findData(key)))
                row.addWidget(choice)
            picker.currentIndexChanged.connect(lambda _:choices[picker.currentData()].setChecked(True));modes.addWidget(row)
            return row,caption,group,choices
        _,_,self.scope_group,self.scope_buttons=mode_row('Область перевода',[('monitor','Весь экран','monitor'),('region','Область','region')],self.screen_scope)
        self.render_settings_group,self.render_label,self.render_group,self.render_buttons=mode_row('Способ отображения',[('above','Над оригиналом','text_above'),('replace','Вместо оригинала','ocr')],self.screen_render)
        self.render_buttons['above'].setToolTip(tr('Перевод рядом с английским текстом. Если сверху нет места, длинный абзац показывается сбоку.'))
        _,_,self.display_group,self.display_buttons=mode_row('Где показывать',[('overlay','Поверх игры','layers'),('external','Отдельное окно','window')],self.game_mode_pick)
        area_row=StableModeRow();area_label=QLabel(tr('Выделение области'));area_label.setObjectName('subtitle');area_row.addWidget(area_label)
        self.capture_buttons['region']=ActionButton(tr('Выбрать область'),lambda:self.capture_freeze('region'))
        self.capture_buttons['region'].setToolTip(tr('Выдели участок с текстом для автоперевода.'))
        self.capture_buttons['region'].body.insertStretch(0);self.capture_buttons['region'].body.addStretch()
        for label in (self.capture_buttons['region'].caption,self.capture_buttons['region'].shortcut):label.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred)
        area_row.addWidget(self.capture_buttons['region']);modes.addWidget(area_row)
        self.region_label=QLabel();self.region_label.setObjectName('subtitle');self.region_label.setWordWrap(True)
        self.region_label.setMinimumWidth(200);modes.addWidget(self.region_label)
        self.screen_scope.currentIndexChanged.connect(self.sync_capture_controls);self.sync_capture_controls()
        auto_body.addWidget(self.auto_options);layout.addWidget(auto)
        self.auto_card_pick=WrappingCheckBox(tr('Карточка при наведении'));self.auto_card_pick.setChecked(self.settings.get('auto_card',True));self.auto_card_pick.toggled.connect(self.set_auto_card)
        self.auto_translate_pick=WrappingCheckBox(tr('Переводить карточку при открытии'));self.auto_translate_pick.setChecked(self.settings.get('auto_translate_card',False));self.auto_translate_pick.toggled.connect(lambda value:self.set_feature('auto_translate_card',value))
        self.card_options=Surface();cards=QVBoxLayout(self.card_options);cards.setContentsMargins(20,14,20,14)
        label=QLabel(tr('Карточка'));label.setObjectName('panelTitle');cards.addWidget(label)
        options=CompactRow();options.setObjectName('cardChecks');options.addWidget(self.auto_card_pick);options.addWidget(self.auto_translate_pick);cards.addWidget(options)
        layout.addWidget(self.card_options);layout.addStretch()
        self.tabs.addTab(scroll(page),tr('Игровой экран'))
        self.game_settings_page=QWidget()
        settings_layout=QVBoxLayout(self.game_settings_page)
        form=QFormLayout();form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.language_pick=QComboBox()
        self.language_pick.addItem('Русский','ru');self.language_pick.addItem('English','en')
        self.language_pick.setCurrentIndex(max(0,self.language_pick.findData(self.settings['ui_language'])))
        self.language_pick.setToolTip(tr('Язык меню и настроек. Применяется после перезапуска Lexora. Язык перевода игровых текстов не меняется.'))
        self.language_pick.currentIndexChanged.connect(self.save_interface_language)
        form.addRow(tr('Язык интерфейса'),self.language_pick)
        self.monitor_pick=QComboBox()
        for index,m in enumerate(self.monitors,1):self.monitor_pick.addItem(f"{index} · {m['w']} × {m['h']}",m['name'])
        self.monitor_pick.setCurrentIndex(self.monitors.index(self.monitor))
        self.monitor_pick.currentIndexChanged.connect(self.change_monitor)
        self.game=QLineEdit(self.settings['game'])
        self.game.setPlaceholderText(tr('Необязательно'))
        self.game.editingFinished.connect(self.save_game_settings)
        form.addRow(tr('Монитор'),self.monitor_pick)
        settings_layout.addLayout(form);settings_layout.addWidget(divider())
        self.recording_pick=QCheckBox(tr('Показывать в записи и скриншотах'))
        self.recording_pick.setChecked(self.settings.get('recording_visible',False))
        self.recording_pick.setToolTip(tr('Для PrintScreen и OBS → Захват экрана. OCR получает окно игры отдельно, без перевода. Перед первым захватом переключись в игру и нажми горячую клавишу. Изменение режима останавливает автоперевод; настройка сохраняется сразу.')+'\n\n'+tr('Если в fullscreen пропадает курсор, выключи видимость в записи: этот режим использует WGC. Обычный перевод работает без него.'))
        self.recording_pick.toggled.connect(self.set_recording_mode)
        settings_layout.addWidget(self.recording_pick)
        self.game_profiles=Foldout(tr('Настройки для разных игр'));settings_layout.addWidget(self.game_profiles)
        self.game_profiles.setToolTip(tr('Необязательные профили сохраняют отдельные настройки для разных игр. Для обычного перевода они не нужны.'))
        setup=self.game_profiles.body
        form=QFormLayout();form.addRow(tr('Название игры'),self.game);setup.addLayout(form)
        self.game.setToolTip(tr('Необязательная подпись сохранённых слов и профиля. Для перевода вводить название не нужно.'))
        row=QHBoxLayout()
        row.addWidget(button(tr('Сохранить профиль'),self.save_profile))
        row.addWidget(button(tr('Загрузить профиль'),self.load_profile))
        setup.addLayout(row)
        self.auto_profiles_pick=QCheckBox(tr('Выбирать профиль автоматически'))
        self.auto_profiles_pick.setChecked(self.settings.get('auto_profiles',False))
        self.auto_profiles_pick.setToolTip(tr('Профиль сохраняет монитор, область, распознавание и оформление. Привяжи его к EXE игры для автоматического выбора.'))
        self.auto_profiles_pick.toggled.connect(lambda value:self.set_feature('auto_profiles',value))
        setup.addWidget(self.auto_profiles_pick)
        row=QHBoxLayout()
        row.addWidget(button(tr('Привязать игру'),self.bind_game))
        row.addWidget(button(tr('Убрать привязку'),self.unbind_game))
        setup.addLayout(row)
        self.profile_binding=QLabel()
        self.profile_binding.setTextFormat(Qt.TextFormat.PlainText)
        self.profile_binding.setWordWrap(True)
        setup.addWidget(self.profile_binding)
        self.game.textChanged.connect(self.refresh_profile_binding)
        self.refresh_profile_binding()
        self.region_ocr=QPlainTextEdit(self);self.region_ocr.hide()
        self.region_ocr.setReadOnly(True)
        self.region_ocr.setMaximumHeight(100)
        self.region_ocr.setPlaceholderText(tr('Распознанный текст текущего кадра'))
        settings_layout.addStretch()
        self.update_region_label()
        self.refresh_key_labels()

    def sync_capture_controls(self):
        for control in (self.capture_buttons['region'],self.region_label):control.show()

    def open_translation_settings(self):
        index=next(i for i in range(self.tabs.count()) if self.tabs.list.item(i).text()==tr('Перевод'))
        self.tabs.setCurrentIndex(index);self.provider.setFocus(Qt.FocusReason.OtherFocusReason)

    def build_history(self):
        page = QWidget()
        manual = QVBoxLayout(page)
        manual.addWidget(note(tr('Можно исправить распознанный английский текст или ввести собственную фразу. История хранится только в текущей сессии.')))
        split = QSplitter(Qt.Orientation.Vertical)
        self.manual = QPlainTextEdit()
        self.manual.setPlaceholderText(tr('Распознанный английский текст или фраза для ручного перевода'))
        self.read_result = QPlainTextEdit()
        self.read_result.setReadOnly(True)
        self.read_result.setPlaceholderText(tr('Здесь появятся исходные реплики и переводы'))
        split.addWidget(self.manual)
        split.addWidget(self.read_result)
        split.setMinimumHeight(220)
        manual.addWidget(split)
        row = QHBoxLayout()
        row.addWidget(button(tr('Перевести'),self.manual_translate))
        self.manual_term = QLineEdit()
        self.manual_term.setPlaceholderText(tr('Слово или выражение'))
        row.addWidget(self.manual_term)
        row.addWidget(button(tr('Карточка слова'),lambda:self.show_card(self.manual_term.text(),self.manual.toPlainText())))
        manual.addLayout(row)
        self.tabs.addTab(page,tr('История'))

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(note(tr('Выбери переводчик и подключи свой аккаунт или ключ. Переключение на другой сервис всегда выполняется вручную.')))
        form = QFormLayout()
        self.provider = QComboBox()
        for value in ('yandex_web','subscription','api','mymemory','yandex','deepl','local'):
            self.provider.addItem(tr(LABELS[value]),value)
        self.provider.setCurrentIndex(max(0,self.provider.findData(self.settings['provider'])))
        form.addRow(tr('Переводчик'),self.provider)
        layout.addLayout(form)
        self.provider_pages = ProviderPages()
        self.provider_pages.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
        self.provider_indices = {}
        self.cloud_keys,self.cloud_status = {},{}
        for provider in ('yandex_web','subscription','api','mymemory','yandex','deepl','local'):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.provider_indices[provider] = self.provider_pages.addWidget(panel)
            if provider=='yandex_web':
                panel_layout.addWidget(note(tr('Ключ, регистрация и платёжный аккаунт не нужны. Нажми «Использовать» — перевод будет доступен в карточке, на снимке и в автоматическом оверлее.')))
                panel_layout.addWidget(note(tr('Неофициальное подключение к бесплатному переводу. Распознанный английский текст отправляется выбранному сервису. Возможны ограничения или изменение доступа. Повторные запросы ограничены по частоте; неизменный текст берётся из кэша.')))
            elif provider=='subscription':
                self.account_label = note('')
                panel_layout.addWidget(self.account_label)
                row = QHBoxLayout()
                self.login_button = button(tr('Войти в ChatGPT'),lambda:self.login(False),True)
                self.new_login_button = button(tr('Другой аккаунт'),lambda:self.login(True))
                self.logout_button = button(tr('Отключить'),self.logout)
                for b in (self.login_button,self.new_login_button,self.logout_button):row.addWidget(b)
                panel_layout.addLayout(row)
                panel_layout.addWidget(note(tr('В браузере разреши использование подписки. После входа получи модели ниже. Это расходует общие лимиты твоего плана ChatGPT.')))
            elif provider=='api':
                self.cloud_status['api'] = note('')
                panel_layout.addWidget(self.cloud_status['api'])
                self.api_key = QLineEdit()
                self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
                self.api_key.setPlaceholderText(tr('Собственный OpenAI API-ключ'))
                panel_layout.addWidget(self.api_key)
                row = QHBoxLayout()
                row.addWidget(button(tr('Сохранить ключ'),self.save_api_key))
                row.addWidget(button(tr('Удалить ключ'),self.delete_api_key))
                panel_layout.addLayout(row)
                panel_layout.addWidget(note(tr('API оплачивается отдельно от ChatGPT Plus. Сохранённый ключ скрыт и защищён Windows.')))
                panel_layout.addWidget(button(tr('Создать ключ OpenAI API'),lambda:self.open_link('https://platform.openai.com/api-keys')))
            elif provider=='mymemory':
                panel_layout.addWidget(note(tr('Бесплатный онлайн-перевод английский → русский без ключа и регистрации. Есть суточная квота; при исчерпании программа остановит перевод. Текст отправляется MyMemory. Качество зависит от доступных переводов.')))
            elif provider in ('yandex','deepl'):
                field = QLineEdit()
                field.setEchoMode(QLineEdit.EchoMode.Password)
                field.setPlaceholderText(tr('Собственный ключ ')+tr(LABELS[provider]))
                self.cloud_keys[provider] = field
                self.cloud_status[provider] = note('')
                panel_layout.addWidget(self.cloud_status[provider])
                panel_layout.addWidget(field)
                row = QHBoxLayout()
                row.addWidget(button(tr('Сохранить ключ'),lambda checked=False,p=provider:self.save_cloud_key(p)))
                row.addWidget(button(tr('Удалить ключ'),lambda checked=False,p=provider:self.delete_cloud_key(p)))
                panel_layout.addLayout(row)
                cloud_form = QFormLayout()
                if provider=='yandex':
                    self.yandex_auth = QComboBox()
                    self.yandex_auth.addItem(tr('API-ключ сервисного аккаунта'),'api_key')
                    self.yandex_auth.addItem(tr('IAM-токен пользователя'),'iam')
                    self.yandex_auth.setCurrentIndex(max(0,self.yandex_auth.findData(self.settings['yandex_auth'])))
                    self.yandex_folder = QLineEdit(self.settings['yandex_folder'])
                    self.yandex_folder.setPlaceholderText(tr('Нужен только для IAM-токена пользователя'))
                    cloud_form.addRow(tr('Авторизация'),self.yandex_auth)
                    cloud_form.addRow(tr('ID каталога'),self.yandex_folder)
                    panel_layout.addWidget(note(tr('Нужен доступ к Translate и роль ai.translate.user. API-ключ использует каталог своего сервисного аккаунта.')))
                    guide = 'https://aistudio.yandex.ru/ru/docs/translate/quickstart'
                elif provider=='deepl':
                    self.deepl_plan = QComboBox()
                    for label,value in [(tr('Определить по ключу'),'auto'),('DeepL API Free','free'),('DeepL API Pro','pro')]:self.deepl_plan.addItem(label,value)
                    self.deepl_plan.setCurrentIndex(max(0,self.deepl_plan.findData(self.settings['deepl_plan'])))
                    cloud_form.addRow(tr('Тариф API'),self.deepl_plan)
                    panel_layout.addWidget(note(tr('Нужен ключ именно DeepL API. У обычной подписки на сайт DeepL другой способ доступа.')))
                    guide = 'https://developers.deepl.com/docs/getting-started/auth'
                panel_layout.addLayout(cloud_form)
                panel_layout.addWidget(button(tr('Инструкция: где получить API-ключ'),lambda checked=False,u=guide:self.open_link(u)))
            else:
                panel_layout.addWidget(QLabel(tr('Готовая модель')))
                self.local_path = QLineEdit(self.settings.get('local_model',''))
                self.local_path.setPlaceholderText(tr('Папка en-ru'))
                row = QHBoxLayout()
                row.addWidget(self.local_path)
                row.addWidget(button(tr('Выбрать готовую модель…'),self.choose_model))
                panel_layout.addLayout(row)
                panel_layout.addWidget(QLabel(tr('Скачать в')))
                self.download_path = QLineEdit(self.settings.get('model_download_dir') or str(self.store.folder/'models'))
                row = QHBoxLayout()
                row.addWidget(self.download_path)
                row.addWidget(button(tr('Куда скачивать…'),self.choose_download_folder))
                panel_layout.addWidget(note(tr('Папка загрузки: внутри будет создана папка en-ru. Временный архив скачивается туда же.')))
                panel_layout.addLayout(row)
                self.download_button = button(tr('Скачать модель · 200 МБ'),self.install_model)
                panel_layout.addWidget(self.download_button)
                self.local_quality_pick=QComboBox()
                for label,value in [(tr('Быстро · меньше задержка'),'fast'),(tr('Баланс · по умолчанию'),'balanced'),(tr('Тщательнее · медленнее'),'quality')]:self.local_quality_pick.addItem(label,value)
                self.local_quality_pick.setCurrentIndex(max(0,self.local_quality_pick.findData(self.settings.get('local_quality','balanced'))))
                panel_layout.addWidget(QLabel(tr('Режим перевода')))
                panel_layout.addWidget(self.local_quality_pick)
                panel_layout.addWidget(note(tr('«Тщательнее» рассматривает больше вариантов, но не гарантирует лучший смысл. Повторяющиеся строки берутся из кэша. Модель работает на CPU и оставляет видеопамять игре.')))
                panel_layout.addWidget(note(tr('После загрузки путь появится в поле готовой модели. Модель работает на CPU, без сети. Объяснение грамматики доступно через GPT.')))
            panel_layout.addStretch()
        layout.addWidget(self.provider_pages)
        self.model_group = QWidget()
        model_form = QFormLayout(self.model_group)
        self.model_pick = ModelPicker()
        self.model_pick.setPlaceholderText(tr('Список загрузится после подключения'))
        self.model_pick.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.model_pick)
        self.model_refresh_button=button(tr('Обновить'),lambda:self.get_models(force=True))
        row.addWidget(self.model_refresh_button)
        model_form.addRow(tr('Модель GPT'),row)
        layout.addWidget(self.model_group)
        self.model_status=note('')
        self.model_status.setText(tr('Список загрузится автоматически после подключения.'))
        model_form.addRow(self.model_status)
        self.model_pick.setToolTip(tr('Модели выбранного подключения. Список обновляется при входе, смене переводчика и затем каждые пять минут, пока открыта вкладка. Обновление не выполняет перевод.'))
        row = QHBoxLayout()
        row.addWidget(button(tr('Использовать'),self.apply_settings,True))
        layout.addLayout(row)
        layout.addStretch()
        self.tabs.addTab(scroll(page),tr('Перевод'))
        self.build_ocr()
        self.build_appearance()
        self.build_dictionaries()
        self.provider.currentIndexChanged.connect(self.select_provider)
        self.sync_provider_page()

    def sync_provider_page(self):
        provider = self.provider.currentData()
        self.provider_pages.setCurrentIndex(self.provider_indices[provider])
        self.model_group.setVisible(provider in ('subscription','api'))
        self.provider_pages.updateGeometry()
        self.provider_pages.parentWidget().layout().invalidate()

    def build_ocr(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.ocr_engine_pick=ReadableCombo()
        for value,label in ocr.ENGINES:self.ocr_engine_pick.addItem(tr(label),value)
        self.ocr_engine_pick.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.ocr_engine_pick.setCurrentIndex(max(0,self.ocr_engine_pick.findData(self.settings.get('ocr_engine','windows'))))
        self.ocr_engine_pick.setToolTip(tr('Windows OCR — встроенный движок. Lexora Game OCR — дополнительная локальная модель для игровых текстов. Начни с универсального профиля и сравни результат в предпросмотре.'))
        self.ocr_device_pick=ReadableCombo()
        self.ocr_device_pick.addItem(tr('Видеокарта (GPU)'),'gpu');self.ocr_device_pick.addItem(tr('Процессор (CPU)'),'cpu')
        self.ocr_device_pick.setCurrentIndex(max(0,self.ocr_device_pick.findData(self.settings.get('ocr_device','gpu'))))
        self.ocr_device_pick.setToolTip(tr('Устройство для Lexora Game OCR. GPU ускоряет распознавание через DirectML и использует видеопамять. Если GPU недоступна, приложение перейдёт на CPU. Первый запуск может быть дольше.'))
        self.ocr_backend_status=note('')
        self.ocr_engine_pick.currentIndexChanged.connect(lambda _:self.ocr_device_pick.setEnabled(self.ocr_engine_pick.currentData()=='game'))
        self.ocr_device_pick.setEnabled(self.ocr_engine_pick.currentData()=='game')
        self.filter_pick = ReadableCombo()
        for value,label,description in ocr.PROFILES:self.filter_pick.addItem(tr(label),value)
        self.filter_pick.setCurrentIndex(max(0,self.filter_pick.findData(self.settings['filter'])))
        self.filter_description = note('')
        form=QFormLayout();form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(tr('Движок OCR'),self.ocr_engine_pick)
        form.addRow(tr('Вычисления'),self.ocr_device_pick)
        form.addRow(tr('Профиль OCR'),self.filter_pick);layout.addLayout(form)
        layout.addWidget(self.ocr_backend_status)
        layout.addWidget(self.filter_description)
        def describe():
            profile = next(p for p in ocr.PROFILES if p[0]==self.filter_pick.currentData())
            self.filter_description.setToolTip(tr(profile[2]))
        self.filter_pick.currentIndexChanged.connect(describe)
        describe()
        preview=button(tr('Предпросмотр'),self.preview_ocr);self.ocr_preview_button=preview
        preview.setToolTip(tr('Показывает исходный кадр, обработку и найденный текст. Использует выбранную область, а если её нет — весь монитор. Переводчику ничего не отправляется.'))
        actions=CompactRow();actions.addWidget(button(tr('Сохранить'),self.apply_ocr,True));actions.addWidget(preview);layout.addWidget(actions)
        from .ocr_preview import OCRPreview
        self.ocr_preview=OCRPreview();layout.addWidget(self.ocr_preview);self.ocr_preview.hide()
        layout.addStretch()
        self.tabs.addTab(scroll(page),tr('Распознавание'))
        page=QWidget();layout=QVBoxLayout(page)
        self.hotkey_fields={};self.mouse_hotkey_fields={};self.gamepad_hotkey_fields={}
        title=QLabel(tr('Привязки'));title.setObjectName('sectionTitle');layout.addWidget(title)
        subtitle=QLabel(tr('Настройте горячие клавиши и кнопки для быстрых действий в игре.'));subtitle.setObjectName('subtitle');subtitle.setWordWrap(True);layout.addWidget(subtitle)
        self.binding_table=BindingTable();self.device_panels=self.binding_table
        self.binding_panels=self.binding_table.headers;self.binding_icons=self.binding_table.icons
        layout.addSpacing(10);layout.addWidget(self.binding_table)
        for index,(action,label,icon_kind) in enumerate([('study',tr('Экранный словарь'),'dictionary'),('region',tr('Выбор области'),'region'),('toggle',tr('Автоперевод'),'auto'),('screen',tr('Текущий кадр'),'frame')]):
            row_fields=[]
            for device,title,fields in (('keyboard',tr('Клавиатура'),self.hotkey_fields),('mouse',tr('Мышь'),self.mouse_hotkey_fields),('gamepad',tr('Геймпад'),self.gamepad_hotkey_fields)):
                value=self.settings['gamepad_bindings'][action] if device=='gamepad' else device_bindings(self.settings['hotkeys'][action],device)
                field=BindingGamepadEdit(value) if device=='gamepad' else BindingKeyEdit(value,device)
                field.recordingChanged.connect(self.recording_changed)
                field.recorded.connect(lambda chord,key=action,kind=device:self.record_hotkey(key,chord,kind))
                field.invalid.connect(self.message);fields[action]=field
                field.setAccessibleName(title+': '+label)
                if device!='gamepad':field.setToolTip(tr('Нажми поле и прожми ')+(tr('клавишу или сочетание.') if device=='keyboard' else tr('Mouse3, Mouse4 или Mouse5. Можно с Ctrl, Alt или Shift.')))
                field.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                field.customContextMenuRequested.connect(lambda position,item=field,key=action,kind=device:self.binding_menu(item,key,kind,position))
                row_fields.append(field)
            self.binding_table.add_action(index,action,label,icon_kind,row_fields,self.reset_hotkey)
        self.gamepad_controls=self.binding_table.gamepad_panel
        extras=QWidget();gamepad_body=QVBoxLayout(extras);gamepad_body.setContentsMargins(0,0,0,0)
        from .binding_widgets import GamepadSwitch
        self.gamepad_enabled_pick=GamepadSwitch()
        self.gamepad_enabled_pick.setAccessibleName(tr('Включить привязки геймпада'))
        self.gamepad_enabled_pick.setChecked(self.settings['gamepad_enabled'])
        self.gamepad_enabled_pick.toggled.connect(self.set_gamepad_enabled)
        self.gamepad_device_pick=QComboBox();self.gamepad_device_pick.addItem(tr('Любой геймпад'),'')
        self.gamepad_device_pick.currentIndexChanged.connect(self.choose_gamepad)
        refresh=button(tr('Обновить'),self.refresh_gamepads);refresh.setToolTip(tr('Обновить список подключённых геймпадов'))
        gamepad_header=QHBoxLayout()
        pad_icon=QLabel();pad_icon.setFixedSize(36,36);pad_icon.setProperty('iconKind','gamepad');pad_icon.setObjectName('iconTile');pad_icon.setPixmap(device_icon('gamepad').pixmap(36,36));gamepad_header.addWidget(pad_icon)
        pad_labels=QVBoxLayout();pad_title=QLabel(tr('Использовать геймпад'));pad_title.setStyleSheet('font-weight: 600;');pad_labels.addWidget(pad_title)
        pad_subtitle=QLabel(tr('Позволяет назначать кнопки геймпада для действий Lexora'));pad_subtitle.setObjectName('subtitle');pad_subtitle.setWordWrap(True);pad_labels.addWidget(pad_subtitle)
        gamepad_header.addLayout(pad_labels,1);gamepad_header.addWidget(self.gamepad_enabled_pick);gamepad_body.addLayout(gamepad_header)
        gamepad_row=CompactRow();gamepad_row.addWidget(self.gamepad_device_pick);gamepad_row.addWidget(refresh)
        gamepad_body.addWidget(gamepad_row)
        self.gamepad_status=QLabel(tr('Устройства ещё не проверены.'))
        self.gamepad_status.setObjectName('subtitle');self.gamepad_status.setWordWrap(True);gamepad_body.addWidget(self.gamepad_status)
        self.binding_table.add_gamepad_controls(extras)
        self.tabs.list.currentItemChanged.connect(lambda current,previous:self.refresh_gamepads() if current and current.text()==tr('Привязки') else None)
        layout.addStretch()
        self.binding_hint=QLabel(tr('Правой кнопкой — дополнительные привязки.'))
        self.binding_hint.setObjectName('subtitle');self.binding_hint.setWordWrap(True);layout.addWidget(self.binding_hint)
        self.tabs.addTab(scroll(page),tr('Привязки'))

    def build_appearance(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        layout.addWidget(note(tr('Базовые размеры указаны в процентах. Точные размеры и отступ доступны в «Дополнительно». Колесо над числом меняет значение.')))
        self.ui_scale_pick = AdjustSpinBox()
        self.ui_scale_pick.setRange(60,175)
        self.ui_scale_pick.setSuffix(' %')
        self.ui_scale_pick.setValue(self.settings['ui_scale'])
        self.theme_pick = QComboBox()
        self.theme_pick.setIconSize(QSize(58,16));self.theme_pick.setMaxVisibleItems(12)
        for key,theme in THEMES.items():self.theme_pick.addItem(theme_swatch(theme),tr(theme['label']),key)
        self.theme_pick.setCurrentIndex(max(0,self.theme_pick.findData(self.settings['theme'])))
        adjustment(form,tr('Масштаб интерфейса'),self.ui_scale_pick,tr('100% — обычный размер. Больше значение — крупнее текст в программе и карточке.'))
        form.addRow(tr('Тема'),self.theme_pick)
        self.window_size_pick=QComboBox()
        for label,key in ((tr('720p · 1280 × 720'),'720p'),(tr('Full HD · 1920 × 1080'),'1080p'),
                          (tr('2K · 2560 × 1440'),'1440p'),(tr('Свой размер'),'custom')):
            self.window_size_pick.addItem(label,key)
        self.window_size_pick.setCurrentIndex(self.window_size_pick.findData(self.settings['window_preset']))
        window_row=CompactRow();window_row.addWidget(self.window_size_pick)
        self.window_lock_pick=QPushButton();self.window_lock_pick.setCheckable(True);self.window_lock_pick.setFixedSize(36,34)
        self.window_lock_pick.setIconSize(QSize(22,22))
        self.window_lock_pick.setStyleSheet('QPushButton { padding:0; }')
        self.window_lock_pick.setChecked(self.settings['window_size_locked']);window_row.addWidget(self.window_lock_pick)
        self.window_lock_pick.toggled.connect(self.change_size_locks)
        window_row.addWidget(button(tr('Сбросить'),self.reset_window_size))
        self.window_size_pick.setToolTip(tr('Если окно не помещается на мониторе, его размер подстраивается под рабочую область.'))
        form.addRow(tr('Размер окна'),window_row)
        self.card_theme_pick=QComboBox();self.card_theme_pick.setIconSize(QSize(58,16));self.card_theme_pick.setMaxVisibleItems(12)
        self.card_theme_pick.addItem(tr('Как у приложения'),'')
        for key,theme in CARD_THEMES.items():self.card_theme_pick.addItem(theme_swatch(theme),tr(theme['label']),key)
        self.card_theme_pick.setCurrentIndex(self.card_theme_pick.findData(self.settings['card_theme']))
        self.card_width_pick,self.card_height_pick = AdjustSpinBox(),AdjustSpinBox()
        self.card_width_pick.setRange(320,1000)
        self.card_height_pick.setRange(320,1100)
        self.card_width_pick.setValue(self.settings['card_width'])
        self.card_height_pick.setValue(self.settings['card_height'])
        self.card_opacity_pick = AdjustSpinBox()
        self.card_opacity_pick.setRange(40,100)
        self.card_opacity_pick.setSuffix(' %')
        self.card_opacity_pick.setValue(round(self.settings['card_opacity']*100))
        self.card_scale_pick=AdjustSpinBox();self.card_scale_pick.setRange(53,167);self.card_scale_pick.setSuffix(' %')
        self.card_scale_pick.setValue(round(self.card_width_pick.value()/CARD_DEFAULT[0]*100))
        self.card_size_pick=QComboBox()
        for label,key in ((tr('Стандартная · 600 × 700'),'default'),(tr('Компактная · 480 × 560'),'small'),
                          (tr('Крупная · 720 × 840'),'large'),(tr('Свой размер'),'custom')):self.card_size_pick.addItem(label,key)
        def sync_card_preset():
            size=(self.card_width_pick.value(),self.card_height_pick.value())
            key=next((key for key,value in CARD_SIZES.items() if value==size),'custom')
            with QSignalBlocker(self.card_size_pick):self.card_size_pick.setCurrentIndex(self.card_size_pick.findData(key))
        def sync_card_scale():
            with QSignalBlocker(self.card_scale_pick):self.card_scale_pick.setValue(round(self.card_width_pick.value()/CARD_DEFAULT[0]*100))
            sync_card_preset()
        def change_card_scale(percent):
            old_width=self.card_width_pick.value();old_height=self.card_height_pick.value()
            width=round(CARD_DEFAULT[0]*percent/100)
            with QSignalBlocker(self.card_scale_pick):
                self.card_width_pick.setValue(width)
                self.card_height_pick.setValue(round(old_height*width/old_width))
        self.card_scale_pick.valueChanged.connect(change_card_scale)
        self.card_width_pick.valueChanged.connect(sync_card_scale)
        self.card_height_pick.valueChanged.connect(sync_card_preset)
        self.card_size_pick.currentIndexChanged.connect(self.choose_card_size)
        sync_card_preset()
        card_row=CompactRow();card_row.addWidget(self.card_size_pick)
        self.card_lock_pick=QPushButton();self.card_lock_pick.setCheckable(True);self.card_lock_pick.setFixedSize(36,34)
        self.card_lock_pick.setIconSize(QSize(22,22))
        self.card_lock_pick.setStyleSheet('QPushButton { padding:0; }')
        self.card_lock_pick.setChecked(self.settings['card_size_locked']);card_row.addWidget(self.card_lock_pick)
        self.card_lock_pick.toggled.connect(self.change_size_locks)
        card_row.addWidget(button(tr('Сбросить'),self.reset_card_size))
        form.addRow(tr('Размер карточки'),card_row)
        adjustment(form,tr('Масштаб карточки'),self.card_scale_pick,tr('100% — ширина 600 пикселей. Карточку можно растянуть за край; точные размеры доступны в «Дополнительно».'))
        # Retained as an internal compatibility control for old preferences.
        self.card_background_pick=AdjustSpinBox()
        self.card_background_pick.setRange(15,100)
        self.card_background_pick.setSuffix(' %')
        self.card_background_pick.setValue(round(self.settings['card_background']*100))
        adjustment(form,tr('Фон карточки'),self.card_background_pick,tr('Ниже — игра сильнее видна через фон. Буквы и кнопки остаются чёткими.'))
        self.overlay_theme_pick=QComboBox();self.overlay_theme_pick.setIconSize(QSize(58,16));self.overlay_theme_pick.setMaxVisibleItems(12)
        self.overlay_theme_pick.addItem(tr('Как у приложения'),'')
        for key,theme in OVERLAY_THEMES.items():self.overlay_theme_pick.addItem(theme_swatch(theme),tr(theme['label']),key)
        self.overlay_theme_pick.setCurrentIndex(self.overlay_theme_pick.findData(self.settings['overlay_theme']))
        self.overlay_background_pick=AdjustSpinBox()
        self.overlay_background_pick.setRange(0,100)
        self.overlay_background_pick.setSuffix(' %')
        self.overlay_background_pick.setValue(round(self.settings['overlay_background']*100))
        adjustment(form,tr('Непрозрачность фона'),self.overlay_background_pick,tr('0% — только буквы, 100% — непрозрачный фон. В режиме замены фон всегда плотный, чтобы скрыть оригинал.'))
        self.size_pick = AdjustSpinBox()
        self.size_pick.setRange(12,48)
        self.size_pick.setValue(self.settings['font_size'])
        self.opacity_pick = AdjustSpinBox()
        self.opacity_pick.setRange(30,100)
        self.opacity_pick.setSuffix(' %')
        self.opacity_pick.setValue(round(self.settings['opacity']*100))
        self.offset_pick = AdjustSpinBox()
        self.offset_pick.setRange(0,180)
        self.offset_pick.setValue(self.settings['offset'])
        self.text_scale_pick=AdjustSpinBox();self.text_scale_pick.setRange(55,218);self.text_scale_pick.setSuffix(' %')
        self.text_scale_pick.setValue(round(self.size_pick.value()/22*100))
        def sync_text_scale():
            with QSignalBlocker(self.text_scale_pick):self.text_scale_pick.setValue(round(self.size_pick.value()/22*100))
        self.text_scale_pick.valueChanged.connect(lambda percent:self.size_pick.setValue(round(22*percent/100)))
        self.size_pick.valueChanged.connect(sync_text_scale)
        adjustment(form,tr('Размер перевода'),self.text_scale_pick,tr('100% — текст 22 пикселя. Точный размер — в «Дополнительно».'))
        adjustment(form,tr('Видимость перевода'),self.opacity_pick,tr('100% — полностью видимый перевод; 30% — более прозрачный.'))
        layout.addLayout(form)
        layout.addWidget(divider())
        self.appearance_advanced=Foldout(tr('Дополнительно'));layout.addWidget(self.appearance_advanced)
        detailed=QFormLayout()
        for control in (self.card_width_pick,self.card_height_pick,self.size_pick,self.offset_pick):control.setSuffix(' px')
        adjustment(detailed,tr('Ширина карточки'),self.card_width_pick,tr('Точная ширина карточки слова.'))
        adjustment(detailed,tr('Высота карточки'),self.card_height_pick,tr('Точная высота карточки слова.'))
        adjustment(detailed,tr('Размер перевода'),self.size_pick,tr('Точный размер букв экранного перевода.'))
        adjustment(detailed,tr('Отступ над оригиналом'),self.offset_pick,tr('0 — прямо над английским текстом. Больше — русский перевод располагается выше.'))
        self.appearance_advanced.body.addLayout(detailed)
        layout.addWidget(note(tr('Карточку можно перемещать за верхнюю полосу и растягивать за правый нижний угол. Прозрачность фона не уменьшает видимость текста. Масштаб интерфейса действует и на текст карточки.')))
        preview_themes=QFormLayout()
        preview_themes.addRow(tr('Тема карточки'),self.card_theme_pick)
        preview_themes.addRow(tr('Тема экранного перевода'),self.overlay_theme_pick)
        layout.addLayout(preview_themes)
        self.appearance_previews=PreviewBlocks(self.appearance_preview_settings,page);layout.addWidget(self.appearance_previews)
        for control in (self.theme_pick,self.card_theme_pick,self.overlay_theme_pick,self.screen_render):
            control.currentIndexChanged.connect(self.appearance_previews.refresh)
        for control in (self.ui_scale_pick,self.card_width_pick,self.card_height_pick,self.card_background_pick,
                        self.overlay_background_pick,self.size_pick,self.opacity_pick,self.offset_pick):
            control.valueChanged.connect(self.appearance_previews.refresh)
        row=CompactRow();row.addWidget(button(tr('Применить'),self.apply_appearance,True))
        self.appearance_reset_button=button(tr('Сбросить оформление'),self.reset_appearance)
        row.addWidget(self.appearance_reset_button);layout.addWidget(row)
        layout.addStretch()
        self.tabs.addTab(scroll(page),tr('Оформление'))

    def appearance_preview_settings(self):
        return {**self.settings,'ui_scale':self.ui_scale_pick.value(),'theme':self.theme_pick.currentData(),'card_theme':self.card_theme_pick.currentData(),
                'overlay_theme':self.overlay_theme_pick.currentData(),'overlay_background':self.overlay_background_pick.value()/100,
                'card_background':self.card_background_pick.value()/100,'card_width':self.card_width_pick.value(),
                'card_height':self.card_height_pick.value(),'font_size':self.size_pick.value(),'opacity':self.opacity_pick.value()/100,
                'offset':self.offset_pick.value(),'screen_mode':self.screen_render.currentData()}

    def build_dictionaries(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(note(tr('Встроенные словари работают без сети. Викисловарь содержит русские значения, транскрипцию и примеры. Наличие и подробность статьи зависят от слова.')))
        self.dictionary_list = QListWidget()
        self.dictionary_list.setObjectName('dictionaryList')
        layout.addWidget(self.dictionary_list)
        self.dictionary_preview=QPlainTextEdit()
        self.dictionary_preview.setReadOnly(True)
        self.dictionary_preview.setMaximumHeight(130)
        self.dictionary_preview.setPlaceholderText(tr('Выбери словарь, чтобы увидеть описание'))
        self.dictionary_list.currentItemChanged.connect(self.describe_dictionary)
        layout.addWidget(self.dictionary_preview)
        row = QHBoxLayout()
        row.addWidget(button(tr('Добавить словарь…'),self.import_dictionary))
        row.addWidget(button(tr('Применить выбор'),self.apply_dictionaries,True))
        layout.addLayout(row)
        layout.addWidget(note(tr('Викисловарь: значения, транскрипция и примеры. FreeDict/WikDict: перевод на русский. WordNet: определения и примеры на английском. Мои слова: твои сохранённые значения. Можно импортировать дополнительные словари с полями term/meaning или word/translation.')))
        layout.addStretch()
        self.tabs.addTab(scroll(page),tr('Словари'))
        self.refresh_dictionaries()
