import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from windowwords.web_translation import WebTranslator,extract
from windowwords.translation import Translator
from windowwords.storage import Store
from windowwords.auth import ServiceError


def response(payload,status=200):
    r=Mock(status_code=status,ok=200<=status<300)
    r.json.return_value=payload
    r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False)
    return r


class WebTests(unittest.TestCase):
    def test_yandex_response_and_blank_rejection(self):
        self.assertEqual(extract('yandex_web',{'code':200,'text':['Привет','Мир']}),'Привет\nМир')
        for payload in ({'code':200,'text':[]},{'code':200,'text':[None]},{'code':500,'text':['oops']}):
            with self.assertRaises(ServiceError):extract('yandex_web',payload)

    def test_removed_providers_send_no_network_requests(self):
        client=WebTranslator();client.session.get=Mock();client.session.post=Mock()
        for provider in ('google_web','google','libre'):
            with self.assertRaises(ServiceError):client.translate(provider,'Hello')
        client.session.get.assert_not_called();client.session.post.assert_not_called()

    def test_yandex_anonymous_request_has_no_credentials(self):
        client=WebTranslator()
        client.session.post=Mock(return_value=response({'code':200,'text':['Привет']}))
        self.assertEqual(client.translate('yandex_web','Hello'),'Привет')
        args=client.session.post.call_args.kwargs
        self.assertEqual(args['params']['lang'],'en-ru')
        self.assertNotIn('key',args['params'])
        self.assertNotIn('Authorization',client.session.headers)

    def test_service_rejection_stops_without_retry(self):
        for status in (403,429):
            client=WebTranslator()
            client.session.post=Mock(return_value=response({},status))
            with self.assertRaisesRegex(ServiceError,'ограничил'):client.translate('yandex_web','Hello')
            self.assertEqual(client.session.post.call_count,1)

    def test_captcha_html_is_not_a_translation(self):
        client=WebTranslator()
        r=response({});r.json.side_effect=ValueError('CAPTCHA')
        client.session.post=Mock(return_value=r)
        with self.assertRaisesRegex(ServiceError,'проверку'):client.translate('yandex_web','Hello')
        self.assertEqual(client.session.post.call_count,1)

    def test_cancellation_during_pacing_sends_nothing(self):
        client=WebTranslator();client.last_request['yandex_web']=10
        client.session.get=Mock()
        with patch('windowwords.web_translation.time.monotonic',return_value=10.1):
            with self.assertRaises(ServiceError):client.translate('yandex_web','Hello',cancel=lambda:True)
        client.session.get.assert_not_called()

    def test_request_pacing_and_network_error_do_not_echo_source(self):
        client=WebTranslator();client.last_request['yandex_web']=10
        client.session.post=Mock(side_effect=requests.ConnectionError('secret in request URL'))
        with patch('windowwords.web_translation.time.monotonic',side_effect=[10.1,11.1,11.1]),patch('windowwords.web_translation.time.sleep') as sleep:
            with self.assertRaises(ServiceError) as caught:client.translate('yandex_web','private phrase')
        sleep.assert_called_once()
        self.assertNotIn('secret',str(caught.exception))
        self.assertNotIn('private phrase',str(caught.exception))

    def test_translator_caches_without_reading_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));settings=store.settings();settings['provider']='yandex_web'
            store.vault.read=Mock(side_effect=AssertionError('Credentials must not be read'))
            translator=Translator(store,None);translator.web.translate=Mock(return_value='Привет')
            self.assertEqual(translator.translate(settings,'Hello')[0],'Привет')
            self.assertEqual(translator.translate(settings,'Hello')[1],'кэш')
            self.assertEqual(translator.web.translate.call_count,1)

    def test_oversized_input_is_rejected_before_network(self):
        client=WebTranslator();client.session.get=Mock()
        with self.assertRaisesRegex(ServiceError,'4000'):client.translate('yandex_web','a'*4001)
        client.session.get.assert_not_called()
