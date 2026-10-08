"""Optional anonymous translation endpoints; not an official supported API.

No authentication, CAPTCHA solving, retries, or automatic provider switching.
"""
import time
import requests
from .auth import ServiceError

NAMES={'google_web':'Google · без ключа','yandex_web':'Яндекс · без ключа'}


def extract(provider,payload):
    try:
        if provider=='google_web':
            if not isinstance(payload,list) or not payload or not isinstance(payload[0],list):raise ValueError()
            parts=[]
            for part in payload[0]:
                if not isinstance(part,list) or not part or not isinstance(part[0],str):raise ValueError()
                parts.append(part[0])
            value=''.join(parts)
        else:
            if not isinstance(payload,dict) or str(payload.get('code'))!='200':
                code=payload.get('code') if isinstance(payload,dict) else None
                if code in (401,403,429):raise ServiceError(NAMES[provider]+': сервис ограничил доступ. Повторных запросов и обхода проверки нет; выбери другой переводчик.')
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
        self.session.headers.update({'User-Agent':'Lexora/0.6.1','Accept':'application/json'})

    def translate(self,provider,text,cancel=None):
        if not text.strip():return ''
        if len(text)>4000:raise ServiceError(NAMES[provider]+': переводи фрагменты до 4000 символов.')
        # Background worker only; checks cancellation while pacing new requests.
        while time.monotonic()-self.last_request.get(provider,-10000)<1:
            if cancel and cancel():raise ServiceError('Запрос больше не актуален.')
            time.sleep(.05)
        if cancel and cancel():raise ServiceError('Запрос больше не актуален.')
        self.last_request[provider]=time.monotonic()
        options={'timeout':(5,15),'allow_redirects':False}
        try:
            if provider=='google_web':
                response=self.session.get('https://translate.googleapis.com/translate_a/single',
                    params={'client':'gtx','sl':'en','tl':'ru','dt':'t','q':text},**options)
            elif provider=='yandex_web':
                response=self.session.post('https://browser.translate.yandex.net/api/v1/tr.json/translate',
                    params={'lang':'en-ru','srv':'browser_video_translation','text':text},
                    data={'maxRetryCount':'0','fetchAbortTimeout':'1000'},**options)
            else:raise ServiceError('Неизвестный бесплатный переводчик.')
            with response:
                if response.status_code in (401,403,429):
                    raise ServiceError(NAMES[provider]+': сервис ограничил доступ или требует проверку. Автоперевод остановлен; выбери другой переводчик.')
                if not response.ok or 300<=response.status_code<400:
                    raise ServiceError(NAMES[provider]+f': сервис недоступен (HTTP {response.status_code}).')
                try:payload=response.json()
                except ValueError:
                    raise ServiceError(NAMES[provider]+': сайт запросил проверку или изменил ответ. Автоматический обход не выполняется.') from None
                result=extract(provider,payload)
            if cancel and cancel():raise ServiceError('Запрос больше не актуален.')
            return result
        except requests.RequestException:
            raise ServiceError(NAMES[provider]+': нет ответа. Проверь сеть или выбери другой переводчик.') from None
