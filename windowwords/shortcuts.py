from .i18n import tr,trf
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QInputDialog
from . import native,gamepad
from .input_keys import MOUSE_KEYS

def device_bindings(value,device):
    return '; '.join(chord for chord in native.hotkey_variants(value)
                     if (native.parse_hotkey(chord)[1] in MOUSE_KEYS)==(device=='mouse'))

class ShortcutCapture:
    def binding_fields(self):
        return [field for group in (self.hotkey_fields,self.mouse_hotkey_fields,self.gamepad_hotkey_fields) for field in group.values()]
    def field_group(self,device):
        return {'keyboard':self.hotkey_fields,'mouse':self.mouse_hotkey_fields,'gamepad':self.gamepad_hotkey_fields}[device]
    def current_bindings(self):
        return {key:'; '.join(value for value in (field.text().strip(),self.mouse_hotkey_fields[key].text().strip()) if value)
                for key,field in self.hotkey_fields.items()}
    def single_hotkeys_enabled(self):
        app=QApplication.instance()
        return app.applicationState()!=Qt.ApplicationState.ApplicationActive or (
            self.freeze is not None and app.activeWindow() is self.freeze)
    def update_single_hotkeys(self,*args):
        if not self.closing and not self.safety_blocked and hasattr(self.keys,'set_single_enabled'):
            self.keys.set_single_enabled(self.single_hotkeys_enabled())
    def init_gamepad_input(self):
        from .gamepad_input import GamepadHotkeys
        self.gamepad_keys=GamepadHotkeys(self,lambda:not(self.closing or self.safety_blocked or self.hotkey_capture_active))
        self.gamepad_keys.action.connect(self.hotkey.emit)
        self.gamepad_keys.failed.connect(self.message)
    def refresh_gamepad_input(self):
        if not hasattr(self,'gamepad_keys'):return
        self.gamepad_keys.start(self.settings['gamepad_bindings'],self.settings['gamepad_enabled'],self.gamepad_device_pick.currentData() or '')
    def set_gamepad_enabled(self,value):
        self.settings['gamepad_enabled']=bool(value)
        self.store.save_settings(self.settings)
        self.refresh_gamepad_input();self.refresh_key_labels()
    def refresh_gamepads(self):
        if not self.allow_game_action():return
        source=gamepad.RawControllerSource()
        try:devices=source.discover(force=True)
        except (OSError,RuntimeError,ImportError):self.gamepad_status.setText(tr('Не удалось получить список геймпадов Windows.'));return
        previous=self.gamepad_device_pick.currentData()
        self.gamepad_device_pick.blockSignals(True)
        self.gamepad_device_pick.clear();self.gamepad_device_pick.addItem(tr('Любой геймпад'),'')
        for device in devices:self.gamepad_device_pick.addItem(device.name,device.key)
        self.gamepad_device_pick.setCurrentIndex(max(0,self.gamepad_device_pick.findData(previous)))
        self.gamepad_device_pick.blockSignals(False)
        self.gamepad_families={device.key:device.family for device in devices}
        self.gamepad_status.setText(tr('Подключено: ')+str(len(devices)) if devices else tr('Геймпад не найден. Подключи по USB или Bluetooth и обнови список.'))
        self.choose_gamepad()
    def choose_gamepad(self,*args):
        key=self.gamepad_device_pick.currentData() or ''
        families=set(getattr(self,'gamepad_families',{}).values())
        family=getattr(self,'gamepad_families',{}).get(key) or (next(iter(families)) if len(families)==1 else 'mixed')
        for field in self.gamepad_hotkey_fields.values():
            field.finish();field.device=key;field.family=family;field.set_binding(field.value)
        self.refresh_gamepad_input();self.refresh_key_labels()
    def start_hotkeys(self):
        if not self.allow_game_action():return
        self.update_single_hotkeys();self.keys.start();self.refresh_gamepad_input()
    def stop_hotkeys(self):
        if hasattr(self,'gamepad_keys'):self.gamepad_keys.stop()
        self.keys.stop()
        if getattr(self.keys,'is_alive',lambda:True)():self.keys.join(timeout=2)
    def recording_changed(self,active):
        if self.closing:return
        if active:
            if self.hotkey_capture_active:return
            self.hotkey_capture_active=True
            self.close_session(restore=False);self.stop();self.stop_hotkeys()
        else:QTimer.singleShot(0,self.resume_hotkeys)
    def resume_hotkeys(self):
        if self.closing or self.safety_blocked or not self.hotkey_capture_active:return
        if any(field.recording for field in self.binding_fields()):return
        self.hotkey_capture_active=False
        self.restart_bindings()
    def restart_bindings(self):
        self.stop_hotkeys()
        self.keys=native.Hotkeys(self.hotkey.emit,self.native_error.emit,self.settings['hotkeys'],not self.external_mode())
        self.keys.set_escape(self.session_active or (self.running and getattr(self,'screen_snapshot',False)))
        self.start_hotkeys()
    def record_hotkey(self,action,chord,device='keyboard'):
        field=self.field_group(device)[action]
        old=self.settings['gamepad_bindings'][action] if device=='gamepad' else device_bindings(self.settings['hotkeys'][action],device)
        try:
            if device=='gamepad':
                updated=dict(self.settings['gamepad_bindings'],**{action:chord});gamepad.validate_bindings(updated)
            else:
                if len(native.hotkey_variants(chord))>4:raise ValueError(tr('До четырёх привязок на устройство и команду.'))
                other=device_bindings(self.settings['hotkeys'][action],'mouse' if device=='keyboard' else 'keyboard')
                combined='; '.join(value for value in (chord,other) if value)
                updated=dict(self.settings['hotkeys'],**{action:combined});native.validate_bindings(updated)
        except ValueError as error:
            field.set_binding(old) if device=='gamepad' else field.setText(old)
            self.message(str(error));return
        if device=='gamepad':
            self.settings['gamepad_bindings']=updated
            self.gamepad_enabled_pick.setChecked(True)
        else:self.settings['hotkeys']=updated
        self.store.save_settings(self.settings);self.refresh_key_labels()
        self.message(tr('Привязки сохранены: ')+(gamepad.display(chord,field.family) if device=='gamepad' else chord or tr('не назначено')))
    def clear_hotkey(self,action,device='keyboard'):
        field=self.field_group(device)[action];field.finish()
        self.record_hotkey(action,'',device)
        field.set_binding('') if device=='gamepad' else field.setText('')
        if not self.hotkey_capture_active:self.restart_bindings()
    def remove_hotkey(self,action,device='keyboard'):
        field=self.field_group(device)[action];field.finish()
        value=self.settings['gamepad_bindings'][action] if device=='gamepad' else device_bindings(self.settings['hotkeys'][action],device)
        variants=value.split('; ') if value else []
        if len(variants)<=1:self.clear_hotkey(action,device);return
        choice,ok=QInputDialog.getItem(self,tr('Удалить привязку'),tr('Кнопка или сочетание'),variants,0,False)
        if ok:
            variants.remove(choice);value='; '.join(variants)
            field.set_binding(value) if device=='gamepad' else field.setText(value)
            self.record_hotkey(action,value,device)
            if not self.hotkey_capture_active:self.restart_bindings()
