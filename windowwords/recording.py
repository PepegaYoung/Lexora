"""Opt-in visibility in desktop recordings with an independent OCR source."""
from .i18n import tr,trf
from . import native
from .recording_capture import CleanCapture


class RecordingMode:
    def capture_session_image(self,box,revision=None):
        # Ordinary snapshots use BitBlt. WGC can hide the game's hardware cursor
        # in exclusive fullscreen, even after a short capture.
        if not self.settings.get('recording_visible',False):return self.capture_image(box)
        if not self.capture_permitted():raise RuntimeError(tr('Захват остановлен защитой игр.'))
        target=getattr(self,'recording_target',None)
        if not target:raise RuntimeError(tr('Переключись в игру и запусти действие горячей клавишей.'))
        # A still screenshot must not keep a recording session alive.
        capture=CleanCapture()
        revision=self.capture_epoch.value if revision is None else revision
        try:return capture.grab(target,box,cancel=lambda:self.closing or not self.session_active or not self.capture_epoch.accepts(revision))
        finally:capture.close()

    def capture_preview_image(self,box):
        if not self.settings.get('recording_visible',False):return self.capture_image(box)
        if not self.capture_permitted():raise RuntimeError(tr('Захват остановлен защитой игр.'))
        target=getattr(self,'recording_target',None)
        if not target:raise RuntimeError(tr('Переключись в игру и запусти действие горячей клавишей.'))
        # A preview must never leave the continuous auto-translation stream open.
        capture=CleanCapture()
        try:return capture.grab(target,box)
        finally:capture.close()

    def remember_recording_target(self,force=False):
        if not (self.running or self.session_active):
            current=native.foreground()
            if current and not native.is_our_window(current):self.last_game_window=current
        if not self.settings.get('recording_visible',False):return
        if not force and (self.running or self.session_active):return
        hwnd=native.foreground()
        if hwnd and not native.is_our_window(hwnd):self.recording_target=hwnd

    def prepare_recording_capture(self):
        if not self.settings.get('recording_visible',False):return True
        self.remember_recording_target(force=True)
        target=getattr(self,'recording_target',None)
        if target and native.user.IsWindow(target):return True
        self.message(tr('Режим записи: переключись в игру и запусти действие горячей клавишей.'))
        return False

    def apply_recording_visibility(self):
        visible=bool(self.settings.get('recording_visible',False))
        windows=(self,self.card,self.overlay,self.result_window,getattr(self,'freeze',None))
        for widget in windows:
            if widget is None:continue
            widget.setProperty('captureVisible',visible)
            if widget is self.overlay:widget.capture_excluded=False
            if not native.exclude_capture(widget):
                self.message(tr('Windows не применил видимость в записи. Попробуй переключить режим повторно.'))

    def set_recording_mode(self,visible):
        self.stop()
        self.settings['recording_visible']=bool(visible)
        self.store.save_settings(self.settings)
        self.apply_recording_visibility();self.remember_recording_target()
        self.message(tr('Режим записи включён: PrintScreen и OBS → Захват экрана.') if visible else tr('Режим записи выключен: Lexora исключена из захвата.'))

    def init_recording_mode(self):
        self.last_game_window=None;self.recording_target=None;self.recording_capture=CleanCapture()
        self.profile_timer.timeout.connect(self.remember_recording_target)
        self.apply_recording_visibility();self.remember_recording_target()
