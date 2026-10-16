from .i18n import tr,trf
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import QLineEdit
from .gamepad import RawControllerSource,ChordCycle,chord_name,display

class GamepadEdit(QLineEdit):
    recordingChanged=Signal(bool)
    recorded=Signal(str)
    invalid=Signal(str)
    def __init__(self,value):
        super().__init__()
        self.value=value;self.family='mixed';self.device=''
        self.recording=False;self.assigned=False;self.source=RawControllerSource();self.cycles={}
        self.setReadOnly(True);self.setPlaceholderText(tr('Не назначено'));self.set_binding(value)
        self.timer=QTimer(self);self.timer.setInterval(30);self.timer.timeout.connect(self.poll)
        self.expire=QTimer(self);self.expire.setSingleShot(True);self.expire.timeout.connect(self.timeout)
        self.setToolTip(tr('Нажми поле, зажми кнопку или сочетание на геймпаде и отпусти все кнопки. Escape отменяет запись.'))
    def set_binding(self,value):
        self.value=value
        self.setText(display(value,self.family))
    def begin(self,append=False):
        if self.recording:return
        if hasattr(self,'capture_guard') and not self.capture_guard():return
        self.previous=self.value;self.append_mode=append;self.assigned=False
        self.recording=True;self.cycles.clear()
        self.setProperty('recording',True);self.style().unpolish(self);self.style().polish(self)
        self.setText('');self.setPlaceholderText(tr('Нажми и отпусти кнопки геймпада…'))
        self.recordingChanged.emit(True)
        self.timer.start();self.expire.start(30000)
    def begin_add(self):self.finish();self.setFocus(Qt.FocusReason.OtherFocusReason);self.begin(True)
    def poll(self):
        if not self.recording:return
        try:frames=self.source.poll()
        except (OSError,RuntimeError,ImportError):
            self.invalid.emit(tr('Не удалось прочитать геймпад Windows.'));self.finish();return
        self.cycles={key:cycle for key,cycle in self.cycles.items() if key in frames}
        for key,buttons in frames.items():
            if self.device and key!=self.device:continue
            cycle=self.cycles.setdefault(key,ChordCycle())
            chord=cycle.feed(buttons)
            if chord:
                value=chord_name(chord)
                if self.append_mode and self.previous:value=self.previous+'; '+value
                self.assigned=True
                self.set_binding(value);self.recorded.emit(value);self.finish();return
            if buttons and cycle.armed:self.setText(display(chord_name(buttons),self.family)+tr(' · отпусти кнопки'))
    def finish(self):
        if not self.recording:return
        self.timer.stop();self.expire.stop();self.source.reset();self.cycles.clear();self.recording=False
        if not self.assigned:self.set_binding(self.previous)
        self.setPlaceholderText(tr('Не назначено'))
        self.setProperty('recording',False);self.style().unpolish(self);self.style().polish(self)
        self.recordingChanged.emit(False)
    def timeout(self):self.invalid.emit(tr('Запись отменена: кнопки не нажаты. Проверь подключение геймпада.'));self.finish()
    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:self.begin()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.finish();self.clearFocus()
        else:self.begin()
        event.accept()
    def focusOutEvent(self,event):self.finish();super().focusOutEvent(event)
