import hashlib
from pathlib import Path
import shutil
import tempfile
import zipfile
import requests

from .auth import ServiceError

MODEL_URL = 'https://argos-net.com/v1/translate-en_ru-1_9.argosmodel'
MODEL_SHA256 = '591d743ae103752b88ffc38785c50421320f4eff93c8967e0d3d2e14d4e27811'


def download_model(folder, destination=None):
    """Install one pinned, verified archive without extracting arbitrary paths."""
    folder = Path(folder)
    target = Path(destination)/'en-ru' if destination else folder/'models'/'en-ru'
    required = ('sentencepiece.model','model/model.bin','model/config.json','model/shared_vocabulary.json')
    if all((target/name).is_file() for name in required):
        return str(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.windowwords-download-',dir=target.parent) as temp:
        archive = Path(temp)/'model.zip'
        checksum = hashlib.sha256()
        try:
            with requests.get(MODEL_URL,stream=True,timeout=(5,20)) as response:
                response.raise_for_status()
                with archive.open('wb') as output:
                    size = 0
                    for chunk in response.iter_content(1024*1024):
                        size += len(chunk)
                        if size>500*1024*1024:
                            raise ServiceError('Файл модели слишком большой.')
                        output.write(chunk)
                        checksum.update(chunk)
        except requests.RequestException:
            raise ServiceError('Не удалось загрузить модель. Проверь сеть и повтори.') from None
        if checksum.hexdigest()!=MODEL_SHA256:
            raise ServiceError('Контрольная сумма модели не совпала. Установка отменена.')
        target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            for name in (*required,'metadata.json','README.md'):
                matches = [info for info in package.infolist() if info.filename.endswith('/'+name)]
                if not matches and name in required:
                    raise ServiceError('В архиве отсутствует необходимый файл модели.')
                if matches:
                    destination = target/name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    temp_file = destination.with_suffix(destination.suffix+'.tmp')
                    with package.open(matches[0]) as source,temp_file.open('wb') as output:
                        shutil.copyfileobj(source,output)
                    temp_file.replace(destination)
        (target/'MODEL_SOURCE.txt').write_text('Argos Translate English → Russian 1.9\n'+MODEL_URL+
            '\nSHA256: '+MODEL_SHA256+'\nTraining-data acknowledgements: README.md\n',encoding='utf-8')
    return str(target)
