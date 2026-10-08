"""Current-user installer. No elevation, credentials, registry or game changes."""
import base64,ctypes,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath

VERSION='0.6.1'

def install_payload(payload,target):
    target=Path(target).resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(payload) as archive:
        records=[]
        for info in archive.infolist():
            path=PurePosixPath(info.filename)
            if not path.parts or path.parts[0]!='Lexora-'+VERSION or path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename:
                raise ValueError('Invalid installation archive')
            rel=Path(*path.parts[1:])
            if info.is_dir():continue
            records.append((info,rel))
        if not any(rel==Path('Lexora.exe') for _,rel in records):raise ValueError('Missing application')
        if target.exists():
            # Reinstalling the same version is idempotent, never replaces a running app.
            if all((target/rel).is_file() and (target/rel).read_bytes()==archive.read(info) for info,rel in records):return target
            raise FileExistsError('This version is already installed; use another folder or remove the old version first.')
        with tempfile.TemporaryDirectory(prefix='lexora-install-',dir=target.parent) as folder:
            staging=Path(folder)/'application'
            staging.mkdir()
            for info,rel in records:
                destination=(staging/rel).resolve()
                if not destination.is_relative_to(staging.resolve()):raise ValueError('Invalid archive path')
                destination.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(info) as source,destination.open('wb') as out:shutil.copyfileobj(source,out)
            staging.rename(target)
    return target

def shortcuts(target):
    script=r'''
    $ErrorActionPreference='Stop'
    $ProgressPreference='SilentlyContinue'
    [Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
    $data=[Console]::In.ReadToEnd() | ConvertFrom-Json
    $shell=New-Object -ComObject WScript.Shell
    $start=[Environment]::GetFolderPath('Programs')
    $desktop=[Environment]::GetFolderPath('Desktop')
    foreach ($folder in @($start,$desktop)) {
      $link=$shell.CreateShortcut((Join-Path $folder 'Lexora.lnk'))
      $link.TargetPath=$data.exe
      $link.WorkingDirectory=$data.folder
      $link.IconLocation=$data.exe+',0'
      $link.Save()
    }
    '''
    executable=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(executable),'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],
        input=json.dumps({'exe':str(target/'Lexora.exe'),'folder':str(target)}).encode('ascii'),capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,timeout=30)
    return result.returncode==0

def main():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    payload=root/'payload.zip'
    if '--verify-install' in sys.argv:
        destination=Path(sys.argv[sys.argv.index('--verify-install')+1])
        installed=install_payload(payload,destination)
        assert (installed/'Lexora.exe').is_file()
        assert (installed/'data/wiktionary.sqlite3').is_file()
        install_payload(payload,destination)
        return 0
    message=ctypes.windll.user32.MessageBoxW
    destination=Path(os.environ['LOCALAPPDATA'])/'Programs/Lexora'/VERSION
    if message(None,'Установить Lexora '+VERSION+' для текущего пользователя?\n\n'+str(destination)+'\n\nСлова и прежние подключения сохранятся.','Установка Lexora',1)!=1:return 0
    try:
        installed=install_payload(payload,destination)
        links=shortcuts(installed)
    except Exception:
        message(None,'Не удалось установить Lexora. Если версия уже установлена, используй её папку. Также можно распаковать portable-архив вручную.','Lexora',0x10)
        return 1
    text='Установка завершена.' if links else 'Установка завершена, но ярлык создать не удалось. Открой Lexora.exe в папке установки.'
    if message(None,text+'\n\nОткрыть Lexora?','Lexora',4)==6:
        ctypes.windll.shell32.ShellExecuteW(None,'open',str(installed/'Lexora.exe'),None,str(installed),1)
    return 0

if __name__=='__main__':raise SystemExit(main())
