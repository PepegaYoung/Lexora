"""Read-only Windows.Gaming.Input; no emulation, hooks, vibration or game handles."""
from .i18n import tr,trf
import re,time
from dataclasses import dataclass

ACTIONS=('study','region','toggle','screen')
STANDARD=('South','East','West','North','LB','RB','LT','RT','L3','R3','View','Menu','Guide','Touchpad',
          'Up','Right','Down','Left','Paddle1','Paddle2','Paddle3','Paddle4')
LABELS={
    'CROSS':'South','CIRCLE':'East','SQUARE':'West','TRIANGLE':'North',
    'XBOX_A':'South','XBOX_B':'East','XBOX_X':'West','XBOX_Y':'North',
    'LETTER_A':'South','LETTER_B':'East','LETTER_X':'West','LETTER_Y':'North',
    'LEFT_BUMPER':'LB','LEFT1':'LB','RIGHT_BUMPER':'RB','RIGHT1':'RB',
    'LEFT_TRIGGER':'LT','LEFT2':'LT','RIGHT_TRIGGER':'RT','RIGHT2':'RT',
    'LEFT_STICK_BUTTON':'L3','LEFT3':'L3','RIGHT_STICK_BUTTON':'R3','RIGHT3':'R3',
    'OPTIONS':'Menu','START':'Menu','MENU':'Menu','SHARE':'View','SELECT':'View','VIEW':'View','BACK':'View',
    'MODE':'Guide','UP':'Up','RIGHT':'Right','DOWN':'Down','LEFT':'Left',
}
LABELS.update({'XBOX_'+key:value for key,value in tuple(LABELS.items()) if not key.startswith('XBOX_')})
LABELS.update({'PADDLE'+str(i):'Paddle'+str(i) for i in range(1,5)})
LABELS.update({'XBOX_PADDLE'+str(i):'Paddle'+str(i) for i in range(1,5)})
# Standard HID button order for these Sony devices; Windows labels take precedence.
SONY_PRODUCTS={0x05C4,0x09CC,0x0CE6,0x0DF2}
SONY_BUTTONS=('West','South','East','North','LB','RB','LT','RT','View','Menu','L3','R3','Guide','Touchpad')
DIRECTIONS={1:('Up',),2:('Up','Right'),3:('Right',),4:('Down','Right'),5:('Down',),
            6:('Down','Left'),7:('Left',),8:('Up','Left')}

def button_token(value):
    if value not in STANDARD and not re.fullmatch(r'Button(?:[1-9]|[1-9]\d|1[0-2]\d|13[0-6])|Switch[1-8](?:Up|Right|Down|Left)',value):
        raise ValueError(tr('Неизвестная кнопка геймпада.'))
    return value

def parse_chord(value):
    if not isinstance(value,str):raise ValueError(tr('Неверная привязка геймпада.'))
    parts=[button_token(part.strip()) for part in value.split('+')]
    if not 1<=len(parts)<=6 or len(set(parts))!=len(parts):raise ValueError(tr('Выбери от одной до шести разных кнопок геймпада.'))
    return frozenset(parts)

def chord_name(buttons):
    order={name:i for i,name in enumerate(STANDARD)}
    return '+'.join(sorted(buttons,key=lambda name:(order.get(name,100),name)))

def variants(value):
    if not isinstance(value,str):raise ValueError(tr('Неверная привязка геймпада.'))
    if not value:return []
    parts=value.split(';')
    if len(parts)>4:raise ValueError(tr('До четырёх привязок на команду.'))
    return [parse_chord(part) for part in parts]

def validate_bindings(bindings):
    if not isinstance(bindings,dict) or set(bindings)!=set(ACTIONS):raise ValueError(tr('Неверные команды геймпада.'))
    seen=set()
    for value in bindings.values():
        for chord in variants(value):
            if chord in seen:raise ValueError(tr('Эти кнопки геймпада уже назначены.'))
            seen.add(chord)

def display(value,family='mixed'):
    ps={'South':'×','East':'○','West':'□','North':'△','LB':'L1','RB':'R1','LT':'L2','RT':'R2',
        'View':'Share / Create','Menu':'Options','Guide':'PS'}
    xbox={'South':'A','East':'B','West':'X','North':'Y','View':'View','Menu':'Menu','Guide':'Xbox'}
    common={'Up':'↑','Right':'→','Down':'↓','Left':'←','Touchpad':tr('Тачпад')}
    def label(name):
        if name in common:return common[name]
        if name.startswith('Button'):return tr('Кнопка ')+name[6:]
        if family=='playstation':return ps.get(name,name)
        if family=='xbox':return xbox.get(name,name)
        a,b=ps.get(name,name),xbox.get(name,name)
        return a if a==b else a+' / '+b
    return '; '.join(' + '.join(label(name) for name in chord_name(chord).split('+')) for chord in variants(value))

class ChordCycle:
    """One command on release; ignore held buttons at startup/reconnect."""
    def __init__(self):self.armed=False;self.peak=frozenset();self.ambiguous=False
    def feed(self,buttons):
        buttons=frozenset(buttons)
        if not self.armed:
            if not buttons:self.armed=True
            return None
        if buttons:
            if len(buttons)>len(self.peak):self.peak=buttons;self.ambiguous=False
            elif len(buttons)==len(self.peak) and buttons!=self.peak:self.ambiguous=True
            return None
        result=self.peak if self.peak and not self.ambiguous else None
        self.peak=frozenset();self.ambiguous=False
        return result

@dataclass(frozen=True)
class Controller:
    key:str
    name:str
    family:str

class RawControllerSource:
    def __init__(self):self.devices={};self.next_scan=0
    def reset(self):self.devices.clear();self.next_scan=0
    def discover(self,force=False):
        if not force and time.monotonic()<self.next_scan:return [row[0] for row in self.devices.values()]
        # Lazy imports: do not initialize controller APIs while protected games run.
        from winrt.windows.gaming.input import RawGameController,Gamepad
        from winrt.system import Array
        devices={}
        for raw in RawGameController.raw_game_controllers:
            key=raw.non_roamable_id
            if key in self.devices:devices[key]=self.devices[key];continue
            try:pad=Gamepad.from_game_controller(raw)
            except (OSError,RuntimeError):pad=None
            family='playstation' if raw.hardware_vendor_id==0x054C else 'xbox' if pad is not None else 'generic'
            info=Controller(key,raw.display_name or tr('Геймпад'),family)
            if not (0<=raw.button_count<=136 and 0<=raw.switch_count<=8 and 0<=raw.axis_count<=64):continue
            labels=[]
            for i in range(raw.button_count):
                name=raw.get_button_label(i).name
                fallback=SONY_BUTTONS[i] if raw.hardware_vendor_id==0x054C and raw.hardware_product_id in SONY_PRODUCTS and i<len(SONY_BUTTONS) else 'Button'+str(i+1)
                labels.append(LABELS.get(name,fallback))
            devices[key]=(info,raw,pad,labels,Array('?',raw.button_count),Array('i',raw.switch_count),Array('d',raw.axis_count))
        self.devices=devices;self.next_scan=time.monotonic()+1
        return [row[0] for row in devices.values()]
    def poll(self):
        self.discover()
        frames={}
        for key,(info,raw,pad,labels,buttons,switches,axes) in tuple(self.devices.items()):
            try:
                if pad is not None and info.family!='playstation':
                    from winrt.windows.gaming.input import GamepadButtons as B
                    state=pad.get_current_reading()
                    mapping={'A':'South','B':'East','X':'West','Y':'North','LEFT_SHOULDER':'LB','RIGHT_SHOULDER':'RB',
                             'LEFT_THUMBSTICK':'L3','RIGHT_THUMBSTICK':'R3','VIEW':'View','MENU':'Menu',
                             'D_PAD_UP':'Up','D_PAD_DOWN':'Down','D_PAD_LEFT':'Left','D_PAD_RIGHT':'Right',
                             **{'PADDLE'+str(i):'Paddle'+str(i) for i in range(1,5)}}
                    pressed={token for name,token in mapping.items() if state.buttons&getattr(B,name)}
                    if state.left_trigger>.65:pressed.add('LT')
                    if state.right_trigger>.65:pressed.add('RT')
                else:
                    raw.get_current_reading(buttons,switches,axes)
                    pressed={labels[i] for i,down in enumerate(buttons) if down}
                    for i,position in enumerate(switches):
                        pressed.update(direction if i==0 else f'Switch{i+1}{direction}' for direction in DIRECTIONS.get(int(position),()))
                frames[key]=frozenset(pressed)
            except (OSError,RuntimeError):
                self.devices.pop(key,None);self.next_scan=0
        return frames
