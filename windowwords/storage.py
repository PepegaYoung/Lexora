import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
from contextlib import contextmanager
import uuid
import time

APPEARANCE_DEFAULTS={
    'ui_scale':100,'theme':'aurora','card_theme':'','window_preset':'720p',
    'card_width':600,'card_height':700,'card_opacity':1.0,'font_size':22,
    'opacity':.9,'offset':14,'card_background':.72,'overlay_background':.58,'overlay_theme':'standard',
    'window_size_locked':False,'card_size_locked':False,
}

def base_dir():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


def profile_dir():
    override = os.environ.get('WINDOWWORDS_PROFILE')
    path = Path(override) if override else Path(os.environ['LOCALAPPDATA']) / 'WindowWords'
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    source = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise RuntimeError('Windows не смог защитить или прочитать сохранённые учётные данные.')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free(ctypes.cast(outgoing.data, ctypes.c_void_p))


class Vault:
    def __init__(self, folder):
        self.path = folder / 'credentials.dpapi'
        self.lock = threading.RLock()

    def read(self):
        if not self.path.exists():
            return {}
        return json.loads(protect(self.path.read_bytes(), decrypt=True))

    def write(self, value):
        atomic_write(self.path, protect(json.dumps(value).encode('utf-8')))

    def set(self, name, value):
        with self.lock:
            records = self.read()
            if value is None:
                records.pop(name, None)
            else:
                records[name] = value
            self.write(records)


class Store:
    def __init__(self, folder=None):
        self.folder = folder or profile_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.vault = Vault(self.folder)
        self.db = self.folder / 'words.sqlite3'
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS words (id INTEGER PRIMARY KEY, term TEXT, '
                         'meaning TEXT, sentence TEXT, game TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
            conn.execute('CREATE TABLE IF NOT EXISTS reviews (word_id INTEGER PRIMARY KEY REFERENCES words(id), '
                         'due REAL NOT NULL, days INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, '
                         'known INTEGER NOT NULL DEFAULT 0)')
            conn.execute('CREATE TRIGGER IF NOT EXISTS remove_review AFTER DELETE ON words BEGIN '
                         'DELETE FROM reviews WHERE word_id=OLD.id; END')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def settings(self):
        default = {'provider': 'yandex_web', 'models': {}, 'filter': 'raw', 'ocr_engine':'windows','ocr_device':'gpu', 'game': '',
                   'font_size': 22, 'opacity': .9, 'offset': 14, 'region': None,
                   'monitor': '', 'local_model': '', 'profiles':{},
                   'hotkeys':{'study':'Alt+Q','region':'Alt+W','toggle':'Alt+T','screen':'Alt+V'},
                   'gamepad_bindings':{'study':'','region':'','toggle':'','screen':''},'gamepad_enabled':False,
                   'host_id': 'urn:uuid:' + str(uuid.uuid4()),
                   'ui_scale':100,'ui_scale_revision':1,'theme':'aurora','theme_revision':1,'ui_language':'ru',
                   'card_width':600,'card_height':700,'card_size_revision':1,'card_theme':'','card_opacity':1.0,
                   'model_download_dir':'','dictionary_enabled':['wiktionary','personal'],
                   'custom_dictionaries':[],'yandex_auth':'api_key','yandex_folder':'','deepl_plan':'auto',
                   'window_geometry':'','window_preset':'720p',
                   'screen_scope':'region','screen_mode':'above','card_background':.72,'overlay_background':.58,
                   'local_quality':'balanced','game_mode':'external','dictionary_revision':2,'auto_card':True,
                   'auto_translate_card':False,'auto_profiles':False,'profile_apps':{},
                   'recording_visible':False,'game_protection':True,'protection_action':'quit',
                   'protected_games':['marvel.exe','marvel-win64-shipping.exe','marvelrivals.exe'],'onboarding_completed':False}
        default.update(APPEARANCE_DEFAULTS)
        binding_defaults=dict(default['hotkeys'])
        path = self.folder / 'settings.json'
        if path.exists():
            previous=json.loads(path.read_text(encoding='utf-8'))
            default.update(previous)
            # Existing profiles are already in use. Offer the first-run guide
            # only to new users; returning users can open it from Help.
            default['onboarding_completed']=previous.get('onboarding_completed',True)
            if previous.get('ui_scale_revision',0)<1:
                default['ui_scale']=max(60,min(175,round(previous.get('ui_scale',120)/1.2)))
                default['ui_scale_revision']=1
            if previous.get('card_size_revision',0)<1:
                if (previous.get('card_width'),previous.get('card_height')) in ((440,440),(560,600)):
                    default.update(card_width=600,card_height=700)
                default['card_size_revision']=1
            if previous.get('theme_revision',0)<1:
                if previous.get('theme','dark')=='dark':default['theme']='aurora'
                default['theme_revision']=1
            if 'window_preset' not in previous and previous.get('window_geometry'):default['window_preset']='custom'
            default['hotkeys']={action:default['hotkeys'].get(action,chord) for action,chord in binding_defaults.items()}
            if previous.get('dictionary_revision',0)<1:
                default['dictionary_enabled']=list(dict.fromkeys(['wiktionary',*default['dictionary_enabled']]))
                default['dictionary_revision']=1
            if previous.get('dictionary_revision',0)<2:
                if default['dictionary_enabled']==['wiktionary','freedict','wordnet','personal']:
                    default['dictionary_enabled']=['wiktionary','personal']
                default['dictionary_revision']=2
        else:
            self.save_settings(default)
        default.pop('auto_start_region',None)
        from .providers import LABELS
        from .themes import THEMES,CARD_THEMES,OVERLAY_THEMES
        if default.get('ui_language') not in ('ru','en'):default['ui_language']='ru'
        if type(default['onboarding_completed']) is not bool:default['onboarding_completed']=True
        if not isinstance(default['theme'],str) or default['theme'] not in THEMES:default['theme']='aurora'
        if not isinstance(default['card_theme'],str) or default['card_theme'] not in ('',*CARD_THEMES):default['card_theme']=''
        if not isinstance(default['overlay_theme'],str) or default['overlay_theme'] not in ('',*OVERLAY_THEMES):default['overlay_theme']='standard'
        if default['window_preset'] not in ('720p','1080p','1440p','custom'):default['window_preset']='720p'
        for key in ('window_size_locked','card_size_locked'):
            if type(default[key]) is not bool:default[key]=False
        if default['provider'] not in LABELS:default['provider']='yandex_web'
        default.pop('libre_url',None)
        from .gamepad import ACTIONS,validate_bindings
        try:validate_bindings(default['gamepad_bindings'])
        except ValueError:default['gamepad_bindings']={action:'' for action in ACTIONS};default['gamepad_enabled']=False
        if type(default['gamepad_enabled']) is not bool:default['gamepad_enabled']=False
        if type(default['game_protection']) is not bool:default['game_protection']=True
        if default['protection_action'] not in ('quit','pause'):default['protection_action']='quit'
        if not isinstance(default['protected_games'],list) or len(default['protected_games'])>100 or any(not isinstance(value,str) for value in default['protected_games']):
            default['protected_games']=['marvel.exe','marvel-win64-shipping.exe','marvelrivals.exe']
        return default

    def save_settings(self, settings):
        allowed = {'provider','models','filter','ocr_engine','ocr_device','game','font_size','opacity','offset','region','monitor','local_model','host_id','profiles','hotkeys','gamepad_bindings','gamepad_enabled',
                   'ui_scale','ui_scale_revision','theme','theme_revision','card_theme','card_size_revision','ui_language','card_width','card_height','card_opacity','window_size_locked','card_size_locked','model_download_dir','dictionary_enabled','custom_dictionaries',
                   'yandex_auth','yandex_folder','deepl_plan','window_geometry','window_preset',
                   'screen_scope','screen_mode','card_background','overlay_background','overlay_theme','local_quality','game_mode','dictionary_revision','auto_card',
                   'auto_translate_card','auto_profiles','profile_apps','game_protection','protection_action','protected_games','recording_visible','onboarding_completed'}
        safe = {k: v for k, v in settings.items() if k in allowed}
        atomic_write(self.folder / 'settings.json', json.dumps(safe, ensure_ascii=False, indent=2).encode('utf-8'))

    def save_word(self, term, meaning, sentence, game):
        with self.connect() as conn:
            conn.execute('INSERT INTO words(term,meaning,sentence,game) VALUES(?,?,?,?)', (term,meaning,sentence,game))

    def words(self, search=''):
        with self.connect() as conn:
            return conn.execute('SELECT id,term,meaning,sentence,game,created FROM words WHERE '
                                'term LIKE ? OR sentence LIKE ? OR meaning LIKE ? ORDER BY id DESC', ('%'+search+'%',)*3).fetchall()

    def delete_word(self, ident):
        with self.connect() as conn:
            conn.execute('DELETE FROM words WHERE id=?', (ident,))

    def edit_word(self, ident, term, meaning, sentence, game):
        with self.connect() as conn:
            conn.execute('UPDATE words SET term=?,meaning=?,sentence=?,game=? WHERE id=?', (term,meaning,sentence,game,ident))
            conn.execute('DELETE FROM reviews WHERE word_id=?',(ident,))

    def due_words(self,now=None,limit=20):
        now=time.time() if now is None else now
        with self.connect() as conn:
            return conn.execute('SELECT w.id,w.term,w.meaning,w.sentence,w.game,w.created FROM words w '
                'LEFT JOIN reviews r ON r.word_id=w.id WHERE r.word_id IS NULL OR r.due<=? '
                'ORDER BY COALESCE(r.due,0),w.id LIMIT ?',(now,limit)).fetchall()

    def review_word(self,ident,known,now=None):
        now=time.time() if now is None else now
        with self.connect() as conn:
            if not conn.execute('SELECT 1 FROM words WHERE id=?',(ident,)).fetchone():return False
            old=conn.execute('SELECT days,attempts,known FROM reviews WHERE word_id=?',(ident,)).fetchone() or (0,0,0)
            days=min(180,1 if old[0]==0 else max(3,old[0]*2+1)) if known else 0
            due=now+days*86400 if known else now+600
            conn.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?)',
                         (ident,due,days,old[1]+1,old[2]+int(bool(known))))
        return True

    def review_stats(self,now=None):
        now=time.time() if now is None else now
        with self.connect() as conn:
            total=conn.execute('SELECT COUNT(*) FROM words').fetchone()[0]
            due=conn.execute('SELECT COUNT(*) FROM words w LEFT JOIN reviews r ON r.word_id=w.id '
                            'WHERE r.word_id IS NULL OR r.due<=?',(now,)).fetchone()[0]
        return total,due


class Dictionary:
    def __init__(self, path=None):
        self.path = path or base_dir() / 'data' / 'dictionary.sqlite3'

    def lookup(self, text):
        term = text.casefold().strip(' .,!?;:"()[]')
        variants = [term]
        irregular = {'hid':'hide','hidden':'hide','trousers':'trousers','boots':'boot','missed':'miss',
                     'was':'be','were':'be','went':'go','found':'find','thought':'think','took':'take'}
        if term in irregular:
            variants.append(irregular[term])
        if term.endswith('ies'):
            variants.append(term[:-3]+'y')
        for suffix in ('ing','ed','es','s'):
            if term.endswith(suffix) and len(term) > len(suffix)+2:
                root = term[:-len(suffix)]
                variants += [root, root+'e']
                if len(root)>1 and root[-1]==root[-2]:
                    variants.append(root[:-1])
        if not self.path.exists():
            return ''
        from contextlib import closing
        with closing(sqlite3.connect(f'{self.path.as_uri()}?mode=ro', uri=True)) as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='forms'").fetchone():
                aliases=conn.execute('SELECT term FROM forms WHERE form=? LIMIT 10',(term,)).fetchall()
                variants.extend(row[0] for row in aliases)
            for variant in dict.fromkeys(variants):
                rows = conn.execute('SELECT meaning FROM dictionary WHERE term=? LIMIT 5', (variant,)).fetchall()
                if rows:
                    return '\n\n'.join(r[0] for r in rows)
        return ''
