import copy,json,platform,time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QPlainTextEdit,QFileDialog
from .core import Generation
from .learning import ReviewPage
from .speech import Speaker
from .diagnostics import Measurements,diagnosis
from .backup import export_backup,import_backup
from .design import VERSION
from . import native

class Features:
    def init_feature_state(self):
        self.measurements=Measurements()
        self.speaker=Speaker()
        self.speech_epoch=Generation()
        self.auto_card_inflight=False
        self.auto_translate_timer=QTimer(self)
        self.auto_translate_timer.setSingleShot(True)
        self.auto_translate_timer.timeout.connect(self.auto_translate_current)
        self.profile_candidate=''
        self.profile_seen=0
        self.profile_last=''
        self.profile_timer=QTimer(self)
        self.profile_timer.setInterval(1500)
        self.profile_timer.timeout.connect(self.detect_profile)
        self.diagnostic_timer=QTimer(self)
        self.diagnostic_timer.setInterval(1000)
        self.diagnostic_timer.timeout.connect(self.refresh_diagnostics)
        self.card.speak_word.connect(lambda:self.say(self.card.term.text()))
        self.card.speak_context.connect(lambda:self.say(self.card.sentence.toPlainText()))
        self.card.stop_speech.connect(self.stop_speech)
        self.card.term.textEdited.connect(self.card_input_changed)
        self.card.sentence.textChanged.connect(self.card_input_changed)
    def build_feature_pages(self):
        self.review_page=ReviewPage(self.store)
        self.review_page.speak.connect(self.say)
        self.review_page.stop_speech.connect(self.stop_speech)
        self.tabs.addTab(self.review_page,'Повторение')
        page=QWidget()
        layout=QVBoxLayout(page)
        version=QLabel('Lexora '+VERSION)
        layout.addWidget(version)
        self.diagnostic_text=QPlainTextEdit()
        self.diagnostic_text.setReadOnly(True)
        layout.addWidget(self.diagnostic_text,1)
        row=QHBoxLayout()
        for title,action in (('Обновить',self.refresh_diagnostics),('Отчёт об ошибке',self.export_report)):
            button=QPushButton(title);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row)
        row=QHBoxLayout()
        for title,action in (('Резервная копия',self.backup_all),('Восстановить копию',self.restore_all)):
            button=QPushButton(title);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row)
        text=QLabel('Копия содержит слова, прогресс и настройки. Ключи и вход в аккаунт не копируются. Отчёт содержит только технические счётчики.')
        text.setWordWrap(True)
        layout.addWidget(text)
        self.tabs.addTab(page,'Диагностика')
    def start_feature_timers(self):
        self.profile_timer.start();self.diagnostic_timer.start()
        self.refresh_diagnostics()
    def set_feature(self,key,enabled):
        self.settings[key]=bool(enabled)
        self.store.save_settings(self.settings)
        if key=='auto_translate_card':
            if enabled and self.card.isVisible():self.auto_translate_timer.start(350)
            else:self.auto_translate_timer.stop()
    def auto_translate_current(self):
        if self.closing or not self.settings.get('auto_translate_card') or not self.card.isVisible():return
        if self.card.answer.toPlainText().strip() or self.card.saved_id:return
        if self.auto_card_inflight or self.cloud_busy:
            self.auto_translate_timer.start(500)
            return
        self.analyze_card(False,automatic=True)
    def card_input_changed(self,*args):
        self.card_epoch.next()
        self.auto_translate_timer.stop()
        if self.settings.get('auto_translate_card') and self.card.isVisible() and not getattr(self.card,'saved_id',None):
            self.card.answer.clear()
            self.auto_translate_timer.start(350)
    def say(self,text):
        if not text.strip():return
        revision=self.speech_epoch.next()
        self.speaker.stop()
        self.message('Произношу английский текст…')
        def done(_):
            if self.speech_epoch.accepts(revision):self.message('Произношение завершено.')
        def failed(error):
            if self.speech_epoch.accepts(revision):self.message(error)
        self.task(lambda:self.measurements.run('speech',lambda:self.speaker.speak(text)) if self.speech_epoch.accepts(revision) else '',done,failed)
    def stop_speech(self):
        self.speech_epoch.next();self.speaker.stop()
    def bind_game(self):
        game=self.game.text().strip()
        if not game:self.message('Введи название игры перед привязкой.');return
        path,_=QFileDialog.getOpenFileName(self,'Исполняемый файл игры','','Приложения (*.exe)')
        if not path:return
        self.save_profile()
        exe=Path(path).name.casefold()
        self.settings['profile_apps'][exe]=game
        self.store.save_settings(self.settings)
        self.refresh_profile_binding()
        self.message('Профиль привязан: '+exe+' → '+game)
    def unbind_game(self):
        game=self.game.text().strip()
        self.settings['profile_apps']={exe:name for exe,name in self.settings['profile_apps'].items() if name!=game}
        self.store.save_settings(self.settings);self.refresh_profile_binding()
    def refresh_profile_binding(self):
        apps=[exe for exe,name in self.settings['profile_apps'].items() if name==self.game.text().strip()]
        self.profile_binding.setText('Привязка: '+(', '.join(apps) if apps else 'не задана'))
    def detect_profile(self):
        if self.closing or not self.settings.get('auto_profiles') or self.hotkey_capture_active or self.session_active or self.running:return
        exe=native.foreground_executable()
        if not exe:return
        if exe!=self.profile_candidate:self.profile_candidate=exe;self.profile_seen=1;return
        self.profile_seen+=1
        if self.profile_seen<2:return
        game=self.settings['profile_apps'].get(exe)
        if not game or game not in self.settings['profiles']:
            self.profile_last=''
            return
        if self.profile_last==exe:return
        self.profile_last=exe
        self.apply_profile(game)
    def apply_profile_appearance(self,profile):
        for key,control in (('card_width',self.card_width_pick),('card_height',self.card_height_pick)):
            if key in profile:control.setValue(profile[key])
        if 'card_background' in profile:self.card_background_pick.setValue(round(profile['card_background']*100))
        self.apply_appearance(persist=False)
        self.refresh_profile_binding()
    def refresh_diagnostics(self):
        if self.closing or not hasattr(self,'diagnostic_text'):return
        rows=self.measurements.snapshot()
        names={'ocr':'Распознавание','translate':'Перевод','speech':'Произношение'}
        text=[diagnosis(rows),'']
        for stage in ('ocr','translate','speech'):
            row=rows.get(stage)
            if row:text.append(f'{names[stage]}: последнее {row["last_ms"]} мс · среднее {round(row["total_ms"]/row["count"])} мс · операций {row["count"]} · ошибок {row["errors"]}')
            else:text.append(names[stage]+': ещё не запускалось')
        metrics=self.translator.metrics
        text.extend(['',f'Переводы из кэша: {metrics["cache_hits"]} · обращения к переводчику: {metrics["attempts"]}',
                     'Время измеряется с ожиданием переводчика. Цену и остаток лимитов эти счётчики не определяют.'])
        value='\n'.join(text)
        if self.diagnostic_text.toPlainText()!=value:self.diagnostic_text.setPlainText(value)
    def report(self):
        return {'application':'Lexora','version':VERSION,'os':platform.platform(),
            'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'provider':self.settings['provider'],'ocr_profile':self.settings['filter'],'display_mode':self.settings['game_mode'],
            'measurements':self.measurements.snapshot(),'translation_counts':dict(self.translator.metrics),
            'monitor_sizes':[[m['w'],m['h']] for m in self.monitors]}
    def export_report(self):
        path,_=QFileDialog.getSaveFileName(self,'Технический отчёт','Lexora-report.json','JSON (*.json)')
        if path:
            Path(path).write_text(json.dumps(self.report(),ensure_ascii=False,indent=2),encoding='utf-8')
            self.message('Отчёт сохранён. Он не содержит текстов, ключей и путей к файлам.')
    def backup_all(self):
        path,_=QFileDialog.getSaveFileName(self,'Резервная копия','Lexora-backup.json','JSON (*.json)')
        if path:
            export_backup(self.store,self.settings,Path(path))
            self.message('Слова, прогресс и настройки сохранены. Ключи и аккаунты в копию не входят.')
    def restore_all(self):
        path,_=QFileDialog.getOpenFileName(self,'Восстановить резервную копию','','JSON (*.json)')
        if not path:return
        try:settings,count=import_backup(self.store,Path(path))
        except (ValueError,OSError,KeyError,TypeError):self.message('Копия повреждена или не поддерживается. Настройки не восстановлены.');return
        self.close_session(restore=False);self.stop();self.stop_speech()
        self.settings=settings
        self.auto_translate_timer.stop();self.profile_timer.stop()
        self.refresh_library();self.review_page.refresh()
        self.message(f'Восстановлено записей: {count}. Перезапусти Lexora, чтобы применить все настройки.')
    def close_features(self):
        self.auto_translate_timer.stop();self.profile_timer.stop();self.diagnostic_timer.stop()
        self.speech_epoch.next();self.speaker.stop(closing=True)
