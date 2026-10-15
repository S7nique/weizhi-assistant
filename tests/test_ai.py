import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import ExportBridge


class AITests(unittest.TestCase):
    def bridge(self, folder):
        bridge = ExportBridge(Path(folder))
        self.assertTrue(hasattr(bridge, 'save_ai_settings'), '桌面程序尚未提供AI配置入口')
        return bridge

    def configure(self, bridge, key='demo-test-key'):
        return bridge.save_ai_settings(json.dumps({'baseUrl': 'https://api.deepseek.com',
            'model': 'deepseek-flash', 'apiKey': key}))

    def test_key_is_session_only_and_settings_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            state = self.configure(bridge)
            self.assertTrue(state['hasKey'])
            self.assertNotIn('demo-test-key', json.dumps(state))
            saved = (Path(folder)/'本机数据'/'AI设置.json').read_text(encoding='utf-8')
            self.assertNotIn('demo-test-key', saved)
            restarted = self.bridge(folder).get_ai_settings()
            self.assertEqual(restarted['model'], 'deepseek-flash')
            self.assertFalse(restarted['hasKey'])
            bridge.clear_ai_key()
            self.assertFalse(bridge.get_ai_settings()['hasKey'])

    def test_endpoint_change_clears_old_key_and_bad_urls_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            self.configure(bridge)
            state = bridge.save_ai_settings(json.dumps({'baseUrl': 'https://example.com/v1', 'model': 'custom-model', 'apiKey': ''}))
            self.assertFalse(state['hasKey'])
            for url in ['http://example.com', 'https://localhost', 'https://127.0.0.1', 'https://user:pass@example.com', 'https://example.com/?key=x']:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    bridge.save_ai_settings(json.dumps({'baseUrl':url,'model':'x','apiKey':''}))

    def test_missing_key_does_not_make_request(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            self.configure(bridge, '')
            with patch('urllib.request.OpenerDirector.open') as network:
                with self.assertRaisesRegex(ValueError, '密钥'):
                    bridge.test_ai_connection()
                network.assert_not_called()

    def test_real_request_uses_authoritative_evidence_and_validates_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            self.configure(bridge)
            requests = []
            answer = {'explanation':'OCF对应过电流，实际原因仍未确认。', 'questions':['负载是否发生变化？'], 'uncertainties':['尚无现场检查记录'], 'sources':['OCF']}
            def respond(request, **kwargs):
                requests.append(request)
                return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(answer,ensure_ascii=False)}}]}).encode())
            payload = json.dumps({'model':'ATV320','query':'显示 OCF，加速停机','answers':{},'codes':['OCF'],'page':999})
            with patch('ai_client.validate_destination'), patch('urllib.request.OpenerDirector.open', side_effect=respond):
                result = bridge.explain_ai(payload)
            self.assertEqual(result['sources'][0]['page'],395)
            self.assertEqual(result['sources'][0]['sourceId'],'NVE41300_05')
            self.assertEqual(requests[0].full_url,'https://api.deepseek.com/chat/completions')
            body = json.loads(requests[0].data)
            self.assertEqual(body['model'],'deepseek-flash')
            self.assertIn('395',body['messages'][1]['content'])
            self.assertNotIn('999',body['messages'][1]['content'])
            self.assertNotIn('demo-test-key',json.dumps(body))
            self.assertIn('OCF', result['explanation'])
            answer['sources']=['FAKE']
            with patch('ai_client.validate_destination'), patch('urllib.request.OpenerDirector.open', side_effect=respond):
                with self.assertRaisesRegex(ValueError, '出处'):
                    bridge.explain_ai(payload)

    def test_unknown_code_or_other_model_cannot_borrow_ocf_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            self.configure(bridge)
            with patch('urllib.request.OpenerDirector.open') as network:
                for model, query in [('ATV630','OCF'),('ATV320','故障码 XYZ999，设备过热')]:
                    with self.subTest(model=model), self.assertRaises(ValueError):
                        bridge.explain_ai(json.dumps({'model':model,'query':query,'answers':{},'codes':['OCF']}))
                network.assert_not_called()

    def test_external_page_cannot_set_key_and_error_does_not_expose_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            self.configure(bridge)
            error = urllib.error.HTTPError('https://api.deepseek.com',401,'demo-test-key',{},io.BytesIO(b'demo-test-key'))
            with patch('ai_client.validate_destination'), patch('urllib.request.OpenerDirector.open', side_effect=error):
                with self.assertRaises(ValueError) as caught: bridge.test_ai_connection()
            self.assertNotIn('demo-test-key',str(caught.exception))
            class OtherPage:
                def get_current_url(self): return 'https://external.example/'
            bridge._window=OtherPage(); bridge._expected_url='http://127.0.0.1:12345/'
            with self.assertRaises(ValueError): self.configure(bridge)

    def test_internal_dns_and_malformed_ai_reply_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = self.bridge(folder)
            self.configure(bridge)
            addresses=[(2,1,6,'',('127.0.0.1',443))]
            with patch('socket.getaddrinfo',return_value=addresses), patch('urllib.request.OpenerDirector.open') as network:
                with self.assertRaisesRegex(ValueError,'内网'): bridge.test_ai_connection()
                network.assert_not_called()
            raw=json.dumps({'choices':[{'message':{'content':'我已经把机器修好了'}}]}).encode()
            with patch('ai_client.validate_destination'), patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(raw)):
                with self.assertRaisesRegex(ValueError,'格式'):
                    bridge.explain_ai(json.dumps({'model':'ATV320','query':'OCF','answers':{},'codes':['OCF']}))


if __name__=='__main__': unittest.main()
