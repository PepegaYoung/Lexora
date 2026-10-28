"""Physical Windows key names shared by the recorder and global shortcuts."""
KEY_NAMES = {
    'SPACE':0x20, 'ENTER':0x0D, 'TAB':0x09, 'BACKSPACE':0x08, 'DELETE':0x2E,
    'INSERT':0x2D, 'HOME':0x24, 'END':0x23, 'PAGEUP':0x21, 'PAGEDOWN':0x22,
    'LEFT':0x25, 'UP':0x26, 'RIGHT':0x27, 'DOWN':0x28,
    'CAPSLOCK':0x14, 'NUMLOCK':0x90, 'SCROLLLOCK':0x91, 'PAUSE':0x13,
    'PRINTSCREEN':0x2C, 'NUMMULTIPLY':0x6A, 'NUMPLUS':0x6B, 'NUMMINUS':0x6D,
    'NUMDECIMAL':0x6E, 'NUMDIVIDE':0x6F, 'SEMICOLON':0xBA, 'PLUS':0xBB,
    'COMMA':0xBC, 'MINUS':0xBD, 'PERIOD':0xBE, 'SLASH':0xBF, 'BACKTICK':0xC0,
    'BRACKETLEFT':0xDB, 'BACKSLASH':0xDC, 'BRACKETRIGHT':0xDD, 'QUOTE':0xDE,
    'MOUSE3':0x04, 'MOUSE4':0x05, 'MOUSE5':0x06,
    **{'NUM'+str(i):0x60+i for i in range(10)},
}
DISPLAY_NAMES = {name:value for name,value in (
    ('Space',0x20),('Enter',0x0D),('Tab',0x09),('Backspace',0x08),('Delete',0x2E),
    ('Insert',0x2D),('Home',0x24),('End',0x23),('PageUp',0x21),('PageDown',0x22),
    ('Left',0x25),('Up',0x26),('Right',0x27),('Down',0x28),('CapsLock',0x14),
    ('NumLock',0x90),('ScrollLock',0x91),('Pause',0x13),('PrintScreen',0x2C),
    ('NumMultiply',0x6A),('NumPlus',0x6B),('NumMinus',0x6D),('NumDecimal',0x6E),
    ('NumDivide',0x6F),('Semicolon',0xBA),('Plus',0xBB),('Comma',0xBC),('Minus',0xBD),
    ('Period',0xBE),('Slash',0xBF),('Backtick',0xC0),('BracketLeft',0xDB),
    ('Backslash',0xDC),('BracketRight',0xDD),('Quote',0xDE),('Mouse3',0x04),('Mouse4',0x05),('Mouse5',0x06),
)}
VK_NAMES = {value:name for name,value in DISPLAY_NAMES.items()}
VK_NAMES.update({0x60+i:'Num'+str(i) for i in range(10)})
MODIFIER_KEYS = {0x10:4,0xA0:4,0xA1:4,0x11:2,0xA2:2,0xA3:2,
                 0x12:1,0xA4:1,0xA5:1,0x5B:8,0x5C:8}
MOUSE_KEYS={0x04,0x05,0x06}

def key_name(vk):
    if 0x30<=vk<=0x39 or 0x41<=vk<=0x5A:return chr(vk)
    if 0x70<=vk<=0x87:return 'F'+str(vk-0x6F)
    return VK_NAMES.get(vk)

def chord_name(vk,modifiers):
    name='Escape' if vk==0x1B else key_name(vk)
    if not name:return None
    return '+'.join([label for flag,label in ((2,'Ctrl'),(1,'Alt'),(4,'Shift'),(8,'Win'))
                     if modifiers&flag]+[name])

class ModifierState:
    def __init__(self,pressed=()):self.pressed=set(pressed)
    def update(self,key,down):
        if key not in MODIFIER_KEYS:return
        if down:self.pressed.add(key)
        else:
            self.pressed.discard(key)
            # Remove a generic seed when Windows reports the physical side.
            flag=MODIFIER_KEYS[key]
            for generic in (0x10,0x11,0x12):
                if MODIFIER_KEYS[generic]==flag:self.pressed.discard(generic)
    @property
    def flags(self):
        result=0
        for key in self.pressed:result|=MODIFIER_KEYS.get(key,0)
        return result

class ShortcutGate:
    """Only consume configured keys, including their matching release."""
    def __init__(self,callback,bindings=None):
        self.callback=callback
        self.bindings=bindings if bindings is not None else {}
        self.held=set()
        self.single_enabled=True
        self.mouse_single_enabled=False
    def process(self,key,down,modifiers):
        if key in self.held:
            if not down:self.held.discard(key)
            return True
        if not down:return False
        action=self.bindings.get((modifiers&0xF,key))
        if action is None or (not modifiers and not self.single_enabled and not (key in MOUSE_KEYS and self.mouse_single_enabled)):return False
        self.held.add(key)
        self.callback(action)
        return True
