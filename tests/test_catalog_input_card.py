import sentencepiece,ctranslate2
import ctypes,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlparse,urlencode
from urllib.request import urlopen
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from windowwords import native
from windowwords.auth import AUTH,APP_NAME,ChatGPTAuth,PLAN_SCOPE,ServiceError
from windowwords.card_layout import place_card
from windowwords.core import Box
from windowwords.input_capture import InputCapture,MouseEvent,mouse_key
from windowwords.input_keys import ModifierState,ShortcutGate
from windowwords.model_catalog import parse_catalog
from windowwords.storage import Store
from tests import test_usability as usability

class CatalogInputTests(unittest.TestCase):
    def test_catalog_keeps_account_order_names_and_filters_hidden(self):
        rows={'models':[{'slug':'gpt-6.1-sol','display_name':'GPT-6.1 Sol','visibility':'list'},
                        {'slug':'hidden','visibility':'hide'},
                        {'slug':'gpt-6-luna','visibility':'list'},
                        {'slug':'gpt-6.1-sol','visibility':'list'}]}
        self.assertEqual(parse_catalog(rows,'subscription'),[('gpt-6.1-sol','GPT-6.1 Sol'),('gpt-6-luna','gpt-6-luna')])
    def test_api_catalog_excludes_non_text_and_accepts_new_names(self):
        rows={'data':[{'id':name} for name in ('gpt-next','gpt-image-new','gpt-realtime-new','gpt-audio-new','o5','chat-latest','embedding-new')]}
        self.assertEqual([row[0] for row in parse_catalog(rows,'api')],['gpt-next','o5','chat-latest'])
    def test_empty_malformed_catalog_is_an_error(self):
        for rows in ({},{'models':[]},{'models':'oops'},None):
            with self.assertRaises(ServiceError):parse_catalog(rows,'subscription')
    def test_extra_keys_and_mouse_variants_parse_and_conflict(self):
        for name,vk in [('Alt+Z',0x5A),('Alt+R',0x52),('Num9',0x69),('NumPlus',0x6B),('Semicolon',0xBA),('Mouse4',5),('Ctrl+Mouse5',6)]:
            self.assertEqual(native.parse_hotkey(name)[1],vk)
        with self.assertRaises(ValueError):native.validate_bindings({'one':'Mouse4','two':'mouse4'})
    def test_shortcut_gate_ignores_unrelated_and_consumes_full_press(self):
        calls=[];gate=ShortcutGate(calls.append,{(1,ord('Z')):'study'})
        self.assertFalse(gate.process(ord('R'),True,1))
        self.assertTrue(gate.process(ord('Z'),True,1))
        self.assertTrue(gate.process(ord('Z'),True,1))
        self.assertTrue(gate.process(ord('Z'),False,0))
        self.assertEqual(calls,['study'])
    def test_mouse_shortcut_suspend_and_modifier(self):
        calls=[];gate=ShortcutGate(calls.append,{(0,5):'one',(2,6):'two'})
        gate.single_enabled=False
        self.assertFalse(gate.process(5,True,0))
        self.assertTrue(gate.process(6,True,2))
        self.assertTrue(gate.process(6,False,0))
        self.assertEqual(calls,['two'])
    def test_modifier_state_tracks_both_sides_and_release(self):
        state=ModifierState()
        state.update(0xA2,True);state.update(0xA3,True);state.update(0xA4,True)
        self.assertEqual(state.flags,3)
        state.update(0xA2,False);self.assertEqual(state.flags,3)
        state.update(0xA3,False);self.assertEqual(state.flags,1)
        state.update(0xA4,False);self.assertEqual(state.flags,0)
    def test_native_capture_records_occupied_chord_once(self):
        recorded=[];capture=InputCapture(recorded.append,lambda:None,lambda _:None)
        self.assertTrue(capture.process(ord('Z'),True,1))
        self.assertTrue(capture.process(ord('Z'),True,1))
        self.assertTrue(capture.process(ord('Z'),False,0))
        self.assertFalse(capture.process(ord('R'),True,1))
        self.assertEqual(recorded,['Alt+Z'])
    def test_native_mouse_identity_and_keyboard_fallback_dispatch(self):
        self.assertEqual(mouse_key(0x20B,1<<16),5)
        self.assertEqual(mouse_key(0x20C,2<<16),6)
        self.assertIsNone(mouse_key(0x200,1<<16))
        actions=[];failures=[]
        keys=native.Hotkeys(actions.append,failures.append,{'study':'Alt+Z','region':'Mouse4'},False)
        def key(vk,message):
            event=native.KeyboardEvent(vkCode=vk)
            return keys.keyboard_callback(0,message,ctypes.addressof(event))
        def get_message(*args):
            key(0xA4,0x104)
            self.assertEqual(key(ord('Z'),0x104),1)
            key(0xA4,0x105)
            self.assertEqual(key(ord('Z'),0x105),1)
            event=MouseEvent(mouseData=1<<16)
            self.assertEqual(keys.mouse_callback(0,0x20B,ctypes.addressof(event)),1)
            self.assertEqual(keys.mouse_callback(0,0x20C,ctypes.addressof(event)),1)
            return 0
        with patch.object(native.user,'PeekMessageW'),patch.object(native.user,'GetMessageW',side_effect=get_message),\
             patch.object(native.user,'RegisterHotKey',return_value=False) as register,\
             patch.object(native.user,'SetWindowsHookExW',return_value=101) as hook,\
             patch.object(native.user,'CallNextHookEx',return_value=0),patch.object(native.user,'UnhookWindowsHookEx') as unhook,\
             patch('windowwords.input_capture.modifier_state',return_value=ModifierState()):
            keys.run()
        self.assertEqual(actions,['study','region'])
        self.assertEqual(register.call_count,1)
        self.assertEqual([call.args[0] for call in hook.call_args_list],[13,14])
        self.assertEqual(unhook.call_count,2)
    def test_card_flips_above_without_covering_source(self):
        bounds=Box(0,0,1920,1080);anchor=Box(900,1030,100,25)
        card=place_card(bounds,anchor,440,440)
        self.assertLessEqual(card.y+card.h,anchor.y-16)
        self.assertGreaterEqual(card.y,12)
    def test_card_below_with_room_and_negative_monitor(self):
        bounds=Box(-1920,-100,1920,1080);anchor=Box(-1600,20,70,25)
        card=place_card(bounds,anchor,440,440)
        self.assertEqual(card.y,61)
        self.assertGreaterEqual(card.x,bounds.x+12)
        self.assertLessEqual(card.x+card.w,-12)
    def test_short_monitor_uses_side_or_reduces_without_covering_word(self):
        bounds=Box(0,0,800,600);anchor=Box(370,290,60,20)
        card=place_card(bounds,anchor,440,550)
        self.assertTrue(card.y+card.h<=anchor.y-16 or card.y>=anchor.y+anchor.h+16 or card.x+card.w<=anchor.x or card.x>=anchor.x+anchor.w)
        self.assertGreaterEqual(card.y,12);self.assertLessEqual(card.y+card.h,588)
    def test_previous_default_card_migrates_custom_size_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));settings=store.settings()
            settings.update(card_width=560,card_height=600);store.save_settings(settings)
            self.assertEqual((store.settings()['card_width'],store.settings()['card_height']),(440,440))
            settings.update(card_width=700,card_height=800);store.save_settings(settings)
            self.assertEqual(store.settings()['card_width'],700)
    def test_legacy_oauth_registration_renamed_only_after_validated_sign_in(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder))
            old={'client_id':'oaiapp_old','subject':'user','access_token':'old-placeholder','id_token':'old-hint'}
            store.vault.set('chatgpt',old)
            auth=ChatGPTAuth(store,'urn:uuid:test-host');captured={}
            config={'issuer':AUTH,'authorization_endpoint':AUTH+'/api/accounts/authorize','token_endpoint':AUTH+'/api/accounts/oauth/token'}
            def browser(url):
                params=parse_qs(urlparse(url).query);captured.update(params)
                callback=params['redirect_uri'][0]+'?'+urlencode({'state':params['state'][0],'code':'test-code','client_id':'oaiapp_new'})
                threading.Thread(target=lambda:urlopen(callback,timeout=5).read(),daemon=True).start()
                return True
            with patch.object(auth,'discovery',return_value=config),patch('windowwords.auth.webbrowser.open',side_effect=browser),\
                 patch('windowwords.auth.requests.post',return_value=Mock(ok=True,json=lambda:{'access_token':'new-placeholder','token_type':'Bearer','scope':PLAN_SCOPE})),\
                 patch.object(auth,'verify_id',return_value={'sub':'user'}):
                profile=auth.sign_in()
            self.assertEqual(captured['client_id'],['dynamic_agent_client'])
            self.assertEqual(captured['agent_name_hint'],[APP_NAME])
            self.assertNotIn('id_token_hint',captured)
            self.assertEqual(profile['app_name'],APP_NAME)
            self.assertEqual(profile['client_id'],'oaiapp_new')
    def test_cancelled_brand_registration_keeps_active_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder));old={'client_id':'oaiapp_old','access_token':'placeholder'}
            store.vault.set('chatgpt',old);auth=ChatGPTAuth(store,'urn:uuid:test-host')
            with patch.object(auth,'discovery',return_value={'authorization_endpoint':AUTH+'/authorize'}),patch('windowwords.auth.webbrowser.open',return_value=False):
                with self.assertRaises(ServiceError):auth.sign_in()
            self.assertEqual(auth.profile(),old)

class CatalogCardUITests(unittest.TestCase):
    setUpClass=classmethod(usability.UsabilityTests.setUpClass.__func__)
    setUp=usability.UsabilityTests.setUp
    tearDown=usability.UsabilityTests.tearDown
    record=usability.UsabilityTests.record
    def connected(self):
        self.window.model_connection_ready=Mock(return_value=True)
        self.window.task=lambda fn,done,failed=None:done(fn())
        self.window.translator.models=Mock(return_value=[('gpt-6.1-sol','GPT-6.1 Sol'),('gpt-6-luna','GPT-6 Luna')])
        self.window.provider.setCurrentIndex(self.window.provider.findData('api'))
    def test_provider_change_autoloads_catalog_noneditable_and_preserves_choice(self):
        self.connected()
        self.assertFalse(self.window.model_pick.isEditable())
        self.assertEqual(self.window.model_pick.count(),2)
        self.window.model_pick.setCurrentIndex(1)
        self.window.get_models()
        self.assertEqual(self.window.model_pick.currentData(),'gpt-6-luna')
    def test_stale_catalog_refresh_and_no_extra_requests_inside_ttl(self):
        self.connected();fetch=self.window.translator.models
        self.window.get_models(force=False);self.assertEqual(fetch.call_count,1)
        rows,updated=self.window.model_catalogs['api']
        self.window.model_catalogs['api']=(rows,updated-301)
        self.window.get_models(force=False);self.assertEqual(fetch.call_count,2)
    def test_new_connection_invalidates_late_response(self):
        self.window.model_connection_ready=Mock(return_value=True)
        pending=[];self.window.task=lambda fn,done,failed=None:pending.append(done)
        self.window.provider.setCurrentIndex(self.window.provider.findData('api'))
        old=pending.pop();self.window.invalidate_models('api');self.window.get_models()
        old([('old-account-model','Old')])
        self.assertEqual(self.window.model_pick.count(),0)
        pending.pop()([('new-model','New')]);self.assertEqual(self.window.model_pick.currentData(),'new-model')
    def test_missing_previous_model_requires_choice_and_network_error_keeps_list(self):
        self.window.settings['models']['api']='removed'
        self.connected();self.assertEqual(self.window.model_pick.currentIndex(),-1)
        self.assertFalse(self.window.apply_settings())
        self.window.model_pick.setCurrentIndex(0)
        self.window.task=lambda fn,done,failed=None:failed('Нет сети')
        self.window.get_models();self.assertEqual(self.window.model_pick.count(),2)
        self.assertIn('предыдущий список',self.window.model_status.text())
    def test_mouse_and_occupied_alt_chords_are_recorded(self):
        for vk,name in ((Qt.Key.Key_Z,'Alt+Z'),(Qt.Key.Key_R,'Alt+R')):
            field=self.record();QTest.keyClick(field,vk,Qt.KeyboardModifier.AltModifier)
            QTest.keyRelease(field,Qt.Key.Key_Alt);self.app.processEvents()
            self.assertEqual(field.text(),name)
        field=self.record();QTest.mouseClick(field,Qt.MouseButton.BackButton);self.app.processEvents()
        self.assertEqual(field.text(),'Mouse4')
        field.begin_add();QTest.mouseClick(field,Qt.MouseButton.ForwardButton,Qt.KeyboardModifier.ControlModifier)
        QTest.keyRelease(field,Qt.Key.Key_Control);self.app.processEvents()
        self.assertEqual(field.text(),'Mouse4; Ctrl+Mouse5')
    def test_late_capture_signal_does_not_assign_in_new_session(self):
        field=self.record();old=field.capture_revision;field.finish();field.begin()
        field.nativeRecorded.emit(old,'Alt+Z');self.app.processEvents()
        self.assertEqual(field.text(),'Alt+Q')
        self.assertTrue(field.recording)
    def test_native_worker_delivers_recording_on_gui_queue(self):
        field=self.record();revision=field.capture_revision
        worker=threading.Thread(target=lambda:field.nativeRecorded.emit(revision,'Alt+Z'))
        worker.start();worker.join()
        self.assertEqual(field.text(),'Alt+Q')
        self.app.processEvents()
        self.assertEqual(field.text(),'Alt+Z')
        field.nativeFinished.emit(revision);self.app.processEvents()
        self.assertFalse(field.recording)
    def test_compact_card_buttons_and_bottom_placement(self):
        self.window.monitors=[{'x':0,'y':0,'w':1920,'h':1080,'name':'test'}]
        self.window.monitor=self.window.monitors[0]
        with patch('windowwords.native.cursor',return_value=(960,1040)),patch('windowwords.native.place') as place:
            self.window.show_card('sword','She drew her sword.')
        box=place.call_args.args[1]
        self.assertLessEqual(box.y+box.h,1024)
        self.assertEqual(self.window.settings['card_width'],440)
        titles=[button.text() for button in self.window.card.findChildren(QPushButton)]
        self.assertFalse(any('Викисловаре' in title for title in titles))
        self.assertIn('Сохранить',titles)

if __name__=='__main__':unittest.main()
