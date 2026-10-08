from pathlib import Path
import sys,zipfile
def package_runtime(source,destination):
    source=Path(source)
    destination=Path(destination)
    if not (source/'Lexora.exe').is_file():raise FileNotFoundError('Build Lexora.exe first')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(source.rglob('*')):
            rel=file.relative_to(source)
            if not file.is_file() or '__pycache__' in rel.parts or file.suffix in ('.pyc','.dpapi') or file.name in ('settings.json','words.sqlite3','application.lock'):continue
            archive.write(file,'Lexora-0.6.1/'+rel.as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:raise RuntimeError('Invalid installer payload')
if __name__=='__main__':package_runtime(sys.argv[1],sys.argv[2])
