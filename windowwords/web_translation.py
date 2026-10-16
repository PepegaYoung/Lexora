"""Optional anonymous translation endpoints; not an official supported API.

No authentication, CAPTCHA solving, retries, or automatic provider switching.
"""
from .i18n import tr,trf
import time
import requests
from .auth import ServiceError

NAMES={'yandex_web':'Яндекс (бесплатно)'}


def extract(provider,payload):
    if provider!='yandex_web':raise ServiceError('Этот переводчик больше не поддерживается.')
    try:
        if not isinstance(payload,dict) or str(payload.get('code'))!='200':
            code=payload.get('code') if isinstance(payload,dict) else None
            if code in (401,403,429):raise ServiceError(NAMES[provider]+': сервис ограничил доступ. Выбери другой переводчик.')
            raise ValueError()
        values=payload['text']
        if not isinstance(values,list) or not values or not all(isinstance(x,str) for x in values):raise ValueError()
        value='\n'.join(values)
        if not value.strip():raise ValueError()
        return value
    except (KeyError,IndexError,TypeError,ValueError):
        raise ServiceError(NAMES[provider]+': бесплатный сервис вернул неполный ответ или изменил формат. Можно выбрать другой переводчик.') from None


class WebTranslator:
    def __init__(self):
        self.last_request={}
        self.session=requests.Session()
        self.session.headers.update({'User-Agent':'Lexora','Accept':'application/json'})

    def translate(self,provider,text,cancel=None):
        if provider!='yandex_web':raise ServiceError('Этот переводчик больше не поддерживается.')
        if not text.strip():return ''
        if len(text)>4000:raise ServiceError(NAMES[provider]+': переводи фрагменты до 4000 символов.')
        # Background worker only; checks cancellation while pacing new requests.
        while time.monotonic()-self.last_request.get(provider,-10000)<1:
            if cancel and cancel():raise ServiceError(tr('Запрос больше не актуален.'))
            time.sleep(.05)
        if cancel and cancel():raise ServiceError(tr('Запрос больше не актуален.'))
        self.last_request[provider]=time.monotonic()
        options={'timeout':(5,15),'allow_redirects':False}
        try:
            response=self.session.post('https://browser.translate.yandex.net/api/v1/tr.json/translate',
                params={'lang':'en-ru','srv':'browser_video_translation','text':text},
                data={'maxRetryCount':'0','fetchAbortTimeout':'1000'},**options)
            with response:
                if response.status_code in (401,403,429):
                    raise ServiceError(NAMES[provider]+': сервис ограничил доступ или требует проверку. Автоперевод остановлен; выбери другой переводчик.')
                if not response.ok or 300<=response.status_code<400:
                    raise ServiceError(NAMES[provider]+trf(': сервис недоступен (HTTP {0}).',response.status_code))
                try:payload=response.json()
                except ValueError:
                    raise ServiceError(NAMES[provider]+': сайт запросил проверку или изменил ответ. Автоматический обход не выполняется.') from None
                result=extract(provider,payload)
            if cancel and cancel():raise ServiceError(tr('Запрос больше не актуален.'))
            return result
        except requests.RequestException:
            raise ServiceError(NAMES[provider]+': нет ответа. Проверь сеть или выбери другой переводчик.') from None
