"""Official public-client OAuth only. No browser cookies or Codex credential reuse."""
from .i18n import tr,trf
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser

import jwt
import requests

AUTH = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
SCOPE = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
PLAN_SCOPE = 'chatgpt.tokens.use.direct'
APP_NAME = 'Lexora'


class ServiceError(RuntimeError):
    pass


def check_response(response):
    if response.ok:
        return
    codes = {401:tr('Ключ или подключение недействительны. Подключись заново.'),
             403:tr('Доступ не разрешён для этого аккаунта, модели или региона.'),
             429:tr('Достигнут лимит запросов или квота. Проверь использование в настройках сервиса.'),
             400:tr('Сервис отклонил запрос. Проверь доступность выбранной модели.'),
             404:tr('Модель или адрес сервиса недоступны.')}
    # Do not echo remote error bodies: they can contain credentials or user text.
    raise ServiceError(codes.get(response.status_code, trf('Сервис временно недоступен (HTTP {0}).',response.status_code)))


def validate_callback(params, expected_state, previous_client=''):
    if not hmac.compare_digest(params.get('state',''), expected_state):
        raise ServiceError(tr('Неверное состояние ответа авторизации.'))
    if params.get('error'):
        raise ServiceError(tr('Вход отменён или разрешение не выдано.'))
    client = params.get('client_id') or previous_client
    if not client or client == 'dynamic_agent_client':
        raise ServiceError(tr('OpenAI не вернул регистрацию приложения.'))
    if previous_client and client != previous_client:
        raise ServiceError(tr('Регистрация не соответствует выбранному подключению.'))
    if not params.get('code'):
        raise ServiceError(tr('OpenAI не вернул код авторизации.'))
    return client


class ChatGPTAuth:
    def __init__(self, store, host_id):
        self.store, self.host_id = store, host_id
        self.lock = threading.RLock()
        self.cancel = threading.Event()

    def profile(self):
        return self.store.vault.read().get('chatgpt', {})

    def discovery(self):
        response = requests.get(AUTH+'/.well-known/openid-configuration', timeout=(5,15))
        check_response(response)
        config = response.json()
        if config.get('issuer') != AUTH:
            raise ServiceError(tr('Не удалось проверить сервер авторизации OpenAI.'))
        for field in ('jwks_uri','authorization_endpoint','token_endpoint'):
            if urlparse(config.get(field,'')).scheme != 'https' or urlparse(config[field]).netloc != 'auth.openai.com':
                raise ServiceError(tr('Неожиданный адрес сервера авторизации.'))
        return config

    def sign_in(self, new_account=False):
        with self.lock:
            self.cancel.clear()
            previous = {} if new_account else self.profile()
            config = self.discovery()
            state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            result = {}

            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    parsed = urlparse(self.path)
                    if parsed.path != '/auth/callback':
                        self.send_error(404)
                        return
                    raw = parse_qs(parsed.query)
                    if any(len(v)!=1 for v in raw.values()) or not hmac.compare_digest(raw.get('state',[''])[0],state):
                        self.send_error(400)
                        return
                    result.update({k:v[0] for k,v in raw.items()})
                    content = ('<!doctype html><meta charset="utf-8"><title>Lexora</title>'
                               '<h2>Ответ получен</h2><p>Вернись в Lexora для проверки подключения.</p>').encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type','text/html; charset=utf-8')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Content-Length',str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)

            with HTTPServer(('127.0.0.1',0),Callback) as server:
                server.timeout = .3
                redirect = f'http://127.0.0.1:{server.server_port}/auth/callback'
                # The old client may still be registered under the previous name.
                # Renew branding only on a user-initiated sign-in; preserve the
                # active credentials until the new registration is verified.
                client = previous.get('client_id','') if previous.get('app_name')==APP_NAME else ''
                params = {'client_id':client or 'dynamic_agent_client','ext_agent_host_id':self.host_id,
                          'response_type':'code','redirect_uri':redirect,'scope':SCOPE,'resource':RESOURCE,
                          'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':challenge}
                if not client:
                    params['agent_name_hint'] = APP_NAME
                if client and previous.get('id_token'):
                    params['id_token_hint'] = previous['id_token']
                if client and previous.get('email'):
                    params['login_hint'] = previous['email']
                if not webbrowser.open(config['authorization_endpoint']+'?'+urlencode(params)):
                    raise ServiceError(tr('Не удалось открыть браузер для входа.'))
                deadline = time.monotonic()+180
                while not result and time.monotonic()<deadline and not self.cancel.is_set():
                    server.handle_request()
                if not result:
                    raise ServiceError(tr('Вход отменён или истекло время ожидания. Можно повторить.'))
            issued = validate_callback(result,state,client)
            response = requests.post(config['token_endpoint'], data={'grant_type':'authorization_code',
                'client_id':issued,'code':result['code'],'code_verifier':verifier,
                'redirect_uri':redirect,'resource':RESOURCE}, timeout=(5,20))
            check_response(response)
            tokens = response.json()
            claims = self.verify_id(tokens.get('id_token',''),issued,nonce,config)
            if previous.get('subject') and claims['sub'] != previous['subject']:
                raise ServiceError(tr('Получен другой аккаунт. Используй «Другой аккаунт».'))
            if not tokens.get('access_token') or str(tokens.get('token_type','')).casefold()!='bearer':
                raise ServiceError(tr('Не получен доступ для запросов.'))
            profile = dict(tokens,client_id=issued,app_name=APP_NAME,subject=claims['sub'],email=claims.get('email',''),
                           scopes=tokens.get('scope','').split(),expires_at=time.time()+int(tokens.get('expires_in',3600)))
            self.store.vault.set('chatgpt',profile)
            return profile

    @staticmethod
    def verify_id(token, client, nonce, config):
        try:
            key = jwt.PyJWKClient(config['jwks_uri'],timeout=15).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token,key,algorithms=['RS256'],audience=client,issuer=AUTH,
                                options={'require':['exp','iss','aud','sub','nonce']})
            if not hmac.compare_digest(str(claims.get('nonce','')),nonce):
                raise ValueError('nonce')
            return claims
        except Exception:
            raise ServiceError(tr('Не удалось проверить подпись или параметры аккаунта OpenAI.')) from None

    def access_token(self):
        with self.lock:
            profile = self.profile()
            if PLAN_SCOPE not in profile.get('scopes',[]) or not profile.get('access_token'):
                raise ServiceError(tr('Подключи ChatGPT и разреши использовать подписку в настройках.'))
            if profile.get('expires_at',0)>time.time()+90:
                return profile['access_token']
            if not profile.get('refresh_token'):
                raise ServiceError(tr('Подключение истекло. Выполни вход заново.'))
            response = requests.post(AUTH+'/api/accounts/oauth/token',data={
                'grant_type':'refresh_token','client_id':profile['client_id'],
                'refresh_token':profile['refresh_token'],'resource':RESOURCE},timeout=(5,20))
            check_response(response)
            replacement = response.json()
            if not replacement.get('access_token'):
                raise ServiceError(tr('Не удалось обновить подключение. Войди заново.'))
            profile.update(replacement)
            if 'scope' in replacement:
                profile['scopes'] = replacement['scope'].split()
            profile['expires_at'] = time.time()+int(replacement.get('expires_in',3600))
            self.store.vault.set('chatgpt',profile)
            if PLAN_SCOPE not in profile.get('scopes',[]):
                raise ServiceError(tr('Использование подписки больше не разрешено.'))
            return profile['access_token']

    def sign_out(self):
        with self.lock:
            profile = self.profile()
            confirmed = not bool(profile.get('refresh_token'))
            try:
                if profile.get('refresh_token'):
                    endpoint = self.discovery().get('revocation_endpoint','')
                    if urlparse(endpoint).scheme=='https' and urlparse(endpoint).netloc=='auth.openai.com':
                        response = requests.post(endpoint,data={'token':profile['refresh_token'],
                            'token_type_hint':'refresh_token','client_id':profile['client_id']},timeout=(5,10))
                        confirmed = response.status_code==200
            except Exception:
                confirmed = False
            finally:
                self.store.vault.set('chatgpt',{k:profile[k] for k in ('client_id','subject','email','app_name') if k in profile})
            return confirmed
