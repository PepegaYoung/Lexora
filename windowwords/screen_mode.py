from .i18n import tr,trf
import copy
import time
import hashlib
from PySide6.QtCore import QTimer
from .core import Box,Line,Word,normalized
from .screen import Tracker,intersection
from . import ocr,native
from .providers import LABELS
from .safety import game_action


class ScreenMode:
    def screen_box(self,full_monitor=False):
        if full_monitor or (self.running and getattr(self,'screen_snapshot',False)) or self.settings.get('screen_scope')=='monitor':
            m=self.monitor
            return Box(m['x'],m['y'],m['w'],m['h'])
        return self.region

    def screen_options(self):
        self.stop()
        self.settings.update(screen_scope=self.screen_scope.currentData(),screen_mode=self.screen_render.currentData())
        self.store.save_settings(self.settings)
        self.message(tr('Режим выбран. Переведи кадр или включи автоматическое обновление.'))

    @game_action
    def start_screen(self,once=False):
        if self.settings.get('recording_visible',False) and not self.prepare_recording_capture():return
        self.stop()
        if not self.screen_box(full_monitor=once):
            self.message(tr('Выбери область или переключи охват на «Весь выбранный монитор».'))
            return
        if self.session_active:self.close_session(restore=False)
        if hasattr(self,'last_game_window'):
            target=native.foreground()
            target=target if target and not native.is_our_window(target) else self.last_game_window
            self.screen_target=target if native.client_bounds(target) else None
        self.settings['game']=self.game.text()
        self.running=True
        self.screen_suspended=False
        self.screen_snapshot=once
        self.screen_loaded=False
        self.screen_tracks=Tracker()
        self.keys.set_escape(bool(once))
        self.refresh_key_labels()
        self.message((tr('Снимок: ') if once else tr('Авто: '))+tr('распознаю текст · ')+tr(LABELS[self.settings['provider']]))
        # The regular main window remains in Alt+Tab; no focusable overlay.
        self.showMinimized()
        revision=self.epoch.value
        QTimer.singleShot(220,lambda:self.tick() if self.epoch.accepts(revision) and self.running else None)

    def translate_screen_once(self):
        self.start_screen(True)

    def toggle(self):
        if self.running:self.stop()
        else:
            self.auto_options.set_expanded(True)
            self.start_screen(False)

    def tick(self):
        if self.closing or self.safety_blocked or self.freeze:return
        if self.running and not self.screen_in_focus():return
        if self.running and getattr(self,'screen_snapshot',False) and self.screen_loaded:
            self.draw_screen()
            self.pump_screen()
            return
        box=self.screen_box() if self.running else self.region
        if self.ocr_busy or not box or not self.running:return
        self.ocr_busy=True
        revision=self.epoch.value
        self.screen_ocr_revision=revision
        profile=self.settings['filter']
        engine=self.settings.get('ocr_engine','windows')
        device=self.settings.get('ocr_device','gpu')
        previous=tuple(track.line for track in sorted(self.screen_tracks.items,key=lambda track:track.seen)
                       if track.stable)
        bounds=self.screen_bounds()
        if bounds.w<=0 or bounds.h<=0:
            self.overlay.hide();self.ocr_busy=False;self.screen_ocr_revision=None
            self.message(tr('Игра свёрнута или находится вне области перевода.'))
            return
        def done(lines):
            if self.screen_ocr_revision!=revision:return
            self.screen_ocr_revision=None
            self.ocr_busy=False
            if not self.epoch.accepts(revision) or not self.running or self.freeze:return
            lines=tuple(line for line in lines if bounds.contains(box.x+line.box.x+line.box.w/2,box.y+line.box.y+line.box.h/2))
            self.lines=lines
            self.ocr_box=box
            self.region_ocr.setPlainText('\n'.join(l.text for l in lines))
            if self.running:
                self.screen_loaded=True
                self.screen_tracks.update(lines,time.monotonic(),instant=self.screen_snapshot)
                self.draw_screen()
                self.pump_screen()
        def failed(error):
            if self.screen_ocr_revision!=revision:return
            self.screen_ocr_revision=None
            self.ocr_busy=False
            if self.epoch.accepts(revision):self.stop();self.message(error)
        def recognize():
            if not self.running or self.closing or not self.epoch.accepts(revision):return ()
            def read_frame():
                # Crop before the detector downsizes the image. In a windowed
                # game the desktop must not consume its OCR resolution budget.
                image=self.capture_screen_image(bounds,revision)
                key=(revision,box,bounds,profile,engine,device,image.size,
                     hashlib.blake2b(image.tobytes(),digest_size=16).digest())
                cached=getattr(self,'screen_frame_cache',None)
                dx,dy=bounds.x-box.x,bounds.y-box.y
                if cached and cached[0]==key:lines=cached[1]
                else:
                    from .screen_recovery import tracked_subtitle
                    scan_key=(revision,box,bounds,profile,engine,device)
                    full_scan=getattr(self,'screen_full_scan',None)
                    lines=None
                    # Inspect a known subtitle at full glyph resolution between
                    # full-screen scans. Every success requires fresh OCR proof;
                    # a new/absent phrase falls back to the full detector now.
                    if (not self.screen_snapshot and len(self.screen_tracks.items)==1 and full_scan
                            and full_scan[0]==scan_key and time.monotonic()-full_scan[1]<.75):
                        lines=tracked_subtitle(image,previous,profile,engine,device,(dx,dy))
                    if lines is None:
                        lines=ocr.read(image,profile,engine,device)
                        if dx or dy:
                            def shifted(rect):return Box(rect.x+dx,rect.y+dy,rect.w,rect.h)
                            lines=tuple(Line(line.text,shifted(line.box),tuple(Word(word.text,shifted(word.box)) for word in line.words)) for line in lines)
                        if self.running and self.epoch.accepts(revision):self.screen_full_scan=(scan_key,time.monotonic())
                    if self.running and self.epoch.accepts(revision):self.screen_frame_cache=(key,lines)
                if previous and not self.screen_snapshot and self.running and self.epoch.accepts(revision):
                    from .screen_recovery import recover_labels
                    lines=recover_labels(image,lines,previous,profile,engine,device,(dx,dy))
                return lines
            return self.measurements.run('ocr',read_frame)
        self.task(recognize,done,failed)

    def screen_bounds(self):
        box=self.screen_box()
        target=getattr(self,'screen_target',None)
        if not target:return box
        bounds=native.client_bounds(target)
        return intersection(box,bounds) if bounds else Box(box.x,box.y,0,0)

    def screen_in_focus(self):
        target=getattr(self,'screen_target',None)
        if not target or getattr(self,'external_mode',lambda:False)():return True
        if native.foreground()!=target:
            self.overlay.hide()
            if not getattr(self,'screen_suspended',False):
                self.screen_suspended=True
                self.epoch.next()
                if getattr(self,'screen_ocr_revision',None) is not None:self.ocr_busy=False
                if getattr(self,'screen_cloud_revision',None) is not None:self.cloud_busy=False
                self.screen_ocr_revision=self.screen_cloud_revision=None
                if hasattr(self,'recording_capture'):self.recording_capture.close()
                if not getattr(self,'screen_snapshot',False):self.screen_tracks.items=[]
                self.message(tr('Экранный перевод на паузе: вернись в игру — он продолжится автоматически.'))
            return False
        if getattr(self,'screen_suspended',False):
            self.screen_suspended=False
            self.message(tr('Игра активна: экранный перевод продолжен.'))
        # This also runs while OCR/network work is pending and the text is
        # unchanged. The game may have raised its own window above our layer.
        self.overlay.keep_above_game(target)
        return True

    def screen_health(self):
        target=getattr(self,'screen_target',None)
        shown=self.overlay.isVisible()
        tracker=getattr(self,'screen_tracks',None)
        return {'enabled':bool(self.running),'paused_for_focus':bool(getattr(self,'screen_suspended',False)),
                'game_in_foreground':native.foreground()==target if target else None,
                'ocr_lines':len(getattr(self,'lines',())),
                'ready_fragments':len(tracker.ready()) if tracker else 0,
                'overlay_window_shown':shown,
                'overlay_above_game':native.window_above(self.overlay,target) if target and shown else None,
                'layer_recoveries':self.overlay.layer_recoveries}

    def capture_screen_image(self,box,revision=None):
        # Keep normal translation on the compatible desktop capture. A game's
        # client bounds still limit OCR and placement, independently of backend.
        if self.settings.get('recording_visible',False):
            if not self.capture_permitted():raise RuntimeError(tr('Захват остановлен защитой игр.'))
            target=getattr(self,'recording_target',None)
            if not target:raise RuntimeError(tr('Переключись в игру и запусти действие горячей клавишей.'))
            revision=self.epoch.value if revision is None else revision
            return self.recording_capture.grab(target,box,cancel=lambda:self.closing or not self.running or not self.epoch.accepts(revision))
        return self.capture_image(box)

    def pump_screen(self):
        if self.safety_blocked or not self.running or self.cloud_busy:return
        if not self.screen_in_focus():return
        missing=self.screen_tracks.missing()
        if not missing:return
        batch=[]
        for text in missing:
            if batch and (len(batch)>=12 or sum(map(len,batch))+len(text)>3000):break
            batch.append(text)
        self.cloud_busy=True
        revision=self.epoch.value
        self.screen_cloud_revision=revision
        tracker=self.screen_tracks
        settings=copy.deepcopy(self.settings)
        source_keys={normalized(text) for text in batch}
        def obsolete():
            return not source_keys.intersection(normalized(track.line.text) for track in tracker.items)
        self.message(trf('Перевожу {0} фрагм. · ',len(batch))+tr(LABELS[settings['provider']]))
        def done(result):
            if self.screen_cloud_revision!=revision:return
            self.screen_cloud_revision=None
            self.cloud_busy=False
            if not self.running or not self.epoch.accepts(revision):return
            tracker.remember(batch,result)
            visible={normalized(track.line.text) for track in tracker.items if track.stable}
            for source,target in zip(batch,result):
                if normalized(source) in visible:
                    self.history.append((source,target))
                    self.read_result.appendPlainText(source+'\n→ '+target+'\n')
            self.history=self.history[-100:]
            self.draw_screen()
            self.pump_screen()
        def failed(error):
            if self.screen_cloud_revision!=revision:return
            self.screen_cloud_revision=None
            self.cloud_busy=False
            if self.epoch.accepts(revision):
                if obsolete():
                    self.pump_screen()
                    return
                self.stop()
                self.message(error)
                if self.isMinimized():self.tray.showMessage(tr('Экранный перевод остановлен'),error)
        self.task(lambda:self.measurements.run('translate',lambda:self.translator.translate_segments(settings,batch,cancel=lambda:not self.epoch.accepts(revision) or obsolete())),done,failed)

    @game_action
    def draw_screen(self):
        if not self.running:return
        if not self.screen_in_focus():return
        ready=self.screen_tracks.ready()
        if self.external_mode():
            self.overlay.hide()
            if ready:
                if not self.result_window.display(ready,self.settings['font_size'],self.monitor):
                    self.stop()
                    self.message(tr('Windows не смог исключить окно перевода из захвата. Используй снимок с диска или другой монитор.'))
                    return
                self.message(trf('Готово: {0} фрагм. · отдельное окно · Alt+T остановить',len(ready)))
            else:
                self.result_window.content.clear()
                self.result_window.last=''
                if not self.screen_tracks.items:self.message(tr('Текст не найден. Проверь область и профиль OCR.'))
            return
        if not ready:
            self.overlay.hide()
            if not self.screen_tracks.items:self.message(tr('Текст не найден. Попробуй профиль OCR «Универсальный» или «Белый + жёлтый».'))
            return
        try:
            from .screen import protected_lines
            skipped=self.overlay.display_segments(ready,self.screen_box(),self.monitor,self.settings,
                                                  [t.line for t in self.screen_tracks.items],bounds=self.screen_bounds(),target=getattr(self,'screen_target',None),
                                                  protected=protected_lines(getattr(self,'lines',())))
        except RuntimeError as error:
            self.stop();self.message(str(error));return
        suffix=trf(' · {0} фрагм. не поместились; переводы есть в истории.',skipped) if skipped else ''
        close_hint=tr(' · Escape закрыть') if self.screen_snapshot else tr(' · остановить: ')+self.settings['hotkeys']['toggle']
        self.message(trf('Готово: {0} фрагм. · ',len(ready)-skipped)+(tr('снимок, ')+self.settings['hotkeys']['screen']+tr(' обновить') if self.screen_snapshot else tr('автоматическое обновление'))+close_hint+suffix)
