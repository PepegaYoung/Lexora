from .i18n import tr,trf
from PySide6.QtCore import Qt,Signal,QEvent,Slot
from PySide6.QtWidgets import QSpinBox,QAbstractSpinBox,QWidget,QVBoxLayout,QHBoxLayout,QSlider,QPushButton,QLabel,QLineEdit,QSizePolicy
from .input_capture import InputCapture
from .input_keys import key_name


class HotkeyEdit(QLineEdit):
    """Record physical Windows keys; append alternatives without manual text input."""
    recordingChanged=Signal(bool)
    recorded=Signal(str)
    invalid=Signal(str)
    nativeRecorded=Signal(int,str)
    nativeFinished=Signal(int)
    nativeFailed=Signal(int,str)
    def __init__(self,value,device='any'):
        super().__init__(value)
        self.setReadOnly(True)
        self.device=device
        self.setPlaceholderText(tr('Не назначено'))
        self.recording=False
        self.assigned=False
        self.capture=None
        self.capture_revision=0
        self.nativeRecorded.connect(self.on_native_recorded,Qt.ConnectionType.QueuedConnection)
        self.nativeFinished.connect(self.on_native_finished,Qt.ConnectionType.QueuedConnection)
        self.nativeFailed.connect(self.on_native_failed,Qt.ConnectionType.QueuedConnection)
        self.setToolTip(tr('Нажми поле и прожми клавишу или боковую кнопку мыши: F8, Alt+Z, Mouse4, Ctrl+Mouse5. «+» добавляет вариант. Escape отменяет запись.'))
        self.setAccessibleName(tr('Запись сочетания клавиш'))

    @Slot(int,str)
    def on_native_recorded(self,revision,chord):
        if revision==self.capture_revision:self.assign_chord(chord)

    @Slot(int)
    def on_native_finished(self,revision):
        if revision==self.capture_revision:self.finish()

    @Slot(int,str)
    def on_native_failed(self,revision,error):
        if revision==self.capture_revision:self.capture_failed(error)

    def begin(self,append=False):
        if self.recording:return
        if hasattr(self,'capture_guard') and not self.capture_guard():
            self.invalid.emit(tr('Запись клавиш остановлена защитой игр.'))
            return
        self.recording=True
        self.assigned=False
        self.append_mode=append
        self.previous=self.text()
        self.setProperty('recording',True)
        self.style().unpolish(self);self.style().polish(self)
        self.selectAll()
        self.recordingChanged.emit(True)
        self.capture_revision+=1
        revision=self.capture_revision
        self.capture=InputCapture(lambda chord:self.nativeRecorded.emit(revision,chord),
                                  lambda:self.nativeFinished.emit(revision),lambda error:self.nativeFailed.emit(revision,error),device=self.device)
        self.capture.start()

    def capture_failed(self,error):
        if self.recording:self.invalid.emit(error)

    def assign_chord(self,chord):
        if not self.recording or self.assigned:return
        if chord=='Escape':self.finish();self.clearFocus();return
        from .native import parse_hotkey
        from .input_keys import MOUSE_KEYS
        mouse=parse_hotkey(chord)[1] in MOUSE_KEYS
        if (self.device=='keyboard' and mouse) or (self.device=='mouse' and not mouse):
            self.invalid.emit(tr('Нажми кнопку ')+(tr('мыши') if self.device=='mouse' else tr('клавиатуры'))+'.')
            return
        if self.append_mode and self.previous:chord=self.previous+'; '+chord
        self.assigned=True
        self.setText(chord)
        self.recorded.emit(chord)

    def begin_add(self):
        self.finish()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.begin(append=True)

    def finish(self):
        if not self.recording:return
        self.recording=False
        self.capture_revision+=1
        if self.capture is not None:
            self.capture.stop()
            self.capture.join(timeout=1)
            self.capture=None
        self.setProperty('recording',False)
        self.style().unpolish(self);self.style().polish(self)
        self.deselect()
        self.recordingChanged.emit(False)

    def focusInEvent(self,event):
        super().focusInEvent(event)
        if event.reason() in (Qt.FocusReason.MouseFocusReason,Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason):self.begin()

    def mousePressEvent(self,event):
        if event.button() in (Qt.MouseButton.MiddleButton,Qt.MouseButton.BackButton,Qt.MouseButton.ForwardButton):
            if not self.recording:self.begin()
            modifiers=event.modifiers()
            parts=[label for flag,label in ((Qt.KeyboardModifier.ControlModifier,'Ctrl'),(Qt.KeyboardModifier.AltModifier,'Alt'),
                   (Qt.KeyboardModifier.ShiftModifier,'Shift'),(Qt.KeyboardModifier.MetaModifier,'Win')) if modifiers&flag]
            name={Qt.MouseButton.MiddleButton:'Mouse3',Qt.MouseButton.BackButton:'Mouse4',Qt.MouseButton.ForwardButton:'Mouse5'}[event.button()]
            self.assign_chord('+'.join(parts+[name]))
            event.accept();return
        super().mousePressEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:self.begin()

    def mouseReleaseEvent(self,event):
        if self.recording and self.assigned and event.button() in (Qt.MouseButton.MiddleButton,Qt.MouseButton.BackButton,Qt.MouseButton.ForwardButton):
            event.accept()
            if not event.modifiers():self.finish()
            return
        super().mouseReleaseEvent(event)

    def focusOutEvent(self,event):
        self.finish()
        super().focusOutEvent(event)

    def event(self,event):
        if event.type()==QEvent.Type.KeyPress and self.recording and event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):
            self.keyPressEvent(event)
            return True
        if event.type()==QEvent.Type.ShortcutOverride and self.recording:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self,event):
        if not self.recording:
            self.begin()
        event.accept()
        if event.isAutoRepeat() or self.assigned:return
        key=event.key()
        if key==Qt.Key.Key_Escape:
            self.finish()
            self.clearFocus()
            return
        if key in (Qt.Key.Key_Shift,Qt.Key.Key_Control,Qt.Key.Key_Alt,Qt.Key.Key_Meta):return
        modifiers=event.modifiers()
        parts=[label for flag,label in ((Qt.KeyboardModifier.ControlModifier,'Ctrl'),(Qt.KeyboardModifier.AltModifier,'Alt'),
               (Qt.KeyboardModifier.ShiftModifier,'Shift'),(Qt.KeyboardModifier.MetaModifier,'Win')) if modifiers&flag]
        vk=int(event.nativeVirtualKey())
        if key_name(vk):name=key_name(vk)
        elif 0x70<=vk<=0x87:name='F'+str(vk-0x6F)
        elif Qt.Key.Key_A<=key<=Qt.Key.Key_Z or Qt.Key.Key_0<=key<=Qt.Key.Key_9:name=chr(key)
        elif Qt.Key.Key_F1<=key<=Qt.Key.Key_F24:name='F'+str(key-Qt.Key.Key_F1+1)
        else:
            names={Qt.Key.Key_Space:'Space',Qt.Key.Key_Return:'Enter',Qt.Key.Key_Enter:'Enter',Qt.Key.Key_Tab:'Tab',
                   Qt.Key.Key_Backspace:'Backspace',Qt.Key.Key_Delete:'Delete',Qt.Key.Key_Insert:'Insert',Qt.Key.Key_Home:'Home',
                   Qt.Key.Key_End:'End',Qt.Key.Key_PageUp:'PageUp',Qt.Key.Key_PageDown:'PageDown',Qt.Key.Key_Left:'Left',
                   Qt.Key.Key_Right:'Right',Qt.Key.Key_Up:'Up',Qt.Key.Key_Down:'Down',Qt.Key.Key_Backtab:'Tab'}
            name=names.get(key)
            if not name:
                self.invalid.emit(tr('Эта клавиша не поддерживается. Попробуй другую клавишу или боковую кнопку мыши.'))
                return
        chord='+'.join([*parts,name])
        self.assign_chord(chord)

    def keyReleaseEvent(self,event):
        event.accept()
        if not self.recording or not self.assigned:return
        remaining=event.modifiers()
        flags={Qt.Key.Key_Shift:Qt.KeyboardModifier.ShiftModifier,Qt.Key.Key_Control:Qt.KeyboardModifier.ControlModifier,
               Qt.Key.Key_Alt:Qt.KeyboardModifier.AltModifier,Qt.Key.Key_Meta:Qt.KeyboardModifier.MetaModifier}
        if event.key() in flags:remaining&=~flags[event.key()]
        if not remaining&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.ShiftModifier|Qt.KeyboardModifier.MetaModifier):
            self.finish()



class AdjustSpinBox(QSpinBox):
    """Wheel over a value works without clicking or scrolling the whole page."""
    def __init__(self):
        super().__init__()
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.wheel_remainder = 0

    def wheelEvent(self,event):
        self.wheel_remainder += event.angleDelta().y()
        steps = int(self.wheel_remainder/120)
        if steps:
            self.wheel_remainder -= steps*120
            self.stepBy(steps)
        elif event.pixelDelta().y():self.stepBy(1 if event.pixelDelta().y()>0 else -1)
        event.accept()


class ClickSlider(QSlider):
    """Dragging/clicking changes the value; scrolling only scrolls the page."""
    def wheelEvent(self,event):
        event.ignore()


def adjustment(form,title,value,description):
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(4)
    row = QHBoxLayout()
    value.setMinimumWidth(90)
    value.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
    row.addWidget(value)
    slider = ClickSlider(Qt.Orientation.Horizontal)
    slider.setRange(value.minimum(),value.maximum())
    slider.setValue(value.value())
    slider.valueChanged.connect(value.setValue)
    value.valueChanged.connect(slider.setValue)
    row.addWidget(slider,2)
    layout.addLayout(row)
    value.setToolTip(description+tr(' Колесо мыши над числом меняет значение.'))
    for item in (value,slider):item.setProperty('helpText',description+tr(' Колесо мыши над числом меняет значение.'))
    form.addRow(title,panel)
    return slider
