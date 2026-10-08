import csv
import json
from pathlib import Path
import sqlite3
import uuid
from .storage import Dictionary,base_dir
from .auth import ServiceError


class Dictionaries:
    def __init__(self,store,settings):
        self.store,self.settings = store,settings

    def sources(self):
        return [{'id':'wiktionary','name':'Викисловарь · значения, транскрипция и примеры','path':str(base_dir()/'data'/'wiktionary.sqlite3')},
                {'id':'freedict','name':'FreeDict / WikDict · EN → RU','path':str(base_dir()/'data'/'dictionary.sqlite3')},
                {'id':'wordnet','name':'WordNet 3.1 · определения EN','path':str(base_dir()/'data'/'wordnet.sqlite3')},
                {'id':'personal','name':'Мои сохранённые слова','path':''},
                *self.settings.get('custom_dictionaries',[])]

    def lookup(self,term):
        entries = []
        enabled = self.settings.get('dictionary_enabled',[])
        for source in self.sources():
            if source['id'] not in enabled:
                continue
            if source['id']=='personal':
                with self.store.connect() as conn:
                    rows = conn.execute('SELECT meaning FROM words WHERE lower(term)=? ORDER BY id DESC LIMIT 3',
                                        (term.casefold().strip(' .,!?;:"()[]'),)).fetchall()
                value = '\n\n'.join(r[0] for r in rows)
            else:
                try:
                    value = Dictionary(Path(source['path'])).lookup(term)
                except (sqlite3.Error,OSError):
                    value = ''
            if value:
                entries.append(source['name']+'\n'+value)
        return '\n\n──────────\n\n'.join(entries)

    def import_file(self,path,name):
        path = Path(path)
        if path.stat().st_size>150*1024*1024:
            raise ServiceError('Словарь слишком большой: максимум 150 МБ.')
        try:
            if path.suffix.casefold()=='.json':
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                records = ({'term':k,'meaning':v} for k,v in data.items()) if isinstance(data,dict) else data
                rows = self.normalize(records)
            else:
                with path.open(encoding='utf-8-sig',newline='') as handle:
                    sample = handle.read(8192)
                    handle.seek(0)
                    try:dialect = csv.Sniffer().sniff(sample,delimiters=',;\t')
                    except csv.Error:dialect = csv.excel
                    rows = self.normalize(csv.DictReader(handle,dialect=dialect))
        except (ValueError,TypeError,UnicodeError,csv.Error):
            raise ServiceError('Не удалось прочитать словарь. Используй UTF-8 JSON или CSV с полями term/meaning либо word/translation.') from None
        if not rows:
            raise ServiceError('В словаре нет непустых пар слово / значение.')
        ident = 'custom-'+uuid.uuid4().hex
        folder = self.store.folder/'dictionaries'
        folder.mkdir(exist_ok=True)
        destination = folder/(ident+'.sqlite3')
        conn = sqlite3.connect(destination)
        try:
            with conn:
                conn.execute('CREATE TABLE dictionary(term TEXT,meaning TEXT)')
                conn.executemany('INSERT INTO dictionary VALUES(?,?)',rows)
                conn.execute('CREATE INDEX dictionary_term ON dictionary(term)')
        finally:conn.close()
        source = {'id':ident,'name':name.strip() or path.stem,'path':str(destination),'entries':len(rows)}
        self.settings['custom_dictionaries'].append(source)
        self.settings['dictionary_enabled'].append(ident)
        self.store.save_settings(self.settings)
        return source

    @staticmethod
    def normalize(records):
        rows = []
        for record in records:
            if not isinstance(record,dict):raise ValueError('Invalid row')
            term = record.get('term',record.get('word',''))
            meaning = record.get('meaning',record.get('translation',''))
            if not isinstance(term,str) or not isinstance(meaning,str):raise ValueError('Invalid values')
            if term.strip() and meaning.strip():
                rows.append((term.strip().casefold(),meaning.strip()))
            if len(rows)>1000000:raise ValueError('Too many entries')
        return rows
