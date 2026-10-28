"""A short, skippable first-run guide. Examples never capture or translate online."""
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QScrollArea,QStackedWidget,QSizePolicy
from .i18n import tr,trf
from .appearance_preview import PreviewCanvas,configure_demo_capture
from .ui_icons import device_icon
from .in_app_dialog import InAppDialog


class OnboardingDialog(InAppDialog):
    navigate=Signal(str)
    def __init__(self,window):
        super().__init__(window,tr('Знакомство с Lexora'));self.settings=dict(window.settings);self.step=0
        body=self.body;body.setSpacing(14)
        heading=QHBoxLayout();self.progress=QLabel();self.progress.setObjectName('subtitle');heading.addWidget(self.progress);heading.addStretch()
        self.skip_button=QPushButton(tr('Пропустить'));self.skip_button.setAutoDefault(False);self.skip_button.clicked.connect(self.reject);heading.addWidget(self.skip_button);body.addLayout(heading)
        self.pages=QStackedWidget();body.addWidget(self.pages,1)
        self.build_welcome();self.build_dictionary();self.build_screen();self.build_ready()
        footer=QHBoxLayout();self.back_button=QPushButton(tr('Назад'));self.back_button.clicked.connect(lambda:self.set_step(self.step-1));footer.addWidget(self.back_button)
        footer.addStretch();self.next_button=QPushButton();self.next_button.setObjectName('primary');self.next_button.setDefault(True);self.next_button.clicked.connect(self.advance);footer.addWidget(self.next_button);body.addLayout(footer)
        self.set_step(0)

    def page(self,title,description):
        page=QWidget();body=QVBoxLayout(page);body.setContentsMargins(4,4,4,4);body.setSpacing(12)
        heading=QLabel(tr(title));heading.setObjectName('panelTitle');heading.setWordWrap(True);body.addWidget(heading)
        heading.setStyleSheet(f'font-size:{round(26*self.settings.get("ui_scale",100)/100)}px; font-weight:600;')
        text=QLabel(tr(description));text.setWordWrap(True);body.addWidget(text)
        area=QScrollArea();area.setWidgetResizable(True);area.setWidget(page);self.pages.addWidget(area)
        return body

    def action_row(self,body,icon,title,text):
        row=QHBoxLayout();image=QLabel();image.setPixmap(device_icon(icon).pixmap(28,28));row.addWidget(image,0,Qt.AlignmentFlag.AlignTop)
        content=QVBoxLayout();heading=QLabel(tr(title));heading.setWordWrap(True);heading.setObjectName('actionTitle');content.addWidget(heading)
        description=QLabel(tr(text));description.setWordWrap(True);description.setObjectName('subtitle');content.addWidget(description);row.addLayout(content,1);body.addLayout(row)

    def shortcut(self,key):
        from .shortcuts import device_bindings
        keyboard=device_bindings(self.settings['hotkeys'].get(key,''),'keyboard')
        return keyboard.split(';')[0].strip() or tr('Не назначено')

    def build_welcome(self):
        body=self.page('Английский через игры','Lexora помогает понять реплику, разобрать отдельное слово и сохранить его для повторения. Покажем главное на коротких примерах.')
        self.action_row(body,'dictionary','Экранный словарь',trf('{0} — снимок экрана, выбор слова или фразы.',self.shortcut('study')))
        self.action_row(body,'translate','Перевод экрана','Один кадр или постоянный перевод выбранной области и всего экрана.')
        self.action_row(body,'words','Мои слова','Сохраняй интересные слова в карточке и возвращайся к ним в разделе «Повторение».')
        body.addStretch()

    def build_dictionary(self):
        body=self.page('Попробуй выбрать слово','В экранном словаре нажми на слово или выдели фразу. Карточка покажет значение и контекст. Escape закрывает снимок и возвращает в игру.')
        scene=QWidget();scene.setObjectName('tutorialScene');sample=QHBoxLayout(scene);sample.addStretch()
        for word in ('He','drew','his','sword.'):
            if word=='sword.':
                self.word_button=QPushButton(word);self.word_button.setObjectName('primary');self.word_button.clicked.connect(self.select_word);sample.addWidget(self.word_button)
            else:sample.addWidget(QLabel(word))
        sample.addStretch();body.addWidget(scene)
        self.word_result=QLabel(tr('Нажми sword, чтобы открыть учебную карточку.'));self.word_result.setWordWrap(True);body.addWidget(self.word_result)
        self.word_hint=QLabel(tr('Учебный пример'));self.word_hint.setObjectName('subtitle');body.addWidget(self.word_hint);body.addStretch()

    def select_word(self):
        self.word_result.setText(tr('sword — меч\nHe drew his sword. — Он обнажил свой меч.'))
        self.word_hint.setText(tr('В игре кнопка «Сохранить» добавит слово в «Мои слова».'))

    def build_screen(self):
        body=self.page('Три способа перевода','Экранный словарь — для отдельных слов. «Текущий кадр» переводит весь монитор один раз. Автоперевод следит за выбранной областью или всем экраном.')
        self.screen_preview=PreviewCanvas('screen',self.settings);body.addWidget(self.screen_preview)
        modes=QHBoxLayout();self.mode_buttons=[]
        for label,mode in (('Над оригиналом','above'),('Вместо оригинала','replace')):
            button=QPushButton(tr(label));button.setCheckable(True);button.clicked.connect(lambda checked=False,key=mode:self.choose_mode(key));modes.addWidget(button);self.mode_buttons.append((mode,button))
        body.addLayout(modes)
        keys=QLabel(trf('Текущий кадр: {0} · Автоперевод: {1}',self.shortcut('screen'),self.shortcut('toggle')));keys.setWordWrap(True);keys.setObjectName('subtitle');body.addWidget(keys)
        self.choose_mode('above');body.addStretch()

    def choose_mode(self,mode):
        settings={**self.settings,'screen_mode':mode};self.screen_preview.set_settings(settings)
        for key,button in self.mode_buttons:
            button.setChecked(key==mode);button.setObjectName('primary' if key==mode else '')
            button.style().unpolish(button);button.style().polish(button)

    def build_ready(self):
        body=self.page('Можно начинать','На игровом экране выбери нужное действие. Профиль игры создавать необязательно. Для перевода проверь выбранный сервис; при необходимости подключи аккаунт, API или локальную модель.')
        self.action_row(body,'translate','Перевод','Выбор сервиса и его подключения — в разделе «Перевод».')
        self.action_row(body,'keyboard','Привязки','Нажми поле команды и прожми удобную клавишу, кнопку мыши или геймпада.')
        self.action_row(body,'settings','Оформление','Настрой размер текста, фон и темы. Два примера показывают результат сразу.')
        self.setup_button=QPushButton(tr('Настроить переводчик'));self.setup_button.clicked.connect(lambda:self.finish_at('Перевод'));body.addWidget(self.setup_button,0,Qt.AlignmentFlag.AlignLeft)
        hint=QLabel(tr('Повторить обучение можно через «?» → «Знакомство с Lexora».'));hint.setWordWrap(True);hint.setObjectName('subtitle');body.addWidget(hint);body.addStretch()

    def set_step(self,index):
        self.step=max(0,min(self.pages.count()-1,index));self.pages.setCurrentIndex(self.step)
        self.progress.setText(trf('Шаг {0} из {1}',self.step+1,self.pages.count()))
        self.back_button.setEnabled(self.step>0);self.next_button.setText(tr('Начать пользоваться') if self.step==self.pages.count()-1 else tr('Далее'))

    def advance(self):
        if self.step==self.pages.count()-1:self.accept()
        else:self.set_step(self.step+1)

    def finish_at(self,page):self.navigate.emit(page);self.accept()


class Onboarding:
    def offer_onboarding(self):
        if self.settings.get('onboarding_completed',False):return
        def offer():
            if not self.closing and self.isVisible() and not self.isMinimized():self.show_onboarding()
        QTimer.singleShot(0,offer)

    def show_onboarding(self):
        if self.closing:return
        existing=getattr(self,'onboarding_dialog',None)
        if existing is not None:existing.raise_();existing.activateWindow();return
        dialog=OnboardingDialog(self);self.onboarding_dialog=dialog
        dialog.navigate.connect(self.onboarding_navigate)
        def finished(*_):
            self.settings['onboarding_completed']=True;self.store.save_settings(self.settings);self.onboarding_dialog=None
        dialog.finished.connect(finished);dialog.open();configure_demo_capture(dialog,self.settings)

    def onboarding_navigate(self,title):
        index=next((i for i in range(self.tabs.count()) if self.tabs.list.item(i).text()==tr(title)),None)
        if index is not None:self.tabs.setCurrentIndex(index)
