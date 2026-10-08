from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QInputDialog
from . import native

class ShortcutCapture:
    def single_hotkeys_enabled(self):
        app=QApplication.instance()
        # Keep single keys available on the captured frame, but release them for
        # typing/navigation in all other Lexora windows, including modal dialogs.
        return app.applicationState()!=Qt.ApplicationState.ApplicationActive or (
            self.freeze is not None and app.activeWindow() is self.freeze)

    def update_single_hotkeys(self,*args):
        if not self.closing and hasattr(self.keys,'set_single_enabled'):
            self.keys.set_single_enabled(self.single_hotkeys_enabled())

    def start_hotkeys(self):
        self.update_single_hotkeys()
        self.keys.start()

    def recording_changed(self,active):
        if self.closing:return
        if active:
            if self.hotkey_capture_active:return
            self.hotkey_capture_active=True
            self.close_session(restore=False)
            self.stop()
            self.keys.stop()
            self.keys.join(timeout=2)
        else:QTimer.singleShot(0,self.resume_hotkeys)

    def resume_hotkeys(self):
        if self.closing or not self.hotkey_capture_active:return
        if any(field.recording for field in self.hotkey_fields.values()):return
        self.hotkey_capture_active=False
        self.keys=native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
        self.start_hotkeys()

    def record_hotkey(self,action,chord):
        old=self.settings['hotkeys'][action]
        try:
            native.validate_bindings(dict(self.settings['hotkeys'],**{action:chord}))
        except ValueError as error:
            self.hotkey_fields[action].setText(old)
            self.message(str(error))
            return
        self.settings['hotkeys'][action]=chord
        self.store.save_settings(self.settings)
        self.refresh_key_labels()
        self.message('Привязки сохранены: '+chord)

    def remove_hotkey(self,action):
        field=self.hotkey_fields[action]
        field.finish()
        variants=native.hotkey_variants(self.settings['hotkeys'][action])
        if len(variants)==1:
            self.message('Чтобы заменить клавишу, нажми поле и прожми новую.')
            return
        choice,ok=QInputDialog.getItem(self,'Удалить привязку','Клавиша или сочетание',variants,0,False)
        if ok:
            variants.remove(choice)
            value='; '.join(variants)
            field.setText(value)
            self.record_hotkey(action,value)
            # Removing a binding does not start a capture session.
            if not self.hotkey_capture_active:
                self.keys.stop();self.keys.join(timeout=2)
                self.keys=native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
                self.keys.set_escape(self.session_active or self.running)
                self.start_hotkeys()
