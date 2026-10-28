from .i18n import tr,trf
import ctypes
from ctypes import wintypes
import threading
from .input_keys import KEY_NAMES,ShortcutGate,ModifierState

user = ctypes.windll.user32
user.SetWindowPos.argtypes = [wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
user.SetWindowDisplayAffinity.argtypes = [wintypes.HWND,wintypes.DWORD]
user.PostThreadMessageW.argtypes = [wintypes.DWORD,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.GetForegroundWindow.restype = wintypes.HWND
user.SetForegroundWindow.argtypes = [wintypes.HWND]
user.IsWindow.argtypes = [wintypes.HWND]
user.GetWindowThreadProcessId.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
user.SetWindowsHookExW.argtypes = [ctypes.c_int,HOOKPROC,wintypes.HINSTANCE,wintypes.DWORD]
user.SetWindowsHookExW.restype = wintypes.HANDLE
user.CallNextHookEx.argtypes = [wintypes.HANDLE,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM]
user.CallNextHookEx.restype = ctypes.c_ssize_t
user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]


class KeyboardEvent(ctypes.Structure):
    _fields_ = [('vkCode',wintypes.DWORD),('scanCode',wintypes.DWORD),('flags',wintypes.DWORD),
                ('time',wintypes.DWORD),('extra',ctypes.c_size_t)]


class EscapeGate:
    """Consume the full Escape press, including release after the session closes."""
    def __init__(self,callback):
        self.callback,self.enabled,self.held = callback,False,False

    def process(self,key,message):
        if key!=0x1B or message not in (0x100,0x101,0x104,0x105):return False
        down = message in (0x100,0x104)
        if self.held:
            if not down:self.held = False
            return True
        if not self.enabled:return False
        if down:
            self.held = True
            self.callback('escape')
        return True


def foreground():
    return user.GetForegroundWindow()


def foreground_executable():
    """Read only the executable name, never process memory or window text."""
    import os
    handle=foreground()
    if not handle:return ''
    pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    if not pid.value or pid.value==os.getpid():return ''
    from .processes import process_snapshot
    try:
        return process_snapshot().get(pid.value,'')
    except OSError:return ''


def is_our_window(handle):
    import os
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    return pid.value==os.getpid()


def restore_foreground(handle):
    return bool(handle and user.IsWindow(handle) and (foreground()==handle or user.SetForegroundWindow(handle)))


def refresh_window_cursor(handle):
    # Ask the game to choose its cursor, without changing visibility counters.
    if handle and foreground()==handle:
        user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        user.PostMessageW(handle,0x20,handle,1|(0x200<<16))


def client_bounds(handle):
    """Read public window geometry, excluding its title bar and borders."""
    from .core import Box
    user.IsIconic.argtypes=[wintypes.HWND]
    if not handle or not user.IsWindow(handle) or user.IsIconic(handle):return None
    rect=wintypes.RECT();point=wintypes.POINT()
    user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
    if not user.GetClientRect(handle,ctypes.byref(rect)) or not user.ClientToScreen(handle,ctypes.byref(point)):return None
    return Box(point.x,point.y,rect.right-rect.left,rect.bottom-rect.top)


def transition_keys_held():
    # Let the game receive Alt/Ctrl/Shift releases before changing foreground.
    return any(user.GetAsyncKeyState(key)&0x8000 for key in (0x10,0x11,0x12,0x5B,0x5C,0x1B))


def dpi_aware():
    try:
        user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        user.SetProcessDPIAware()


class MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),
                ('rcWork',wintypes.RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]


def monitors():
    items = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,ctypes.c_void_p,wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    @callback_type
    def visit(handle, dc, rect, data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        user.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MonitorInfo)]
        user.GetMonitorInfoW(handle, ctypes.byref(info))
        r = info.rcMonitor
        items.append({'name':info.device,'x':r.left,'y':r.top,'w':r.right-r.left,'h':r.bottom-r.top,'primary':bool(info.flags&1)})
        return True
    user.EnumDisplayMonitors(None,None,visit,0)
    return items


def cursor():
    point = wintypes.POINT()
    user.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def place(widget, box, activate=False,topmost=True):
    user.SetWindowPos(int(widget.winId()), wintypes.HWND(-1 if topmost else -2),round(box.x),round(box.y),
                      max(1,round(box.w)),max(1,round(box.h)),0 if activate else 0x10)


def set_owner(widget, owner=None):
    # Qt's transient parent alone does not establish a Win32 owner for Window
    # widgets. Ownership keeps the card above its snapshot without WS_EX_TOPMOST.
    setter=user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else user.SetWindowLongW
    setter.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
    setter.restype=ctypes.c_ssize_t
    setter(int(widget.winId()),-8,int(owner.winId()) if owner else 0)


def raise_window(widget,activate=False):
    user.SetWindowPos(int(widget.winId()),wintypes.HWND(0),0,0,0,0,0x3 | (0 if activate else 0x10))
    if activate:user.SetForegroundWindow(int(widget.winId()))


def window_above(widget,target):
    """Compare public top-level Z order; never inspect the game's process."""
    user.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT]
    user.GetWindow.restype=wintypes.HWND
    own=int(widget.winId());current=target
    # A bounded traversal also handles a window disappearing between calls.
    for _ in range(256):
        current=user.GetWindow(current,3) if current else None # GW_HWNDPREV
        if not current:return False
        if current==own:return True
    return False


def promote_overlay(widget):
    # Reassert TOPMOST after the game raises itself on Alt+Tab/activation.
    # NOACTIVATE preserves focus and input in the game; only our HWND changes.
    return bool(user.SetWindowPos(int(widget.winId()),wintypes.HWND(-1),0,0,0,0,0x213))


def exclude_capture(widget):
    return bool(user.SetWindowDisplayAffinity(int(widget.winId()),0 if widget.property('captureVisible') else 0x11))


def hotkey_variants(text):
    if not isinstance(text,str):raise ValueError('Неверный формат привязок.')
    if not text:return []
    variants = [part.strip() for part in text.split(';')]
    if not 1<=len(variants)<=8 or any(not part for part in variants):
        raise ValueError('До восьми привязок клавиатуры и мыши на команду.')
    return variants


def parse_hotkeys(text):
    return [parse_hotkey(chord) for chord in hotkey_variants(text)]


def validate_bindings(bindings):
    seen = set()
    for text in bindings.values():
        for parsed in parse_hotkeys(text):
            if parsed in seen:raise ValueError('Эта клавиша или сочетание уже используется.')
            seen.add(parsed)


def hotkey_label(text):
    variants = hotkey_variants(text)
    if not variants:return tr('Не назначено')
    return variants[0]+(f' (+{len(variants)-1})' if len(variants)>1 else '')


def parse_hotkey(text):
    if not isinstance(text,str):raise ValueError('Неверный формат клавиши.')
    parts = text.upper().replace(' ','').split('+')
    modifiers = {'ALT':1,'CTRL':2,'SHIFT':4,'WIN':8}
    if any(p not in modifiers for p in parts[:-1]) or len(set(parts[:-1]))!=len(parts[:-1]):
        raise ValueError('Используй одну клавишу или сочетание, например F8 или Shift+Q.')
    key = parts[-1]
    if len(key)==1 and key.isascii() and key.isalnum():
        value = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1<=int(key[1:])<=24:
        value = 0x6F+int(key[1:])
    elif key in KEY_NAMES:value=KEY_NAMES[key]
    else:
        raise ValueError('Выбери клавишу или Mouse4 / Mouse5. Escape отменяет запись.')
    flags = 0x4000
    for modifier in parts[:-1]:
        flags |= modifiers[modifier]
    return flags,value


class Hotkeys(threading.Thread):
    def __init__(self, callback, failure, bindings=None,allow_escape_hook=True):
        super().__init__(daemon=True)
        self.callback, self.failure = callback, failure
        self.thread_id = None
        self.escape_requested = False
        self.escape_gate = EscapeGate(callback)
        self.ready = threading.Event()
        self.stop_requested=threading.Event()
        self.hook_installed = False
        self.allow_escape_hook=allow_escape_hook
        self.single_enabled=True
        self.mouse_single_enabled=False
        self.registered=set()
        self.bindings = bindings or {'study':'Alt+Q','region':'Alt+W','toggle':'Alt+T','screen':'Alt+V'}

    def run(self):
        if self.stop_requested.is_set():
            self.ready.set()
            return
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user.PeekMessageW(ctypes.byref(msg),None,0,0,0)
        try:
            validate_bindings(self.bindings)
            entries=[(action,chord,parse_hotkey(chord)) for action,text in self.bindings.items() for chord in hotkey_variants(text)]
        except ValueError as error:
            self.failure(str(error));self.ready.set();return
        mapping = {i+1:entry for i,entry in enumerate(entries)}
        mouse_entries=[(modifiers&0xF,key,ident) for ident,(_,_,(modifiers,key)) in mapping.items() if key in (0x04,0x05,0x06)]
        mouse_helper=None
        if mouse_entries:
            from .mouse_helper import MouseHelper
            mouse_helper=MouseHelper(mouse_entries,self.thread_id,user.PostThreadMessageW,self.failure,self.single_enabled,self.mouse_single_enabled)
            mouse_helper.start()
        registered = self.registered
        fallback={}
        gate=ShortcutGate(self.callback,fallback)
        gate.mouse_single_enabled=self.mouse_single_enabled
        state=ModifierState()
        warned=set()
        def sync_single(enabled):
            gate.single_enabled=enabled
            for ident,(action,chord,(modifiers,key)) in mapping.items():
                if key in (0x04,0x05,0x06):
                    continue
                wanted=enabled or bool(modifiers&0xF)
                if not wanted and ident in registered:
                    user.UnregisterHotKey(None,ident);registered.discard(ident)
                if not wanted:
                    fallback.pop((modifiers&0xF,key),None)
                elif ident not in registered and (modifiers&0xF,key) not in fallback:
                    if user.RegisterHotKey(None,ident,modifiers,key):registered.add(ident)
                    else:
                        fallback[(modifiers&0xF,key)]=action
                        if chord not in warned:
                            warned.add(chord)
                            self.failure(chord+' занята другой программой. Lexora использует перехват этого сочетания; если открывается чужой оверлей, отключи его привязку.')
        @HOOKPROC
        def keyboard(code,message,data):
            if code>=0 and message in (0x100,0x101,0x104,0x105):
                key = ctypes.cast(data,ctypes.POINTER(KeyboardEvent)).contents.vkCode
                down=message in (0x100,0x104)
                state.update(key,down)
                if self.escape_gate.process(key,message):return 1
                if gate.process(key,down,state.flags):return 1
            return user.CallNextHookEx(None,code,message,data)
        from .input_capture import modifier_state
        hooks={}
        def sync_hooks():
            # Keyboard modifiers are also needed for Ctrl/Alt + Mouse4/Mouse5.
            need_keyboard=self.allow_escape_hook or bool(fallback)
            for kind,needed,callback in ((13,need_keyboard,keyboard),):
                if needed and kind not in hooks:
                    if kind==13:state.pressed=modifier_state().pressed
                    handle=user.SetWindowsHookExW(kind,callback,None,0)
                    if handle:hooks[kind]=handle
                    else:self.failure('Не удалось включить обработчик '+(tr('клавиатуры') if kind==13 else tr('мыши'))+'. Выбери другую привязку.')
            self.hook_installed=13 in hooks
        self.keyboard_callback = keyboard
        sync_single(self.single_enabled)
        sync_hooks()
        self.escape_gate.enabled = self.escape_requested and self.allow_escape_hook
        self.ready.set()
        try:
            while not self.stop_requested.is_set() and user.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                if msg.message==0x8001:
                    self.escape_gate.enabled = bool(msg.wParam) and self.allow_escape_hook
                elif msg.message==0x8002:
                    sync_single(bool(msg.wParam))
                    if mouse_helper:mouse_helper.set_state(singles=bool(msg.wParam))
                    sync_hooks()
                elif msg.message==0x8003:
                    gate.mouse_single_enabled=bool(msg.wParam)
                    if mouse_helper:mouse_helper.set_state(card=bool(msg.wParam))
                elif msg.message==0x8004 and msg.wParam in mapping and mapping[msg.wParam][2][1] in (0x04,0x05,0x06):
                    self.callback(mapping[msg.wParam][0])
                elif msg.message==0x312 and msg.wParam in registered:
                    self.callback(mapping[msg.wParam][0])
                else:
                    user.TranslateMessage(ctypes.byref(msg))
                    user.DispatchMessageW(ctypes.byref(msg))
        finally:
            if mouse_helper:mouse_helper.stop()
            for hook in hooks.values():user.UnhookWindowsHookEx(hook)
            for ident in registered:
                user.UnregisterHotKey(None,ident)
            registered.clear()

    def stop(self):
        self.stop_requested.set()
        if self.thread_id:
            user.PostThreadMessageW(self.thread_id,0x12,0,0)

    def set_escape(self,enabled):
        enabled=bool(enabled and self.allow_escape_hook)
        self.escape_requested = enabled
        self.escape_gate.enabled = enabled
        if self.thread_id:
            user.PostThreadMessageW(self.thread_id,0x8001,int(enabled),0)

    def set_single_enabled(self,enabled):
        enabled=bool(enabled)
        if self.single_enabled==enabled:return
        self.single_enabled=enabled
        if self.thread_id:
            user.PostThreadMessageW(self.thread_id,0x8002,int(enabled),0)

    def set_mouse_single_enabled(self,enabled):
        self.mouse_single_enabled=bool(enabled)
        if self.thread_id:user.PostThreadMessageW(self.thread_id,0x8003,int(self.mouse_single_enabled),0)
