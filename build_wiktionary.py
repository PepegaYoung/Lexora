"""Extract English entries with Russian glosses from the Russian Wiktionary.

Uses the Kaikki/Wiktextract JSONL dump; no scraping, no executable content.
Data attribution and share-alike notice are in licenses/Wiktionary/README.md.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote
import requests
from contextlib import closing

URL='https://kaikki.org/dictionary/downloads/ru/ru-extract.jsonl.gz'
POS={'noun':'существительное','verb':'глагол','adj':'прилагательное','adv':'наречие',
     'phrase':'выражение','prep':'предлог','pron':'местоимение','name':'имя собственное',
     'conj':'союз','intj':'междометие','num':'числительное'}

def convert(record):
    if record.get('lang_code')!='en':return None
    term=record.get('word','').strip()
    if not term:return None
    parts=[POS.get(record.get('pos'),record.get('pos',''))]
    ipa=list(dict.fromkeys(s['ipa'] for s in record.get('sounds',[]) if s.get('ipa')))
    if ipa:parts.append(' / '.join(ipa[:3]))
    found=False
    for sense in record.get('senses',[]):
        gloss='; '.join(g for g in sense.get('glosses',[]) if isinstance(g,str))
        if not gloss:continue
        found=True
        parts.append('• '+gloss)
        for ex in sense.get('examples',[])[:2]:
            if ex.get('text'):
                parts.append('  '+ex['text']+((' — '+ex['translation']) if ex.get('translation') else ''))
    if not found:return None
    synonyms=list(dict.fromkeys(s['word'] for s in record.get('synonyms',[]) if s.get('word')))
    if synonyms:parts.append('Синонимы: '+', '.join(synonyms[:8]))
    parts.append('Источник: https://ru.wiktionary.org/wiki/'+quote(term,safe=''))
    meaning='\n'.join(p for p in parts if p)
    forms=list(dict.fromkeys(f.get('form','').strip().casefold() for f in record.get('forms',[])))
    return term.casefold(),meaning,[f for f in forms if f and len(f)<=150]

def build(archive,destination):
    temporary=destination.with_suffix('.building.sqlite3')
    count=0
    with closing(sqlite3.connect(temporary)) as conn,conn:
        conn.execute('CREATE TABLE dictionary(term TEXT,meaning TEXT)')
        conn.execute('CREATE TABLE forms(form TEXT,term TEXT)')
        rows,forms=[],[]
        with gzip.open(archive,'rt',encoding='utf-8') as handle:
            for line in handle:
                item=convert(json.loads(line))
                if item:
                    term,meaning,aliases=item
                    rows.append((term,meaning))
                    forms.extend((f,term) for f in aliases if f!=term)
                    count+=1
                if len(rows)>=2000:
                    conn.executemany('INSERT INTO dictionary VALUES(?,?)',rows)
                    conn.executemany('INSERT INTO forms VALUES(?,?)',forms)
                    rows,forms=[],[]
        conn.executemany('INSERT INTO dictionary VALUES(?,?)',rows)
        conn.executemany('INSERT INTO forms VALUES(?,?)',forms)
        conn.execute('CREATE INDEX dictionary_term ON dictionary(term)')
        conn.execute('CREATE INDEX forms_form ON forms(form)')
        words=conn.execute('SELECT count(DISTINCT term) FROM dictionary').fetchone()[0]
        assert count>10000, 'Incomplete extraction'
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    temporary.replace(destination)
    with archive.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    info={'source':URL,'edition':'ru.wiktionary.org','language':'en','entries':count,'headwords':words,
          'archive_sha256':digest,'license':'CC BY-SA 4.0 / GFDL','extracted':'2026-10-07',
          'processing':'English entries, Russian definitions, IPA, examples, synonyms and inflected forms; etymology omitted.'}
    destination.with_suffix('.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    if not args.archive.exists():
        with requests.get(URL,stream=True,timeout=(15,60)) as response:
            response.raise_for_status()
            total=0
            with args.archive.open('wb') as out:
                for chunk in response.iter_content(1024*1024):
                    out.write(chunk);total+=len(chunk)
                    if total%(25*1024*1024)<len(chunk):print('Download',round(total/1024/1024),'MB',flush=True)
    build(args.archive,args.destination)
