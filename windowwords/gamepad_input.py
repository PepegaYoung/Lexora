from PySide6.QtCore import QObject,QTimer,Signal
import time
from .gamepad import RawControllerSource,ChordCycle,variants,validate_bindings

class GamepadHotkeys(QObject):
    action=Signal(str)
    failed=Signal(str)
    def __init__(self,parent,allowed):
        super().__init__(parent)
        self.allowed=allowed
        self.source=RawControllerSource()
        self.cycles={};self.mapping={};self.device='';self.last_actions={}
        self.timer=QTimer(self);self.timer.setInterval(30);self.timer.timeout.connect(self.poll)
    def start(self,bindings,enabled,device=''):
        self.stop()
        validate_bindings(bindings)
        self.mapping={chord:action for action,value in bindings.items() for chord in variants(value)}
        self.device=device
        if enabled and self.mapping and self.allowed():self.timer.start()
    def stop(self):
        self.timer.stop();self.cycles.clear();self.last_actions.clear();self.source.reset()
    def poll(self):
        if not self.timer.isActive():return
        if not self.allowed():self.stop();return
        try:frames=self.source.poll()
        except (OSError,RuntimeError,ImportError):
            self.stop();self.failed.emit('Не удалось прочитать геймпады Windows. Проверь подключение и обнови список.');return
        self.cycles={key:cycle for key,cycle in self.cycles.items() if key in frames}
        for key,buttons in frames.items():
            if self.device and self.device!=key:continue
            chord=self.cycles.setdefault(key,ChordCycle()).feed(buttons)
            action=self.mapping.get(chord)
            if action is not None:
                # A physical pad and its virtual copy can release on adjacent polls.
                now=time.monotonic()
                if now-self.last_actions.get(action,float('-inf'))<.15:continue
                self.last_actions[action]=now
                self.action.emit(action)
                if not self.timer.isActive():return
