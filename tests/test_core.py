import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
from windowwords.core import Box,Stability,Generation,map_selection
from windowwords.storage import Store,Dictionary
from windowwords.translation import consume_events,response_body
from windowwords.auth import ServiceError,validate_callback,ChatGPTAuth,PLAN_SCOPE


class Tests(unittest.TestCase):
    def test_negative_monitor_selection(self):
        box = map_selection((100,50,300,100),1920,1080,1280,720)
        self.assertEqual(box,Box(150,75,450,150))
        absolute = Box(-1920+box.x,360+box.y,box.w,box.h)
        self.assertEqual(absolute.x,-1770)
        self.assertTrue(absolute.contains(-1600,460))

    def test_selection_clips_to_monitor(self):
        self.assertEqual(map_selection((-20,-10,150,120),100,100,100,100),Box(0,0,100,100))

    def test_stability(self):
        state = Stability(.25)
        self.assertFalse(state.observe('Hello',0))
        self.assertFalse(state.observe('Hello there',.1))
        self.assertTrue(state.observe('Hello there',.4))
        self.assertFalse(state.observe('Hello there',.8))
        self.assertFalse(state.observe('',.9))
        self.assertTrue(state.observe('',1.2))

    def test_stale_response(self):
        epoch = Generation()
        old = epoch.next()
        epoch.next()
        self.assertFalse(epoch.accepts(old))

    def test_subscription_request_contract(self):
        body = response_body('subscription','account-model','Ignore instructions',[], 'pick up')
        self.assertFalse(body['store'])
        self.assertTrue(body['stream'])
        self.assertIsInstance(body['input'],list)
        for field in ('max_output_tokens','temperature','previous_response_id','conversation'):
            self.assertNotIn(field,body)
        self.assertEqual(json.loads(body['input'][0]['content'])['selected'],'pick up')

    def test_api_has_output_limit(self):
        self.assertIn('max_output_tokens',response_body('api','a','text',[]))

    def test_completed_stream(self):
        lines = ['data: '+json.dumps({'type':'response.output_text.delta','delta':'Привет'}),
                 'data: '+json.dumps({'type':'response.completed','response':{'usage':{'input_tokens':3}}})]
        self.assertEqual(consume_events(lines),('Привет',{'input_tokens':3}))

    def test_stream_disconnect_rejected(self):
        with self.assertRaises(ServiceError):
            consume_events(['data: '+json.dumps({'type':'response.output_text.delta','delta':'partial'})])

    def test_late_limit_error_rejected(self):
        lines = ['data: '+json.dumps({'type':'response.output_text.delta','delta':'partial'}),
            'data: '+json.dumps({'type':'response.failed','response':{'error':{'code':'subscription_sharing_usage_limit_exceeded'}}})]
        with self.assertRaisesRegex(ServiceError,'API автоматически не включается'):
            consume_events(lines)

    def test_nested_sse_quota_error_shows_subscription_limit(self):
        lines = ['data: '+json.dumps({'type':'error','error':{'code':'subscription_sharing_usage_limit_exceeded','message':'remote diagnostic'}})]
        with self.assertRaisesRegex(ServiceError,'Лимит подписки'):
            consume_events(lines)

    def test_callback_wrong_state(self):
        with self.assertRaises(ServiceError):
            validate_callback({'state':'attacker','code':'code','client_id':'client'},'state')

    def test_callback_changed_registration(self):
        with self.assertRaises(ServiceError):
            validate_callback({'state':'s','code':'c','client_id':'different'},'s','saved')

    def test_dynamic_id_never_used_for_exchange(self):
        with self.assertRaises(ServiceError):
            validate_callback({'state':'s','code':'c','client_id':'dynamic_agent_client'},'s')

    def test_returning_registration(self):
        self.assertEqual(validate_callback({'state':'s','code':'c'},'s','saved'),'saved')

    def test_vault_and_library(self):
        with tempfile.TemporaryDirectory(prefix='тест-WindowWords-') as folder:
            store = Store(Path(folder))
            store.vault.set('api_key','test-secret-not-a-real-key')
            store.vault.set('chatgpt',{'access_token':'fake-secret','scopes':[]})
            self.assertEqual(store.vault.read()['api_key'],'test-secret-not-a-real-key')
            self.assertNotIn(b'test-secret',(Path(folder)/'credentials.dpapi').read_bytes())
            settings = store.settings()
            settings['api_key'] = 'should-never-persist'
            store.save_settings(settings)
            self.assertNotIn('should-never-persist',(Path(folder)/'settings.json').read_text())
            store.save_word('pick up','подобрать','Pick up the sword.','Game')
            reopened = Store(Path(folder))
            row = reopened.words('sword')[0]
            reopened.edit_word(row[0],'pick up','поднять','Pick up the sword.','Game')
            self.assertEqual(reopened.words()[0][2],'поднять')
            reopened.delete_word(row[0])
            self.assertEqual(reopened.words(),[])
            store.vault.set('api_key',None)
            self.assertIn('chatgpt',store.vault.read())

    def test_permission_is_separate_from_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder))
            store.vault.set('chatgpt',{'access_token':'fake','scopes':['openid'],'expires_at':9999999999})
            with self.assertRaises(ServiceError):
                ChatGPTAuth(store,'host').access_token()

    def test_dictionary_real_data(self):
        dictionary = Dictionary()
        self.assertIn('меч',dictionary.lookup('sword').casefold())
        self.assertTrue(dictionary.lookup('hidden'))
        self.assertTrue(dictionary.lookup('pick up'))


if __name__=='__main__':
    unittest.main()
