import ctypes
from ctypes import wintypes
import threading

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
    import os,ntpath
    handle=foreground()
    if not handle:return ''
    pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    if not pid.value or pid.value==os.getpid():return ''
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    process=kernel.OpenProcess(0x1000,False,pid.value)
    if not process:return ''
    try:
        size=wintypes.DWORD(32768)
        buffer=ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(size)):return ''
        return ntpath.basename(buffer.value).casefold()
    finally:kernel.CloseHandle(process)


def is_our_window(handle):
    import os
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    return pid.value==os.getpid()


def restore_foreground(handle):
    return bool(handle and user.IsWindow(handle) and user.SetForegroundWindow(handle))


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


def exclude_capture(widget):
    return bool(user.SetWindowDisplayAffinity(int(widget.winId()), 0x11))


KEY_NAMES = {'SPACE':0x20,'ENTER':0x0D,'TAB':0x09,'BACKSPACE':0x08,'DELETE':0x2E,
             'INSERT':0x2D,'HOME':0x24,'END':0x23,'PAGEUP':0x21,'PAGEDOWN':0x22,
             'LEFT':0x25,'UP':0x26,'RIGHT':0x27,'DOWN':0x28}


def hotkey_variants(text):
    if not isinstance(text,str):raise ValueError('Неверный формат привязок.')
    variants = [part.strip() for part in text.split(';')]
    if not 1<=len(variants)<=4 or any(not part for part in variants):
        raise ValueError('Нужно от одной до четырёх привязок для команды.')
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
        raise ValueError('Выбери букву, цифру, F1–F24 или клавишу навигации. Escape отменяет запись.')
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
        self.registered=set()
        self.bindings = bindings or {'study':'Alt+Q','region':'Alt+W','toggle':'Alt+T','hover':'Alt+H'}

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
        registered = self.registered
        def sync_single(enabled):
            for ident,(action,chord,(modifiers,key)) in mapping.items():
                wanted=enabled or bool(modifiers&0xF)
                if not wanted and ident in registered:
                    user.UnregisterHotKey(None,ident);registered.discard(ident)
                elif wanted and ident not in registered:
                    if user.RegisterHotKey(None,ident,modifiers,key):registered.add(ident)
                    else:self.failure('Горячая клавиша '+chord+' занята. Измени её в настройках или используй кнопку.')
        sync_single(self.single_enabled)
        @HOOKPROC
        def keyboard(code,message,data):
            if code>=0:
                key = ctypes.cast(data,ctypes.POINTER(KeyboardEvent)).contents.vkCode
                if self.escape_gate.process(key,message):return 1
            return user.CallNextHookEx(None,code,message,data)
        hook = user.SetWindowsHookExW(13,keyboard,None,0) if self.allow_escape_hook else None
        self.keyboard_callback = keyboard
        self.hook_installed = bool(hook)
        if self.allow_escape_hook and not hook:self.failure('Не удалось перехватить Escape. Используй кнопку возврата в карточке.')
        self.escape_gate.enabled = self.escape_requested and self.allow_escape_hook
        self.ready.set()
        try:
            while not self.stop_requested.is_set() and user.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                if msg.message==0x8001:
                    self.escape_gate.enabled = bool(msg.wParam) and self.allow_escape_hook
                elif msg.message==0x8002:
                    sync_single(bool(msg.wParam))
                elif msg.message==0x312 and msg.wParam in registered:
                    self.callback(mapping[msg.wParam][0])
                else:
                    user.TranslateMessage(ctypes.byref(msg))
                    user.DispatchMessageW(ctypes.byref(msg))
        finally:
            if hook:user.UnhookWindowsHookEx(hook)
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
