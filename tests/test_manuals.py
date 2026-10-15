import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sys
from pypdf import PdfWriter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop import ExportBridge
FIXTURE=Path(__file__).parent/'fixtures/manual_demo.pdf'

class ManualTests(unittest.TestCase):
    def bridge(self,folder,chosen=FIXTURE):
        bridge=ExportBridge(Path(folder))
        self.assertTrue(hasattr(bridge,'choose_manual_file'),'缺少PDF手册选择与导入功能')
        class Window:
            def get_current_url(self):return 'http://127.0.0.1:12345/'
            def create_file_dialog(self,**kwargs):return (str(chosen),) if chosen else None
        bridge._window=Window();bridge._expected_url='http://127.0.0.1:12345/'
        return bridge

    def import_fixture(self,bridge,model='DEMO-100'):
        picked=bridge.choose_manual_file()
        self.assertNotIn('path',picked)
        return bridge.import_manual(json.dumps({'selectionId':picked['selectionId'],'title':'模拟测试手册','deviceModel':model,'edition':'1.0'}))

    def search(self,bridge,manual_id,query='E202'):
        return bridge.search_manuals(json.dumps({'manualId':manual_id,'query':query}))

    def test_import_search_persists_pdf_page_and_original_stays_unchanged(self):
        original=FIXTURE.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder);item=self.import_fixture(bridge)['manual']
            self.assertEqual(item['pageCount'],2);self.assertEqual(item['textPageCount'],2)
            self.assertNotIn('path',item)
            results=self.search(bridge,item['id'])
            self.assertEqual(results['candidates'][0]['page'],2)
            self.assertIn('温升',results['candidates'][0]['quote'])
            self.assertEqual(results['deviceModel'],'DEMO-100')
            again=self.bridge(folder)
            self.assertEqual(again.list_manuals()[0]['id'],item['id'])
            self.assertEqual(self.search(again,item['id'],'温升')['candidates'][0]['page'],2)
            self.assertEqual(FIXTURE.read_bytes(),original)

    def test_duplicate_is_not_added_and_archive_restore_is_reversible(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder);item=self.import_fixture(bridge)['manual']
            repeated=self.import_fixture(bridge)
            self.assertTrue(repeated['duplicate']);self.assertEqual(len(bridge.list_manuals()),1)
            bridge.set_manual_archived(item['id'],True)
            self.assertEqual(bridge.list_manuals(),[])
            with self.assertRaises(ValueError):self.search(bridge,item['id'])
            self.assertTrue(bridge.list_manuals(True)[0]['archived'])
            bridge.set_manual_archived(item['id'],False)
            self.assertTrue(self.search(bridge,item['id'])['candidates'])

    def test_cancel_invalid_token_and_scan_pdf_fail_without_false_success(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder,None)
            self.assertTrue(bridge.choose_manual_file()['cancelled'])
            with self.assertRaises(ValueError):
                bridge.import_manual(json.dumps({'selectionId':'forged','path':str(FIXTURE),'title':'x','deviceModel':'x','edition':'1'}))
            blank=Path(folder)/'scan.pdf';writer=PdfWriter();writer.add_blank_page(595,842);writer.write(blank)
            bridge=self.bridge(folder,blank)
            with self.assertRaisesRegex(ValueError,'OCR|文字识别'):self.import_fixture(bridge)
            self.assertEqual(bridge.list_manuals(),[])

    def test_pdf_missing_words_and_sql_like_query_do_not_invent_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder);item=self.import_fixture(bridge)['manual']
            self.assertEqual(self.search(bridge,item['id'],'不存在的词ZZ999')['candidates'],[])
            self.assertEqual([h['page'] for h in self.search(bridge,item['id'],'温升90摄氏度')['candidates']],[2])
            self.assertEqual([h['page'] for h in self.search(bridge,item['id'],'温升 90')['candidates']],[2])
            self.assertEqual(self.search(bridge,item['id'],"' OR 1=1 --")['candidates'],[])
            with self.assertRaises(ValueError):self.search(bridge,'../../secret','E202')

    def test_manual_ai_rebuilds_quotes_from_store_and_checks_citations(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder);item=self.import_fixture(bridge)['manual']
            hit=self.search(bridge,item['id'])['candidates'][0]
            bridge.save_ai_settings(json.dumps({'baseUrl':'https://api.deepseek.com','model':'deepseek-flash','apiKey':'mock-only-key'}))
            answer={'explanation':'这是一条测试原文，实际原因未确认。','questions':[],'uncertainties':['未现场检查'],'sources':[hit['id']]}
            requests=[]
            def respond(req,**kwargs):
                requests.append(req)
                return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(answer,ensure_ascii=False)}}]}).encode())
            payload=json.dumps({'manualId':item['id'],'query':'E202','passageIds':[hit['id']],'quote':'伪造的已修复结论','page':99})
            with patch('ai_client.validate_destination'),patch('urllib.request.OpenerDirector.open',side_effect=respond):
                result=bridge.explain_manual_search(payload)
            self.assertEqual(result['sources'][0]['page'],2)
            self.assertIn('E202',result['sources'][0]['quote'])
            self.assertNotIn('伪造的已修复结论',json.loads(requests[0].data)['messages'][1]['content'])
            answer['sources']=['fake-reference']
            with patch('ai_client.validate_destination'),patch('urllib.request.OpenerDirector.open',side_effect=respond):
                with self.assertRaisesRegex(ValueError,'出处'):bridge.explain_manual_search(payload)
            bridge.set_manual_archived(item['id'],True)
            with self.assertRaises(ValueError):bridge.explain_manual_search(payload)

    def test_external_page_cannot_choose_import_or_search_private_manuals(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder)
            class Other:
                def get_current_url(self):return 'https://external.example/'
            bridge._window=Other()
            for call in [bridge.choose_manual_file,bridge.list_manuals,lambda:bridge.search_manuals('{}')]:
                with self.assertRaises(ValueError):call()

    def test_different_manual_scopes_and_partial_scan_pages(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder);original=self.import_fixture(bridge)['manual']
            second=Path(folder)/'version2.pdf';writer=PdfWriter();writer.add_page(PdfReader(FIXTURE).pages[0]);writer.add_blank_page(595,842);writer.write(second)
            newer=self.import_fixture(self.bridge(folder,second),'OTHER-200')['manual']
            self.assertNotEqual(newer['id'],original['id'])
            self.assertEqual(newer['unreadablePageCount'],1)
            self.assertEqual(self.search(bridge,newer['id'],'E202')['candidates'],[])
            self.assertEqual(self.search(bridge,original['id'],'E202')['candidates'][0]['page'],2)

    def test_password_protected_pdf_does_not_create_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            writer=PdfWriter();writer.add_blank_page(595,842);writer.encrypt('test-password')
            encrypted=Path(folder)/'encrypted.pdf';writer.write(encrypted)
            bridge=self.bridge(folder,encrypted)
            with self.assertRaisesRegex(ValueError,'密码'):self.import_fixture(bridge)
            self.assertEqual(bridge.list_manuals(),[])

    def test_pdf_double_glyph_codes_are_normalized_only_in_index(self):
        from manual_library import normalized
        self.assertIn('ocf',normalized('[过电流]OOCCFF\n可能原因'))
        self.assertIn('slf1',normalized('[通信故障]SSLLFF11'))
        self.assertIn('abc123',normalized('ABC123'))
        self.assertIn('aabb12',normalized('AABB12'))

    def test_english_words_after_alarm_code_preserve_exact_code_boundaries(self):
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        with tempfile.TemporaryDirectory() as folder:
            writer=PdfWriter()
            for text in ['E202 Overtemperature. Possible causes are unconfirmed.','E2020 Example. This is a different code.','E202_1 Subgroup alarm.','E202-1 Another subgroup alarm.','2310 Overcurrent.','23100 Different numeric alarm.']:
                page=writer.add_blank_page(595,842)
                font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
                page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
                stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 40 760 Td ('+text+') Tj ET').encode('ascii'))
                page[NameObject('/Contents')]=writer._add_object(stream)
            path=Path(folder)/'english.pdf';writer.write(path)
            bridge=self.bridge(folder,path);item=self.import_fixture(bridge)['manual']
            hits=self.search(bridge,item['id'],'E202')['candidates']
            self.assertEqual([h['page'] for h in hits],[1])
            self.assertIn('E202 Overtemperature',hits[0]['quote'])
            self.assertEqual([h['page'] for h in self.search(bridge,item['id'],'E2020')['candidates']],[2])
            self.assertEqual([h['page'] for h in self.search(bridge,item['id'],'2310')['candidates']],[5])
            self.assertEqual([h['page'] for h in self.search(bridge,item['id'],'23100')['candidates']],[6])
            self.assertEqual([h['page'] for h in self.search(bridge,item['id'],'故障码2310，过流')['candidates']],[5])

    def test_readonly_preview_routes_search_current_library_without_file_upload(self):
        from desktop import make_server
        import urllib.request,urllib.error,threading
        from urllib.parse import urlencode
        with tempfile.TemporaryDirectory() as folder:
            bridge=self.bridge(folder);item=self.import_fixture(bridge)['manual'];server=make_server(bridge._manuals)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(url+'/api/manuals') as r:self.assertEqual(json.load(r)[0]['id'],item['id'])
                with urllib.request.urlopen(url+'/api/manual-search?'+urlencode({'manualId':item['id'],'query':'E202'})) as r:self.assertEqual(json.load(r)['candidates'][0]['page'],2)
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(url+'/api/manuals',data=b'upload'))
                self.assertEqual(e.exception.code,501)
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(url+'/api/manual-search?'+urlencode({'manualId':'../private','query':'E202'}))
                self.assertEqual(e.exception.code,400)
            finally:server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
