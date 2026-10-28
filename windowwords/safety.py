"""Opt-out of translation around selected games, never evade their anti-cheat."""
from .i18n import tr,trf
import ntpath,os
from functools import wraps
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QComboBox,QFormLayout,QListWidget,QPushButton,QDialog
from .processes import running_executables

DEFAULT_PROTECTED=('marvel.exe','marvel-win64-shipping.exe','marvelrivals.exe')

def executable_name(value):
    if not isinstance(value,str):raise ValueError(tr('Выбери EXE игры.'))
    name=ntpath.basename(value.strip()).casefold()
    if not name.endswith('.exe') or len(name)>260 or any(c in name for c in '\\/:*?"<>|\r\n'):
        raise ValueError(tr('Нужно имя EXE без масок.'))
    return name

def protected_match(settings,names):
    if not settings.get('game_protection',True):return ''
    protected={executable_name(value) for value in settings.get('protected_games',DEFAULT_PROTECTED)}
    return next(iter(sorted(protected & {name.casefold() for name in names})), '')

def game_action(function):
    @wraps(function)
    def guarded(self,*args,**kwargs):
        if self.allow_game_action():return function(self,*args,**kwargs)
    return guarded

class GameSafety:
    def init_safety_state(self):
        self.safety_blocked=False
        self.safety_reason=''
        self.safety_quit_pending=False
        self.safety_timer=QTimer(self)
        self.safety_timer.setInterval(500)
        self.safety_timer.timeout.connect(self.check_game_protection)

    def build_safety_page(self):
        page=QWidget();layout=QVBoxLayout(page)
        title=QLabel(tr('Защита игр'));title.setObjectName('sectionTitle');layout.addWidget(title)
        self.safety_explanation=QLabel(tr('Lexora распознаёт текст со снимка экрана и показывает перевод в своём окне. Она не внедряется в игру, не читает её память и не меняет файлы.\n\nЗащиту можно включить для игр, в которых античит реагирует на сторонние приложения или их горячие клавиши. При запуске такой игры Lexora закроется или отключит перевод и привязки — в зависимости от выбранного действия. В остальных играх включать защиту необязательно.'))
        self.safety_explanation.setObjectName('subtitle');self.safety_explanation.setWordWrap(True);layout.addWidget(self.safety_explanation)
        self.safety_enabled=QCheckBox(tr('Включить защиту для игр из списка'))
        self.safety_enabled.setChecked(self.settings.get('game_protection',True))
        self.safety_enabled.setToolTip(tr('Проверка всех запущенных игр, включая свёрнутые. Проверяется только имя процесса Windows.'))
        layout.addWidget(self.safety_enabled)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.safety_action_pick=QComboBox()
        self.safety_action_pick.addItem(tr('Закрыть Lexora'),'quit')
        self.safety_action_pick.addItem(tr('Отключить перевод и привязки'),'pause')
        self.safety_action_pick.setCurrentIndex(max(0,self.safety_action_pick.findData(self.settings.get('protection_action','quit'))))
        form.addRow(tr('При запуске игры'),self.safety_action_pick);layout.addLayout(form)
        self.safety_action_note=QLabel();self.safety_action_note.setObjectName('subtitle');self.safety_action_note.setWordWrap(True);layout.addWidget(self.safety_action_note)
        layout.addWidget(QLabel(tr('Выбранные игры')))
        self.protected_list=QListWidget()
        self.protected_list.setObjectName('protectedGamesList')
        self.protected_list.addItems(self.settings.get('protected_games',list(DEFAULT_PROTECTED)))
        layout.addWidget(self.protected_list,1)
        row=QHBoxLayout()
        for title,action in ((tr('Добавить игру'),self.add_protected_game),(tr('Убрать'),self.remove_protected_game)):
            item=QPushButton(title);item.clicked.connect(action);row.addWidget(item)
        layout.addLayout(row)
        self.safety_status=QLabel();self.safety_status.setWordWrap(True);layout.addWidget(self.safety_status)
        self.safety_resume=QPushButton(tr('Возобновить работу'));self.safety_resume.setObjectName('primary')
        self.safety_resume.clicked.connect(self.resume_game_protection);layout.addWidget(self.safety_resume,0,Qt.AlignmentFlag.AlignLeft)
        self.safety_resume.hide()
        self.tabs.addTab(page,tr('Защита игр'))
        self.safety_enabled.toggled.connect(self.save_game_protection)
        self.safety_action_pick.currentIndexChanged.connect(self.save_game_protection)

    def start_game_protection(self):
        for field in self.binding_fields():field.capture_guard=self.allow_game_action
        self.check_game_protection()
        self.safety_timer.start()

    def save_game_protection(self,*args):
        self.settings.update(game_protection=self.safety_enabled.isChecked(),protection_action=self.safety_action_pick.currentData(),
                             protected_games=[self.protected_list.item(i).text() for i in range(self.protected_list.count())])
        self.store.save_settings(self.settings)
        self.check_game_protection()

    def add_protected_game(self):
        if self.protected_list.count()>=100:self.message(tr('В списке уже 100 игр. Убери лишнюю запись.'));return
        from .process_picker import ProcessPicker
        picker=ProcessPicker(self)
        picker.setWindowTitle(tr('Добавить игру'))
        picker.confirm.setText(tr('Добавить'))
        if picker.exec()!=QDialog.DialogCode.Accepted or not picker.selected_exe:return
        name=executable_name(picker.selected_exe)
        if not self.protected_list.findItems(name,Qt.MatchFlag.MatchExactly):
            self.protected_list.addItem(name)
        self.save_game_protection()

    def remove_protected_game(self):
        row=self.protected_list.currentRow()
        if row>=0:self.protected_list.takeItem(row);self.save_game_protection()

    def safety_observation(self):
        if not self.settings.get('game_protection',True):return '',False
        try:return protected_match(self.settings,running_executables()),False
        except (OSError,ValueError,TypeError):return '',True

    def check_game_protection(self):
        if self.closing:return False
        match,failed=self.safety_observation()
        if match or failed:
            reason=tr('Игра запущена: ')+match if match else tr('Не удалось проверить процессы. Захват и горячие клавиши отключены.')
            self.suspend_game_activity(reason)
            if match and self.settings.get('protection_action','quit')=='quit' and not self.safety_quit_pending:
                self.safety_quit_pending=True
                QTimer.singleShot(0,self.exit_for_protection)
        self.refresh_safety_status(can_resume=not(match or failed))
        return not self.safety_blocked

    def refresh_safety_status(self,can_resume=None):
        if can_resume is None:
            match,failed=self.safety_observation();can_resume=not(match or failed)
        enabled=self.settings.get('game_protection',True)
        self.safety_action_pick.setEnabled(enabled)
        self.safety_action_note.setText(tr('Lexora полностью завершится, когда игра будет обнаружена.') if self.safety_action_pick.currentData()=='quit' else
                                       tr('Захват, карточки и привязки отключатся. Окно Lexora останется открытым.'))
        self.safety_action_note.setVisible(enabled)
        self.safety_status.setText((tr('Перевод и привязки отключены. ')+self.safety_reason) if self.safety_blocked else
                                  tr('Наблюдение включено · игр в списке: ')+str(self.protected_list.count()) if self.settings.get('game_protection',True) else tr('Автоматическая защита отключена.'))
        self.safety_resume.setVisible(self.safety_blocked and not self.safety_quit_pending)
        self.safety_resume.setEnabled(can_resume and not self.safety_quit_pending)
        if self.safety_blocked and can_resume:self.safety_status.setText(tr('Игра закрыта. Можно возобновить работу Lexora.'))

    def suspend_game_activity(self,reason):
        already=self.safety_blocked
        self.safety_blocked=True;self.safety_reason=reason
        if not already:
            self.close_session(restore=False)
            self.stop()
            self.timer.stop()
            self.lines=()
            self.auto_translate_timer.stop()
            self.stop_speech()
            for field in self.binding_fields():field.finish()
            self.hotkey_capture_active=False
            self.stop_hotkeys()
            # Queued jobs still finish their cleanup signals. Captures check
            # the protection state; translations reject invalid generations.
        self.refresh_safety_status()
        self.message(reason)

    def allow_game_action(self):
        return not self.closing and self.check_game_protection()

    def capture_permitted(self):
        # This method may run on an OCR worker; it never operates Qt widgets.
        if self.closing or self.safety_blocked:return False
        match,failed=self.safety_observation()
        return not (match or failed)

    def resume_game_protection(self):
        if self.closing or self.safety_quit_pending:return
        match,failed=self.safety_observation()
        if match or failed:
            self.check_game_protection();return
        if not self.safety_blocked:return
        self.safety_blocked=False;self.safety_reason=''
        self.timer.start()
        from . import native
        self.keys=native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
        self.start_hotkeys()
        self.refresh_safety_status()
        if not self.safety_blocked:self.message(tr('Lexora возобновлена. Перевод запускается вручную.'))

    def exit_for_protection(self):
        # Persist normal GUI settings, then end our own workers without waiting
        # for a remote translator. Never terminates or modifies another process.
        try:self.close()
        finally:os._exit(0)
