"""Shared palettes for the application, icons and translucent word card."""
import re

THEMES={
 'dark':dict(label='Фиолетовая',light=False,bg='#131526',side='#101122',field='#18192e',raised='#202039',text='#ede9f7',bright='#faf8ff',muted='#b3a8cf',secondary='#c6b5e8',line='#51436c',group='#352e50',hover='#44305e',selected='#482368',pill='#352044',tab='#242239',accent='#cc91ff',primary='#8b35cb',focus='#dba8ff',active='#aa64dc',disabled='#222137',dim='#807493'),
 'light':dict(label='Светлая',light=True,bg='#f3f6fb',side='#f3f6fb',field='#ffffff',raised='#ffffff',text='#17283b',bright='#142239',muted='#53647b',secondary='#40546e',line='#b9c9de',group='#d1dce9',hover='#d2e1f3',selected='#d7ece8',pill='#dbeee9',tab='#e0e9f4',accent='#247d74',primary='#247d74',focus='#075a84',active='#247d74',disabled='#e7edf6',dim='#647487'),
 'graphite':dict(label='Графит',light=False,bg='#1b1c20',side='#15161a',field='#141519',raised='#25262c',text='#e9e8ee',bright='#f7f5fc',muted='#b0aebc',secondary='#bcb9c9',line='#44424e',group='#35333f',hover='#383442',selected='#363040',pill='#332c40',tab='#302d38',accent='#c6b9ef',primary='#66528f',focus='#c6b9ef',active='#947ebd',disabled='#29282f',dim='#85818e'),
 'ocean':dict(label='Океан',light=False,bg='#111c2a',side='#0c1521',field='#0b1522',raised='#19293c',text='#e2edf9',bright='#f4f9ff',muted='#a2b6cf',secondary='#afc2d9',line='#344e6b',group='#263d57',hover='#25476b',selected='#223e58',pill='#1f3b53',tab='#20374f',accent='#8fc9f5',primary='#2c6ba1',focus='#9ad4ff',active='#528fbe',disabled='#1c2b3c',dim='#768aa3'),
 'forest':dict(label='Лес',light=False,bg='#142018',side='#0e1912',field='#0c1710',raised='#1d2d22',text='#e5efe6',bright='#f5fbf5',muted='#a4b8a7',secondary='#b2c6b5',line='#3b5343',group='#2b4133',hover='#304f3a',selected='#254331',pill='#24412e',tab='#233b2b',accent='#95d8ac',primary='#2f7352',focus='#a6e2b9',active='#529c70',disabled='#1c2c21',dim='#7a9080'),
 'warm':dict(label='Тёплая',light=True,bg='#f8f3e8',side='#f1e9dd',field='#fffaf2',raised='#fffaf2',text='#3e342b',bright='#30271f',muted='#75685a',secondary='#685847',line='#ccbaa2',group='#ded0bd',hover='#eee0cc',selected='#ede0cf',pill='#ecddc7',tab='#eee3d3',accent='#795536',primary='#87633f',focus='#90693d',active='#a17a4e',disabled='#e9e0d3',dim='#877a6b'),
}

COLOR_ROLES={
 '#111a28':'bg','#101821':'bg','#0c1420':'side','#0b1320':'field','#14212e':'raised',
 '#e4ebf5':'text','#f6fbff':'bright','#9cabc0':'muted','#a8b8cd':'secondary',
 '#33475e':'line','#34506c':'line','#26364b':'group','#2e4b69':'hover',
 '#203b3d':'selected','#1d373b':'pill','#20334a':'tab','#7de0cc':'accent',
 '#247d74':'primary','#76d7ff':'focus','#399c8f':'active','#162234':'disabled','#647487':'dim',
}

def mix(first,second,amount):
 values=[round(int(first[i:i+2],16)*(1-amount)+int(second[i:i+2],16)*amount) for i in (1,3,5)]
 return '#'+''.join(f'{value:02x}' for value in values)


def contrast_ratio(first,second):
 def luminance(color):
  channels=[int(color[i:i+2],16)/255 for i in (1,3,5)]
  linear=[value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4 for value in channels]
  return sum(value*weight for value,weight in zip(linear,(.2126,.7152,.0722)))
 first,second=sorted((luminance(first),luminance(second)))
 return (second+.05)/(first+.05)


def reference_palette(label,bg,accent,text,light=False,gradient=None,primary=None):
 # Keep the reference's main colours; derive readable states for actual controls.
 primary=primary or accent
 while contrast_ratio(primary,'#ffffff')<4.5:primary=mix(primary,'#000000',.08)
 gradient=gradient or (bg,mix(bg,accent,.08))
 selected=mix(bg,accent,.27);pill=mix(bg,accent,.18);tab=mix(bg,accent,.13)
 muted=mix(text,bg,.20)
 while min(contrast_ratio(muted,color) for color in gradient)<4.5:muted=mix(muted,text,.1)
 while min(contrast_ratio(accent,color) for color in (*gradient,selected,pill,tab))<4.5:
  accent=mix(accent,'#000000' if light else '#ffffff',.08)
 return dict(label=label,light=light,bg=bg,side=mix(bg,'#ffffff' if light else '#000000',.12),
   field=mix(bg,'#ffffff' if light else '#000000',.08),raised=mix(bg,text,.06),text=text,
   bright=mix(text,'#000000' if light else '#ffffff',.18),muted=muted,secondary=mix(text,bg,.12),
   line=mix(bg,text,.25),group=mix(bg,text,.12),hover=mix(bg,accent,.20),selected=selected,
   pill=pill,tab=tab,accent=accent,primary=primary,focus=accent,
   active=mix(primary,accent,.35),disabled=mix(bg,text,.07),dim=mix(text,bg,.40),
   gradient=gradient)


THEMES.update({
 'navy_mirage':reference_palette('Морской мираж','#141e30','#a9c8e6','#e6edf5',gradient=('#141e30','#223a55','#35577d'),primary='#35577d'),
 'royal_sapphire':reference_palette('Королевский сапфир','#112250','#e0c58f','#f5f0e9',gradient=('#112250','#1d315c','#3c507d'),primary='#3c507d'),
 'neon_violet':reference_palette('Неоновая фиолетовая','#100d1c','#e488fa','#f4edf9',gradient=('#100d1c','#191329','#281531'),primary='#8d329f'),
 'aurora':reference_palette('Аврора','#070c18','#77d5ff','#e4edf7',gradient=('#070c18','#12213a','#352432'),primary='#255f9c'),
 'coral_glass':reference_palette('Коралловое стекло','#20232b','#ffaaa2','#f0eff2',gradient=('#3b4855','#272d36','#1b1d24'),primary='#a34348'),
 'nocturne':reference_palette('Ночной цветок','#1a1026','#d9a7c5','#e0d6ee',primary='#7e496b'),
 'dune':reference_palette('Эфирные дюны','#f4efe6','#6b705c','#34382c',light=True,gradient=('#f4efe6','#ece0d2','#e7c0b8'),primary='#6b705c'),
 'lagoon':reference_palette('Звёздная лагуна','#002b36','#a6d6c9','#e6d6ea',primary='#1f5f63'),
 'crimson':reference_palette('Багровая дымка','#2b0a12','#df9ead','#e7d7d9',primary='#9e3f57'),
 'jade':reference_palette('Нефритовый шёпот','#1b2e28','#b6d8c7','#ecf3e9',primary='#336b5c'),
 'velvet':reference_palette('Бархатные сумерки','#1a1331','#c4a5d5','#d8c8e6',primary='#683f7f'),
 'amber':reference_palette('Янтарный мираж','#442c1a','#e9b98c','#fff3e0',primary='#a35c1e'),
 'sakura':reference_palette('Полночная сакура','#0b0e1a','#e3a6c0','#f3e6ec',primary='#854a6a'),
})

# Cool blues and greens, then violets, pinks and warm amber/beige tones.
THEME_ORDER=('aurora','ocean','navy_mirage','royal_sapphire','light','lagoon','jade','forest',
             'graphite','dark','velvet','neon_violet','nocturne','sakura','crimson','coral_glass','amber','dune','warm')
THEMES={key:THEMES[key] for key in THEME_ORDER}

# The previous flat dark card remains available independently of app themes.
CARD_THEMES={'standard':{key:value for key,value in THEMES['aurora'].items() if key!='gradient'},**THEMES}
CARD_THEMES['standard']['label']='Стандартная'


def card_palette(key):
 return CARD_THEMES.get(key,CARD_THEMES['aurora'])


# Keep the previous screen backdrop as an explicit choice. Word cards and
# translated captions have independent themes and opacity settings.
OVERLAY_THEMES={'standard':{**THEMES['ocean'],'label':'Стандартная','bg':'#0a111c','text':'#e5f6ff'},**THEMES}


def overlay_palette(key,app_theme='aurora'):
 return palette(app_theme) if key=='' else OVERLAY_THEMES.get(key,OVERLAY_THEMES['standard'])

SCROLLBAR_STYLE='''
QScrollBar:vertical { background:transparent; width:12px; margin:3px 2px; border:0; }
QScrollBar::handle:vertical { background:#33475e; min-height:32px; border-radius:4px; }
QScrollBar:horizontal { background:transparent; height:12px; margin:2px 3px; border:0; }
QScrollBar::handle:horizontal { background:#33475e; min-width:32px; border-radius:4px; }
QScrollBar::handle:vertical:hover,QScrollBar::handle:horizontal:hover { background:#7de0cc; }
QScrollBar::handle:vertical:pressed,QScrollBar::handle:horizontal:pressed { background:#399c8f; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; border:0; background:transparent; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; border:0; background:transparent; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QScrollBar::up-arrow,QScrollBar::down-arrow,QScrollBar::left-arrow,QScrollBar::right-arrow { width:0; height:0; background:transparent; }
'''


def reference_styles(colors):
 stops=','.join(f'stop:{index/(len(colors["gradient"])-1):.2f} {color}' for index,color in enumerate(colors['gradient']))
 return f'''
QWidget {{ background:transparent; }}
QWidget#lexoraRoot {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,{stops}); }}
QDialog,QMenu,QComboBox QAbstractItemView {{ background:{colors['field']}; }}
ResultWindow {{ background:{colors['bg']}; }}
QListWidget#navigation {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {colors['side']},stop:1 {mix(colors['side'],colors['bg'],.5)}); }}
QListWidget#navigation::item:selected {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {colors['selected']},stop:1 {colors['pill']}); }}
QPushButton#primary {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {colors['primary']},stop:1 {mix(colors['primary'],'#000000',.10)}); }}
QPushButton#primary:disabled {{ background:{colors['disabled']}; }}
'''


def palette(theme):return THEMES.get(theme,THEMES['aurora'])

def stylesheet(css,theme):
 colors=palette(theme)
 # Replace once: a destination colour must never become another source colour.
 result=re.sub(r'#[0-9a-fA-F]{6}\b',lambda match:colors.get(COLOR_ROLES.get(match[0].lower()),match[0]),css)
 return result+reference_styles(colors) if 'gradient' in colors else result
