"""Check Git-tracked publication files without printing secret values.

This is a packaging guard, not a replacement for a dedicated secret scanner.
It checks tracked files when Git is initialized; otherwise the release tree.
"""
from pathlib import Path
import os,re,subprocess,sys,zipfile,json

ROOT=Path(__file__).resolve().parent.parent
BLOCKED_PARTS={'__pycache__','.venv','venv','_internal','build','dist','.git','backups','reports','models'}
BLOCKED_NAMES={'settings.json','words.sqlite3','credentials.dpapi','application.lock','desktop.ini','thumbs.db'}
SECRET_PATTERNS=[
    re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
    re.compile(rb'\bAIza[A-Za-z0-9_-]{35}'),
    re.compile(rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(rb'\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{32,}-----END'),
]
PRIVATE_PATH=re.compile(rb'(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\r\n"\x00 ]+')

def candidate_files():
    if (ROOT/'.git').exists():
        result=subprocess.run(['git','-C',str(ROOT),'ls-files','-z'],capture_output=True,check=True)
        return [ROOT/name.decode('utf-8') for name in result.stdout.split(b'\0') if name]
    generated={'data/dictionary.sqlite3','data/wordnet.sqlite3','data/wiktionary.sqlite3','data/source/eng-rus.tei'}
    return [file for file in ROOT.rglob('*') if file.is_file() and
            not any(part in BLOCKED_PARTS for part in file.relative_to(ROOT).parts) and
            file.relative_to(ROOT).as_posix() not in generated]

def check_content(label,content,issues):
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):issues.append(label+': possible embedded secret')
    if PRIVATE_PATH.search(content):issues.append(label+': personal absolute path')
    if content.startswith(b'{'):
        try:
            value=json.loads(content)
            if isinstance(value,dict) and value.get('format')=='lexora-backup':issues.append(label+': personal backup')
        except (ValueError,UnicodeError):pass

def check():
    issues=[];files=candidate_files()
    for file in files:
        rel=file.relative_to(ROOT);label=rel.as_posix()
        if any(part in BLOCKED_PARTS for part in rel.parts) or file.name.lower() in BLOCKED_NAMES or file.suffix.lower() in {'.exe','.dll','.dpapi','.pyc'} or file.name.startswith('.env'):
            issues.append(label+': runtime or personal file')
        if file.stat().st_size>=25*1024*1024:issues.append(label+': too large for browser repository upload')
        content=file.read_bytes();check_content(label,content,issues)
        if file.suffix=='.zip':
            if label!='data/bundled-dictionaries.zip':issues.append(label+': unexpected archive')
            with zipfile.ZipFile(file) as package:
                if package.testzip() is not None:issues.append(label+': invalid archive')
                for name in package.namelist():check_content(label+'!'+name,package.read(name),issues)
    if issues:
        for message in issues:print(message)
        return 1
    print(f'Publication guard passed ({len(files)} files). Run Gitleaks as a separate check.')
    return 0

if __name__=='__main__':raise SystemExit(check())
