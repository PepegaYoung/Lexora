"""Explicitly selected translation providers; never switch providers implicitly."""
import html
import requests
from urllib.parse import urlparse
from .auth import ServiceError

LABELS = {'subscription':'ChatGPT · подписка','api':'OpenAI API','local':'Офлайн-модель',
          'yandex':'Яндекс Translate','google':'Google Cloud Translation','deepl':'DeepL API',
          'mymemory':'MyMemory · бесплатно, без ключа','libre':'LibreTranslate · свой / публичный сервер',
          'google_web':'Google · бесплатно, без ключа','yandex_web':'Яндекс · бесплатно, без ключа'}
CLASSICAL = {'yandex','google','deepl','mymemory','libre','google_web','yandex_web'}


def request_spec(provider,key,settings,text,context=()):
    lines = text.splitlines() or [text]
    if provider=='libre':
        address = settings.get('libre_url','').strip().rstrip('/')
        parsed = urlparse(address)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1'))):
            raise ServiceError('Укажи HTTPS-адрес LibreTranslate или http://localhost:5000 для своего сервера.')
        body = {'q':text,'source':'en','target':'ru','format':'text'}
        if key:body['api_key'] = key
        return address+'/translate',{'json':body}
    if not key:
        raise ServiceError('Сохрани ключ для '+LABELS[provider]+' на вкладке «Перевод».')
    if provider=='google':
        return ('https://translation.googleapis.com/language/translate/v2',
                {'params':{'key':key},'json':{'q':lines,'source':'en','target':'ru','format':'text'}})
    if provider=='yandex':
        iam = settings.get('yandex_auth')=='iam'
        body = {'sourceLanguageCode':'en','targetLanguageCode':'ru','texts':lines,'format':'PLAIN_TEXT'}
        if iam and settings.get('yandex_folder'):
            body['folderId'] = settings['yandex_folder']
        elif iam:
            raise ServiceError('Для IAM-токена Яндекса укажи ID каталога.')
        # Service-account API keys use the account's own folder, not folderId.
        return ('https://translate.api.cloud.yandex.net/translate/v2/translate',
                {'headers':{'Authorization':('Bearer ' if iam else 'Api-Key ')+key},'json':body})
    if provider=='deepl':
        plan = settings.get('deepl_plan','auto')
        free = plan=='free' or (plan=='auto' and key.endswith(':fx'))
        body = {'text':lines,'source_lang':'EN','target_lang':'RU','preserve_formatting':True}
        if context:
            body['context'] = '\n'.join(context[-3:])
        return ('https://api-free.deepl.com/v2/translate' if free else 'https://api.deepl.com/v2/translate',
                {'headers':{'Authorization':'DeepL-Auth-Key '+key},'json':body})
    raise ServiceError('Неизвестный переводчик.')


def translate(provider,key,settings,text,context=(),cancel=None):
    if provider=='mymemory':return translate_memory(text,cancel)
    url,arguments = request_spec(provider,key,settings,text,context)
    try:
        with requests.post(url,timeout=(8,25),**arguments) as response:
            if not response.ok:
                reasons = {400:'Проверь настройки подключения и языки.',401:'Ключ недействителен.',
                           403:'Ключ, проект или роль не разрешают доступ.',429:'Достигнут лимит запросов.',
                           456:'Лимит символов DeepL исчерпан.'}
                raise ServiceError(LABELS[provider]+': '+reasons.get(response.status_code,f'Сервис недоступен (HTTP {response.status_code}).'))
            payload = response.json()
            if provider=='libre':
                translated = payload['translatedText']
                if not isinstance(translated,str) or not translated.strip():raise ValueError('empty translation')
                return translated
            if provider=='google':
                entries = payload['data']['translations']
                translated = [html.unescape(entry['translatedText']) for entry in entries]
            else:
                translated = [entry['text'] for entry in payload['translations']]
            if len(translated)!=len(text.splitlines() or [text]) or any(not isinstance(t,str) or not t.strip() for t in translated):
                raise ValueError('incomplete translation')
            return '\n'.join(translated)
    except requests.RequestException:
        # Google credentials can occur in the request URL. Never echo errors.
        raise ServiceError(LABELS[provider]+': нет ответа. Проверь сеть и повтори.') from None
    except (ValueError,KeyError,TypeError):
        raise ServiceError(LABELS[provider]+': сервис вернул неполный перевод.') from None


def memory_chunks(text):
    chunks,current = [],''
    for character in text:
        if len((current+character).encode('utf-8'))>480:
            split = current.rfind(' ')
            if split>len(current)//2:
                chunks.append(current[:split])
                current = current[split+1:]
            else:
                chunks.append(current)
                current = ''
        current += character
    if current:chunks.append(current)
    return chunks


def translate_memory(text,cancel=None):
    if len(text)>5000:raise ServiceError('MyMemory: переводи фрагменты до 5000 символов.')
    lines = []
    try:
        for line in text.splitlines() or [text]:
            parts = []
            for chunk in memory_chunks(line):
                if cancel and cancel():raise ServiceError('Запрос больше не актуален.')
                with requests.get('https://api.mymemory.translated.net/get',params={'q':chunk,'langpair':'en|ru'},timeout=(8,20)) as response:
                    if not response.ok:raise ServiceError('MyMemory: сервис недоступен или достигнут лимит запросов.')
                    payload = response.json()
                    if payload.get('quotaFinished') or str(payload.get('responseStatus'))=='429':
                        raise ServiceError('MyMemory: суточная квота исчерпана. Выбери офлайн-модель или другой сервис.')
                    if str(payload.get('responseStatus'))!='200':raise ServiceError('MyMemory не завершил перевод. Проверь язык и квоту.')
                    value = payload['responseData']['translatedText']
                    if not isinstance(value,str) or not value.strip():raise ValueError('empty translation')
                    parts.append(html.unescape(value))
            lines.append(' '.join(parts))
        return '\n'.join(lines)
    except requests.RequestException:
        raise ServiceError('MyMemory: нет ответа. Проверь сеть и повтори.') from None
    except (ValueError,KeyError,TypeError):
        raise ServiceError('MyMemory: неполный ответ сервиса.') from None
