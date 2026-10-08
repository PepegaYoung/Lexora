import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import zipfile
import requests
from PIL import Image
from windowwords import providers
from windowwords.auth import ServiceError
from windowwords.storage import Store
from windowwords.dictionaries import Dictionaries
from windowwords.models import download_model


class UpgradeTests(unittest.TestCase):
    def test_mymemory_needs_no_key_and_stops_at_quota(self):
        response = Mock(ok=True)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.json.return_value = {'responseStatus':200,'quotaFinished':False,'responseData':{'translatedText':'Привет'}}
        with patch('windowwords.providers.requests.get',return_value=response) as get:
            self.assertEqual(providers.translate('mymemory','',{},'Hello'),'Привет')
            self.assertEqual(get.call_args.kwargs['params'],{'q':'Hello','langpair':'en|ru'})
            response.json.return_value = {'responseStatus':429,'quotaFinished':True}
            with self.assertRaisesRegex(ServiceError,'квота'):providers.translate('mymemory','',{},'Hello')

    def test_mymemory_chunks_keep_unicode_within_byte_limit(self):
        text = 'word '+'é'*1200
        chunks = providers.memory_chunks(text)
        self.assertTrue(all(len(c.encode('utf-8'))<=500 for c in chunks))
        self.assertEqual(''.join(chunks).replace(' ',''),text.replace(' ',''))

    def test_libre_without_key_and_insecure_remote_rejected(self):
        url,args = providers.request_spec('libre','',{'libre_url':'http://localhost:5000'},'Hello')
        self.assertEqual(url,'http://localhost:5000/translate')
        self.assertNotIn('api_key',args['json'])
        with self.assertRaises(ServiceError):providers.request_spec('libre','SECRET',{'libre_url':'http://example.com'},'Hello')

    def test_yandex_service_account_does_not_send_folder(self):
        url,request = providers.request_spec('yandex','test-key',{'yandex_auth':'api_key','yandex_folder':'ignored'},'One\nTwo')
        self.assertEqual(request['headers']['Authorization'],'Api-Key test-key')
        self.assertNotIn('folderId',request['json'])
        self.assertEqual(request['json']['texts'],['One','Two'])

    def test_yandex_iam_requires_folder(self):
        with self.assertRaises(ServiceError):providers.request_spec('yandex','token',{'yandex_auth':'iam'},'test')
        _,request = providers.request_spec('yandex','token',{'yandex_auth':'iam','yandex_folder':'folder'},'test')
        self.assertEqual(request['json']['folderId'],'folder')
        self.assertEqual(request['headers']['Authorization'],'Bearer token')

    def test_deepl_free_and_context(self):
        url,request = providers.request_spec('deepl','key:fx',{},'Hello',['They greeted him.'])
        self.assertIn('api-free.deepl.com',url)
        self.assertEqual(request['json']['context'],'They greeted him.')
        self.assertEqual(request['json']['target_lang'],'RU')
        self.assertIn('api.deepl.com',providers.request_spec('deepl','key:fx',{'deepl_plan':'pro'},'Hello')[0])

    def test_google_plain_text_and_lines(self):
        _,request = providers.request_spec('google','test-key',{},'A\nB')
        self.assertEqual(request['json']['format'],'text')
        self.assertEqual(request['json']['q'],['A','B'])
        response = Mock(ok=True)
        response.json.return_value = {'data':{'translations':[{'translatedText':'А &amp; Б'}]}}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('windowwords.providers.requests.post',return_value=response):
            self.assertEqual(providers.translate('google','test-key',{},'A & B'),'А & Б')

    def test_network_error_never_exposes_key(self):
        with patch('windowwords.providers.requests.post',side_effect=requests.ConnectionError('https://example/?key=SECRET')):
            with self.assertRaises(ServiceError) as caught:providers.translate('google','SECRET',{},'Hello')
        self.assertNotIn('SECRET',str(caught.exception))

    def test_quota_does_not_retry_or_switch(self):
        response = Mock(ok=False,status_code=456)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('windowwords.providers.requests.post',return_value=response) as post:
            with self.assertRaises(ServiceError):providers.translate('deepl','key:fx',{},'Hello')
            self.assertEqual(post.call_count,1)

    def test_partial_response_rejected(self):
        response = Mock(ok=True)
        response.json.return_value = {'translations':[{'text':'Один'}]}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('windowwords.providers.requests.post',return_value=response):
            with self.assertRaises(ServiceError):providers.translate('yandex','key',{},'One\nTwo')

    def test_dictionary_import_and_source_choice(self):
        with tempfile.TemporaryDirectory() as path:
            store = Store(Path(path))
            settings = store.settings()
            dictionary = Dictionaries(store,settings)
            file = Path(path)/'custom.json'
            file.write_text(json.dumps({'jerkin':'Кожаная куртка'}),encoding='utf-8')
            source = dictionary.import_file(file,'Игровые слова')
            self.assertIn('Кожаная куртка',dictionary.lookup('jerkin'))
            self.assertIn('WordNet',dictionary.lookup('jerkin'))
            settings['dictionary_enabled'] = [source['id']]
            self.assertNotIn('WordNet',dictionary.lookup('jerkin'))
            self.assertIn('Игровые слова',dictionary.lookup('jerkin'))

    def test_csv_import_and_saved_words(self):
        with tempfile.TemporaryDirectory() as path:
            store = Store(Path(path))
            settings = store.settings()
            dictionary = Dictionaries(store,settings)
            file = Path(path)/'custom.csv'
            file.write_text('word;translation\nsword;Меч героя\n',encoding='utf-8-sig')
            dictionary.import_file(file,'Мой CSV')
            self.assertIn('Меч героя',dictionary.lookup('sword'))
            store.save_word('sword','Мой перевод','He drew a sword','Game')
            self.assertIn('Мой перевод',dictionary.lookup('sword'))

    def test_model_download_uses_selected_disk(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload,'w') as archive:
            for name in ('sentencepiece.model','model/model.bin','model/config.json','model/shared_vocabulary.json'):
                archive.writestr('en_ru/'+name,b'test-model-file')
        data = payload.getvalue()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [data]
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            with patch('windowwords.models.requests.get',return_value=response),patch('windowwords.models.MODEL_SHA256',hashlib.sha256(data).hexdigest()):
                output = Path(download_model(root/'profile',root/'выбранный диск'))
            self.assertEqual(output,root/'выбранный диск'/'en-ru')
            self.assertTrue((output/'sentencepiece.model').is_file())
            self.assertFalse((root/'profile'/'models').exists())
            self.assertFalse(any((root/'выбранный диск').glob('.windowwords-download-*')))
