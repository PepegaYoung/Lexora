"""Restore only the public bundled dictionaries; no network or user-profile access."""
from pathlib import Path
import hashlib,json,os,tempfile,zipfile

ROOT=Path(__file__).resolve().parent.parent
EXPECTED={'dictionary.sqlite3','wordnet.sqlite3','wiktionary.sqlite3','source/eng-rus.tei'}

def digest(file):
    with Path(file).open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def restore(destination=None):
    data=ROOT/'data'
    destination=Path(destination) if destination is not None else data
    manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    archive=data/'bundled-dictionaries.zip'
    if manifest.get('version')!=1 or set(manifest['files'])!=EXPECTED:
        raise ValueError('Unexpected dictionary manifest')
    if digest(archive)!=manifest['archive_sha256']:
        raise ValueError('Dictionary archive checksum mismatch')
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        if set(package.namelist())!=EXPECTED or len(package.namelist())!=len(EXPECTED):
            raise ValueError('Unexpected dictionary archive entries')
        # Validate every member and existing target before writing any files.
        contents={}
        for name in sorted(EXPECTED):
            expected=manifest['files'][name]
            info=package.getinfo(name)
            if info.file_size!=expected['bytes'] or info.file_size>64*1024*1024:
                raise ValueError('Unexpected dictionary size')
            content=package.read(name)
            if hashlib.sha256(content).hexdigest()!=expected['sha256']:
                raise ValueError('Dictionary content checksum mismatch')
            target=destination/name
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Dictionary target escapes destination')
            if target.exists() and (not target.is_file() or digest(target)!=expected['sha256']):
                raise FileExistsError('Existing dictionary differs: '+name)
            contents[name]=content
        written=0
        for name,content in contents.items():
            target=destination/name
            if target.exists():continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix='.lexora-dictionary-',dir=target.parent,delete=False) as handle:
                temporary=Path(handle.name);handle.write(content)
            try:
                # Refuse a conflicting target created after the validation phase.
                if target.exists():
                    if digest(target)!=manifest['files'][name]['sha256']:raise FileExistsError(name)
                else:os.replace(temporary,target);written+=1
            finally:
                if temporary.exists():temporary.unlink()
    return written

if __name__=='__main__':
    count=restore()
    print(f'Public dictionaries ready ({count} files restored).')
