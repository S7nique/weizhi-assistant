import json
import tempfile
import threading
import unittest
import urllib.request
from urllib.parse import quote
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop import make_server, ExportBridge

class DesktopTests(unittest.TestCase):
    def test_server_serves_only_packaged_routes(self):
        server=make_server()
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(url+'/api/catalog') as response:
                catalog=json.load(response)
                self.assertEqual(len(catalog['cases']),9)
            with urllib.request.urlopen(url+'/') as response:
                self.assertIn('维知助手',response.read().decode('utf-8'))
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url+quote('/../../下载来源与核验.json'))
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url+'/api/catalog',headers={'Host':'external.example'}))
            self.assertEqual(error.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

    def test_native_export_writes_chinese_without_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=ExportBridge(Path(folder))
            saved=bridge.export_order('# 演示工单\n未确认','md')
            path=Path(saved['path'])
            self.assertTrue(path.is_relative_to(Path(folder)))
            self.assertEqual(path.read_text(encoding='utf-8'),'# 演示工单\n未确认')
            with self.assertRaises(ValueError):bridge.export_order('x','../evil')
            with self.assertRaises(ValueError):bridge.export_order('not json','json')

    def test_history_persists_and_external_page_cannot_export(self):
        import uuid
        with tempfile.TemporaryDirectory() as folder:
            bridge=ExportBridge(Path(folder))
            order={'id':str(uuid.uuid4()),'candidates':[],'answers':{},'query':'演示'}
            bridge.save_order(json.dumps(order))
            self.assertEqual(ExportBridge(Path(folder)).get_history()[0]['query'],'演示')
            class OtherPage:
                def get_current_url(self):return 'https://external.example/'
            bridge._window=OtherPage();bridge._expected_url='http://127.0.0.1:12345/'
            with self.assertRaises(ValueError):bridge.export_order('x','md')

if __name__=='__main__':unittest.main()
