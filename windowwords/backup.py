"""Explicit JSON backup. Credentials, IDs and machine-specific geometry stay local."""
import json,math,ntpath
from .storage import atomic_write

PREFERENCES={'provider','models','filter','game','font_size','opacity','offset','region','monitor','local_model','profiles','hotkeys',
    'ui_scale','theme','card_width','card_height','card_background','overlay_background','model_download_dir',
    'auto_start_region','screen_scope','screen_mode','local_quality','game_mode','auto_card','auto_translate_card','auto_profiles','profile_apps',
    'yandex_auth','yandex_folder','deepl_plan','libre_url','dictionary_enabled'}

def export_backup(store,settings,path):
    with store.connect() as conn:
        reviews=conn.execute('SELECT word_id,due,days,attempts,known FROM reviews').fetchall()
    payload={'format':'lexora-backup','version':1,'settings':{k:v for k,v in settings.items() if k in PREFERENCES},
             'words':[list(row) for row in store.words()],'reviews':[list(row) for row in reviews]}
    atomic_write(path,json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8'))

def import_backup(store,path):
    if path.stat().st_size>20*1024*1024:raise ValueError('Архив JSON больше 20 МБ.')
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('format')!='lexora-backup' or data.get('version')!=1:raise ValueError('Это не резервная копия Lexora.')
    preferences=data.get('settings',{})
    words=data.get('words',[]);reviews=data.get('reviews',[])
    if not isinstance(preferences,dict) or not isinstance(words,list) or not isinstance(reviews,list):raise ValueError('Повреждена резервная копия.')
    if any(k not in PREFERENCES for k in preferences):raise ValueError('Копия содержит неподдерживаемые настройки.')
    current=store.settings()
    for key,value in preferences.items():
        reference=current[key]
        if type(value) is not type(reference) and not (key=='region' and (value is None or isinstance(value,list))):raise ValueError('Неверный тип настройки: '+key)
    ranges={'ui_scale':(75,175),'font_size':(12,48),'card_width':(320,1000),'card_height':(320,1100),
            'opacity':(.3,1),'card_background':(.15,1),'overlay_background':(0,1),'offset':(0,180)}
    for key,(low,high) in ranges.items():
        if key in preferences and not low<=preferences[key]<=high:raise ValueError('Неверное значение настройки: '+key)
    from . import native,ocr
    from .providers import LABELS
    enums={'provider':set(LABELS),'filter':{p[0] for p in ocr.PROFILES},'theme':{'light','dark'},
           'game_mode':{'external','overlay'},'screen_scope':{'monitor','region'},'screen_mode':{'above','replace'},'local_quality':{'fast','balanced','quality'},
           'yandex_auth':{'api_key','iam'},'deepl_plan':{'auto','free','pro'}}
    for key,allowed in enums.items():
        if key in preferences and preferences[key] not in allowed:raise ValueError('Неверный выбор: '+key)
    def valid_region(region):
        return region is None or (isinstance(region,list) and len(region)==4 and
            all(type(v) in (int,float) and math.isfinite(v) for v in region) and region[2]>0 and region[3]>0)
    if 'region' in preferences and not valid_region(preferences['region']):raise ValueError('Неверная область.')
    profiles=preferences.get('profiles',current['profiles'])
    profile_keys={'region','monitor','filter','font_size','opacity','offset','screen_scope','screen_mode','overlay_background',
                  'card_width','card_height','card_background'}
    for name,profile in profiles.items():
        if not isinstance(name,str) or not isinstance(profile,dict) or set(profile)-profile_keys:raise ValueError('Неверный профиль игры.')
        if not valid_region(profile.get('region')):raise ValueError('Неверная область профиля.')
        for key,value in profile.items():
            if key in ranges and (type(value) not in (int,float) or not ranges[key][0]<=value<=ranges[key][1]):raise ValueError('Неверный размер в профиле.')
            if key in enums and value not in enums[key]:raise ValueError('Неверный режим профиля.')
        if not isinstance(profile.get('monitor',''),str):raise ValueError('Неверный монитор профиля.')
    for exe,game in preferences.get('profile_apps',current['profile_apps']).items():
        if not isinstance(exe,str) or ntpath.basename(exe)!=exe or not exe.lower().endswith('.exe') or not isinstance(game,str) or game not in profiles:raise ValueError('Неверная привязка профиля.')
    if any(not isinstance(key,str) or not isinstance(value,str) for key,value in preferences.get('models',{}).items()):raise ValueError('Неверный список моделей.')
    if any(not isinstance(value,str) for value in preferences.get('dictionary_enabled',[])):raise ValueError('Неверный список словарей.')
    if 'libre_url' in preferences:
        from urllib.parse import urlparse
        url=urlparse(preferences['libre_url'])
        if not url.hostname or url.username or url.password or url.query or url.fragment or (url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('localhost','127.0.0.1','::1'))):raise ValueError('Неверный адрес LibreTranslate.')
    if 'hotkeys' in preferences:
        keys=preferences['hotkeys']
        if set(keys)!=set(current['hotkeys']):raise ValueError('Неверные команды горячих клавиш.')
        native.validate_bindings(keys)
    if any(not isinstance(row,list) or len(row)!=6 or type(row[0]) is not int or any(not isinstance(t,str) or len(t)>100000 for t in row[1:]) for row in words):raise ValueError('Неверный формат слов.')
    if len({row[0] for row in words})!=len(words):raise ValueError('Слова повторяются в копии.')
    if any(not isinstance(row,list) or len(row)!=5 or type(row[0]) is not int or
           any(type(t) not in (int,float) or not math.isfinite(t) or t<0 for t in row[1:]) for row in reviews):raise ValueError('Неверный формат повторений.')
    # Merge by content, retain local IDs and words; never replace the credential vault.
    with store.connect() as conn:
        mapping={}
        for ident,term,meaning,sentence,game,created in words:
            existing=conn.execute('SELECT id FROM words WHERE term=? AND meaning=? AND sentence=? AND game=?',
                                  (term,meaning,sentence,game)).fetchone()
            if existing:mapping[ident]=existing[0]
            else:
                cursor=conn.execute('INSERT INTO words(term,meaning,sentence,game,created) VALUES(?,?,?,?,?)',(term,meaning,sentence,game,created))
                mapping[ident]=cursor.lastrowid
        for ident,*progress in reviews:
            if ident in mapping:conn.execute('INSERT OR IGNORE INTO reviews VALUES(?,?,?,?,?)',(mapping[ident],*progress))
    current.update(preferences)
    store.save_settings(current)
    return current,len(mapping)
