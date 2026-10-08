import copy
import time
from PySide6.QtCore import QTimer
from .core import Box,Line
from .screen import Tracker
from . import ocr
from .providers import LABELS


class ScreenMode:
    def screen_box(self):
        if self.settings.get('screen_scope')=='monitor':
            m=self.monitor
            return Box(m['x'],m['y'],m['w'],m['h'])
        return self.region

    def screen_options(self):
        self.stop()
        self.settings.update(screen_scope=self.screen_scope.currentData(),screen_mode=self.screen_render.currentData())
        self.store.save_settings(self.settings)
        self.message('Режим выбран. Переведи кадр или включи автоматическое обновление.')

    def start_screen(self,once=False):
        self.stop()
        if not self.screen_box():
            self.message('Выбери область или переключи охват на «Весь выбранный монитор».')
            return
        if self.session_active:self.close_session(restore=False)
        self.hover=False
        self.settings['game']=self.game.text()
        self.running=True
        self.screen_snapshot=once
        self.screen_loaded=False
        self.screen_tracks=Tracker()
        self.keys.set_escape(True)
        self.refresh_key_labels()
        self.message(('Снимок: ' if once else 'Авто: ')+'распознаю текст · '+LABELS[self.settings['provider']])
        # The regular main window remains in Alt+Tab; no focusable overlay.
        self.showMinimized()
        revision=self.epoch.value
        QTimer.singleShot(220,lambda:self.tick() if self.epoch.accepts(revision) and self.running else None)

    def translate_screen_once(self):
        self.start_screen(True)

    def toggle(self):
        if self.running:self.stop()
        else:self.start_screen(False)

    def tick(self):
        if self.freeze:return
        if self.running and getattr(self,'screen_snapshot',False) and self.screen_loaded:
            self.pump_screen()
            return
        box=self.screen_box() if self.running else self.region
        if self.ocr_busy or not box or not(self.running or self.hover):return
        self.ocr_busy=True
        revision=self.epoch.value
        profile=self.settings['filter']
        def done(lines):
            self.ocr_busy=False
            if not self.epoch.accepts(revision) or self.freeze:return
            self.lines=lines
            self.ocr_box=box
            self.region_ocr.setPlainText('\n'.join(l.text for l in lines))
            if self.running:
                self.screen_loaded=True
                self.screen_tracks.update(lines,time.monotonic(),instant=self.screen_snapshot)
                self.draw_screen()
                self.pump_screen()
        def failed(error):
            self.ocr_busy=False
            if self.epoch.accepts(revision):self.stop();self.message(error)
        self.task(lambda:self.measurements.run('ocr',lambda:ocr.read(self.capture_image(box),profile)),done,failed)

    def pump_screen(self):
        if not self.running or self.cloud_busy:return
        missing=self.screen_tracks.missing()
        if not missing:return
        batch=[]
        for text in missing:
            if batch and (len(batch)>=12 or sum(map(len,batch))+len(text)>3000):break
            batch.append(text)
        self.cloud_busy=True
        revision=self.epoch.value
        tracker=self.screen_tracks
        settings=copy.deepcopy(self.settings)
        self.message(f'Перевожу {len(batch)} фрагм. · '+LABELS[settings['provider']])
        def done(result):
            self.cloud_busy=False
            if not self.running or not self.epoch.accepts(revision):return
            tracker.remember(batch,result)
            for source,target in zip(batch,result):
                self.history.append((source,target))
                self.read_result.appendPlainText(source+'\n→ '+target+'\n')
            self.history=self.history[-100:]
            self.draw_screen()
            self.pump_screen()
        def failed(error):
            self.cloud_busy=False
            if self.epoch.accepts(revision):
                self.stop()
                self.message(error)
                if self.isMinimized():self.tray.showMessage('Экранный перевод остановлен',error)
        self.task(lambda:self.measurements.run('translate',lambda:self.translator.translate_segments(settings,batch,cancel=lambda:not self.epoch.accepts(revision))),done,failed)

    def draw_screen(self):
        if not self.running:return
        ready=self.screen_tracks.ready()
        if self.external_mode():
            self.overlay.hide()
            if ready:
                if not self.result_window.display(ready,self.settings['font_size'],self.monitor):
                    self.stop()
                    self.message('Windows не смог исключить окно перевода из захвата. Используй снимок с диска или другой монитор.')
                    return
                self.message(f'Готово: {len(ready)} фрагм. · отдельное окно · Alt+T остановить')
            else:
                self.result_window.content.clear()
                self.result_window.last=''
                if not self.screen_tracks.items:self.message('Текст не найден. Проверь область и профиль OCR.')
            return
        if not ready:
            self.overlay.hide()
            if not self.screen_tracks.items:self.message('Текст не найден. Попробуй профиль OCR «Универсальный» или «Белый + жёлтый».')
            return
        try:
            skipped=self.overlay.display_segments(ready,self.screen_box(),self.monitor,self.settings,
                                                  [t.line for t in self.screen_tracks.items])
        except RuntimeError as error:
            self.stop();self.message(str(error));return
        suffix=f' · {skipped} фрагм. не поместились; переводы есть в истории.' if skipped else ''
        self.message(f'Готово: {len(ready)-skipped} фрагм. · '+('снимок, Alt+V обновить' if self.screen_snapshot else 'автоматическое обновление')+' · Escape закрыть'+suffix)
