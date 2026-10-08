import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs,urlparse,urlencode
from urllib.request import urlopen
from unittest.mock import patch,Mock
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from windowwords.auth import AUTH,ChatGPTAuth,ServiceError,PLAN_SCOPE
from windowwords.storage import Store


class OAuthTests(unittest.TestCase):
    def test_loopback_pkce_and_signature(self):
        key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        config = {'issuer':AUTH,'authorization_endpoint':AUTH+'/api/accounts/authorize',
                  'token_endpoint':AUTH+'/api/accounts/oauth/token','jwks_uri':AUTH+'/jwks'}
        captured = {}
        def browser(url):
            params = parse_qs(urlparse(url).query)
            captured.update(params)
            callback = params['redirect_uri'][0]+'?'+urlencode({'state':params['state'][0],
                                                            'code':'test-code','client_id':'oaiapp_test'})
            threading.Thread(target=lambda:urlopen(callback,timeout=5).read(),daemon=True).start()
            return True
        def token_post(url,data,timeout):
            self.assertEqual(data['client_id'],'oaiapp_test')
            self.assertEqual(data['redirect_uri'],captured['redirect_uri'][0])
            import hashlib,base64
            challenge = base64.urlsafe_b64encode(hashlib.sha256(data['code_verifier'].encode()).digest()).rstrip(b'=').decode()
            self.assertEqual(challenge,captured['code_challenge'][0])
            token = jwt.encode({'iss':AUTH,'aud':'oaiapp_test','sub':'test-user','email':'test@example.invalid',
                                'nonce':captured['nonce'][0],'exp':int(time.time())+300},key,algorithm='RS256')
            return Mock(ok=True,json=lambda:{'id_token':token,'access_token':'test-token',
                'refresh_token':'test-refresh','token_type':'Bearer','expires_in':3600,'scope':'openid '+PLAN_SCOPE})
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder))
            auth = ChatGPTAuth(store,'urn:uuid:test-host')
            with patch.object(auth,'discovery',return_value=config),patch('windowwords.auth.webbrowser.open',side_effect=browser),\
                 patch('windowwords.auth.requests.post',side_effect=token_post),\
                 patch('windowwords.auth.jwt.PyJWKClient') as jwks:
                jwks.return_value.get_signing_key_from_jwt.return_value.key = key.public_key()
                profile = auth.sign_in()
            self.assertEqual(profile['subject'],'test-user')
            self.assertIn(PLAN_SCOPE,profile['scopes'])
            self.assertEqual(captured['ext_agent_host_id'],['urn:uuid:test-host'])
            self.assertEqual(auth.access_token(),'test-token')

    def test_invalid_audience_and_nonce(self):
        key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        config = {'jwks_uri':AUTH+'/jwks'}
        for changes in ({'aud':'attacker'},{'nonce':'attacker'},{'iss':'https://attacker.invalid'}):
            claims = dict(iss=AUTH,aud='client',nonce='nonce',sub='user',exp=int(time.time())+300)
            claims.update(changes)
            token = jwt.encode(claims,key,algorithm='RS256')
            with patch('windowwords.auth.jwt.PyJWKClient') as jwks:
                jwks.return_value.get_signing_key_from_jwt.return_value.key = key.public_key()
                with self.assertRaises(ServiceError):
                    ChatGPTAuth.verify_id(token,'client','nonce',config)


if __name__=='__main__':
    unittest.main()
