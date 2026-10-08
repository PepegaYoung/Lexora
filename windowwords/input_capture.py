"""Temporary input recorder. Hooks live in this process and store no input log."""
import ctypes
from ctypes import wintypes
import threading
from . import native
from .input_keys import ModifierState,MODIFIER_KEYS,chord_name

class MouseEvent(ctypes.Structure):
    _fields_=[('point',wintypes.POINT),('mouseData',wintypes.DWORD),('flags',wintypes.DWORD),
              ('time',wintypes.DWORD),('extra',ctypes.c_size_t)]

def mouse_key(message,data):
    if message not in (0x20B,0x20C):return None
    button=(data>>16)&0xFFFF
    return (0x05 if button==1 else 0x06 if button==2 else None)

def modifier_state():
    # Read once before installing the hook, then track the modifier events.
    return ModifierState(key for key in (0xA0,0xA1,0xA2,0xA3,0xA4,0xA5,0x5B,0x5C)
                         if native.user.GetAsyncKeyState(key)&0x8000)

class InputCapture(threading.Thread):
    def __init__(self,recorded,finished,failure):
        super().__init__(daemon=True)
        self.recorded,self.finished,self.failure=recorded,finished,failure
        self.stop_requested=threading.Event()
        self.ready=threading.Event()
        self.thread_id=None
        self.assigned=False
        self.held=None
    def stop(self):
        self.stop_requested.set()
        if self.thread_id:native.user.PostThreadMessageW(self.thread_id,0x12,0,0)
    def process(self,key,down,modifiers):
        if key in MODIFIER_KEYS:return False
        if self.held==key:
            if not down:self.held=None
            return True
        if not down or self.assigned:return False
        chord=chord_name(key,modifiers)
        if not chord:return False
        self.assigned=True;self.held=key
        self.recorded('Escape' if key==0x1B else chord)
        return True
    def run(self):
        if self.stop_requested.is_set():self.ready.set();return
        self.thread_id=ctypes.windll.kernel32.GetCurrentThreadId()
        msg=wintypes.MSG()
        native.user.PeekMessageW(ctypes.byref(msg),None,0,0,0)
        state=modifier_state()
        def complete():
            if self.assigned and self.held is None and not state.flags:
                self.finished();self.stop()
        @native.HOOKPROC
        def keyboard(code,message,data):
            if code>=0 and message in (0x100,0x101,0x104,0x105):
                key=ctypes.cast(data,ctypes.POINTER(native.KeyboardEvent)).contents.vkCode
                down=message in (0x100,0x104)
                state.update(key,down)
                consumed=self.process(key,down,state.flags)
                complete()
                if consumed:return 1
            return native.user.CallNextHookEx(None,code,message,data)
        @native.HOOKPROC
        def mouse(code,message,data):
            if code>=0 and message in (0x20B,0x20C):
                event=ctypes.cast(data,ctypes.POINTER(MouseEvent)).contents
                key=mouse_key(message,event.mouseData)
                if key is not None:
                    consumed=self.process(key,message==0x20B,state.flags)
                    complete()
                    if consumed:return 1
            return native.user.CallNextHookEx(None,code,message,data)
        self.callbacks=(keyboard,mouse)
        hooks=[native.user.SetWindowsHookExW(13,keyboard,None,0),
               native.user.SetWindowsHookExW(14,mouse,None,0)]
        self.ready.set()
        try:
            if not all(hooks):self.failure('Не удалось включить запись ввода. Попробуй другую клавишу.');return
            while not self.stop_requested.is_set() and native.user.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                native.user.TranslateMessage(ctypes.byref(msg));native.user.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hook in hooks:
                if hook:native.user.UnhookWindowsHookEx(hook)
