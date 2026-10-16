"""Explicitly selected translation providers; never switch providers implicitly."""
from .i18n import tr,trf
import html
import requests
from .auth import ServiceError

LABELS = {'yandex_web':'Яндекс (бесплатно)','subscription':'ChatGPT (подписка)',
          'api':'OpenAI API','mymemory':'MyMemory (бесплатно)',
          'yandex':'Яндекс API','deepl':'DeepL API','local':'Офлайн-модель'}
CLASSICAL = {'yandex','deepl','mymemory','yandex_web'}


def request_spec(provider,key,settings,text,context=()):
    lines = text.splitlines() or [text]
    if provider not in ('yandex','deepl'):raise ServiceError(tr('Этот переводчик больше не поддерживается. Выбери другой на вкладке «Перевод».'))
    if not key:
        raise ServiceError(tr('Сохрани ключ для ')+tr(LABELS[provider])+tr(' на вкладке «Перевод».'))
    if provider=='yandex':
        iam = settings.get('yandex_auth')=='iam'
        body = {'sourceLanguageCode':'en','targetLanguageCode':'ru','texts':lines,'format':'PLAIN_TEXT'}
        if iam and settings.get('yandex_folder'):
            body['folderId'] = settings['yandex_folder']
        elif iam:
            raise ServiceError(tr('Для IAM-токена Яндекса укажи ID каталога.'))
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
    raise ServiceError(tr('Неизвестный переводчик.'))


def translate(provider,key,settings,text,context=(),cancel=None):
    if provider=='mymemory':return translate_memory(text,cancel)
    url,arguments = request_spec(provider,key,settings,text,context)
    try:
        with requests.post(url,timeout=(8,25),**arguments) as response:
            if not response.ok:
                reasons = {400:tr('Проверь настройки подключения и языки.'),401:tr('Ключ недействителен.'),
                           403:tr('Ключ, проект или роль не разрешают доступ.'),429:tr('Достигнут лимит запросов.'),
                           456:tr('Лимит символов DeepL исчерпан.')}
                raise ServiceError(tr(LABELS[provider])+': '+reasons.get(response.status_code,trf('Сервис недоступен (HTTP {0}).',response.status_code)))
            payload = response.json()
            translated = [entry['text'] for entry in payload['translations']]
            if len(translated)!=len(text.splitlines() or [text]) or any(not isinstance(t,str) or not t.strip() for t in translated):
                raise ValueError('incomplete translation')
            return '\n'.join(translated)
    except requests.RequestException:
        # Never expose credentials or source text from request errors.
        raise ServiceError(tr(LABELS[provider])+tr(': нет ответа. Проверь сеть и повтори.')) from None
    except (ValueError,KeyError,TypeError):
        raise ServiceError(tr(LABELS[provider])+tr(': сервис вернул неполный перевод.')) from None


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
    if len(text)>5000:raise ServiceError(tr('MyMemory: переводи фрагменты до 5000 символов.'))
    lines = []
    try:
        for line in text.splitlines() or [text]:
            parts = []
            for chunk in memory_chunks(line):
                if cancel and cancel():raise ServiceError(tr('Запрос больше не актуален.'))
                with requests.get('https://api.mymemory.translated.net/get',params={'q':chunk,'langpair':'en|ru'},timeout=(8,20)) as response:
                    if not response.ok:raise ServiceError(tr('MyMemory: сервис недоступен или достигнут лимит запросов.'))
                    payload = response.json()
                    if payload.get('quotaFinished') or str(payload.get('responseStatus'))=='429':
                        raise ServiceError(tr('MyMemory: суточная квота исчерпана. Выбери офлайн-модель или другой сервис.'))
                    if str(payload.get('responseStatus'))!='200':raise ServiceError(tr('MyMemory не завершил перевод. Проверь язык и квоту.'))
                    value = payload['responseData']['translatedText']
                    if not isinstance(value,str) or not value.strip():raise ValueError('empty translation')
                    parts.append(html.unescape(value))
            lines.append(' '.join(parts))
        return '\n'.join(lines)
    except requests.RequestException:
        raise ServiceError(tr('MyMemory: нет ответа. Проверь сеть и повтори.')) from None
    except (ValueError,KeyError,TypeError):
        raise ServiceError(tr('MyMemory: неполный ответ сервиса.')) from None
