"""维知助手 Windows 桌面入口；可选 AI 由用户主动调用。"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import datetime
import json
import logging
import sys
import tempfile
import threading
import uuid
from ai_client import AIClient
from manual_library import ManualLibrary

ROOT=Path(__file__).resolve().parent
RESOURCE=Path(getattr(sys,'_MEIPASS',ROOT))/'resources'/'src' if getattr(sys,'frozen',False) else ROOT/'src'
APP_DIR=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else ROOT

class ExportBridge:
    def __init__(self,root):
        self._root=Path(root)
        self._window=None
        self._expected_url=None
        self._ai=AIClient(self._root,json.loads((RESOURCE/'catalog.json').read_text(encoding='utf-8')))
        self._manuals=ManualLibrary(self._root)
        self._manual_selection=None

    def choose_manual_file(self):
        self._assert_local()
        if self._window is None:raise ValueError('请在Windows桌面程序中选择手册。')
        import webview
        picked=self._window.create_file_dialog(dialog_type=webview.FileDialog.OPEN,allow_multiple=False,file_types=('PDF 手册 (*.pdf)',))
        if not picked:return {'cancelled':True}
        path=Path(picked[0]).resolve()
        token=str(uuid.uuid4());self._manual_selection=(token,path)
        return {'cancelled':False,'selectionId':token,'fileName':path.name}

    def import_manual(self,content):
        self._assert_local()
        if not isinstance(content,str) or len(content)>2000:raise ValueError('手册信息无效。')
        data=json.loads(content)
        if not isinstance(data,dict) or not self._manual_selection or data.get('selectionId')!=self._manual_selection[0]:
            raise ValueError('请先通过“选择PDF”按钮选择文件。')
        selection=self._manual_selection
        result=self._manuals.import_pdf(selection[1],data)
        if self._manual_selection==selection:self._manual_selection=None
        return result

    def list_manuals(self,include_archived=False):
        self._assert_local()
        return self._manuals.list(bool(include_archived))

    def set_manual_archived(self,manual_id,archived):
        self._assert_local()
        return self._manuals.archive(manual_id,archived)

    def search_manuals(self,content):
        self._assert_local()
        if not isinstance(content,str) or len(content)>5000:raise ValueError('查询信息无效。')
        data=json.loads(content)
        if not isinstance(data,dict):raise ValueError('查询信息无效。')
        return self._manuals.search(data.get('manualId'),data.get('query'))

    def open_manual_pdf(self,manual_id):
        self._assert_local()
        import os
        path=self._manuals.pdf_path(manual_id)
        os.startfile(str(path))
        return {'opened':True}

    def explain_manual_search(self,content):
        self._assert_local()
        if not isinstance(content,str) or len(content)>10000:raise ValueError('AI手册查询信息无效。')
        data=json.loads(content)
        if not isinstance(data,dict):raise ValueError('AI手册查询信息无效。')
        result=self._manuals.search(data.get('manualId'),data.get('query'))
        ids=data.get('passageIds')
        if not isinstance(ids,list) or not ids or len(ids)>3 or any(not isinstance(i,str) for i in ids):raise ValueError('请选择有效原文依据。')
        hits=[c for c in result['candidates'] if c['id'] in ids]
        if len({c['id'] for c in hits})!=len(set(ids)):raise ValueError('原文依据已失效，请重新检索。')
        return self._ai.explain_passages(data['query'],hits)

    def get_ai_settings(self):
        self._assert_local()
        return self._ai.status()

    def save_ai_settings(self,content):
        self._assert_local()
        return self._ai.configure(content)

    def clear_ai_key(self):
        self._assert_local()
        return self._ai.clear_key()

    def test_ai_connection(self):
        self._assert_local()
        return self._ai.test_connection()

    def explain_ai(self,content):
        self._assert_local()
        return self._ai.explain(content)

    def _assert_local(self):
        if self._window is not None:
            current=self._window.get_current_url()
            if not current or urlsplit(current).netloc!=urlsplit(self._expected_url).netloc:
                raise ValueError('只允许在本机工作台操作文件。')

    def export_order(self,content,format):
        self._assert_local()
        if format not in ('md','json') or not isinstance(content,str) or len(content)>100000:
            raise ValueError('工单内容或文件格式无效。')
        if format=='json':json.loads(content)
        folder=self._root/'导出工单'
        folder.mkdir(parents=True,exist_ok=True)
        name=f'维知工单_{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.{format}'
        path=folder/name
        path.write_text(content,encoding='utf-8')
        return {'path':str(path)}

    def get_history(self):
        self._assert_local()
        path=self._root/'本机数据'/'工单记录.json'
        if not path.exists():return []
        records=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(records,list):raise ValueError('本机记录格式异常，请保留文件并联系维护人员。')
        return records[:20]

    def save_order(self,content):
        self._assert_local()
        if not isinstance(content,str) or len(content)>100000:raise ValueError('工单内容过长。')
        order=json.loads(content)
        if not isinstance(order,dict) or not isinstance(order.get('id'),str) or not isinstance(order.get('candidates'),list) or not isinstance(order.get('answers'),dict):
            raise ValueError('工单格式无效。')
        uuid.UUID(order['id'])
        records=[item for item in self.get_history() if item.get('id')!=order['id']]
        path=self._root/'本机数据'/'工单记录.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps([order,*records][:20],ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path)
        return {'saved':True}


def make_server(library=None):
    routes={'/':('ui.html','text/html'),'/client-core.js':('core.mjs','text/javascript'),'/api/catalog':('catalog.json','application/json')}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
                self.send_error(403);return
            route=urlsplit(self.path).path
            if route=='/api/health':
                data=b'{"ok":true,"mode":"evidence","desktop":true}'
                content_type='application/json'
            elif route in ('/api/manuals','/api/manual-search'):
                try:
                    if route=='/api/manuals':value=library.list(True) if library else []
                    else:
                        if library is None:raise ValueError('手册库未就绪')
                        params=parse_qs(urlsplit(self.path).query)
                        value=library.search(params.get('manualId',[''])[0],params.get('query',[''])[0])
                    data=json.dumps(value,ensure_ascii=False).encode('utf-8');content_type='application/json'
                except ValueError:
                    self.send_error(400);return
            elif route in routes:
                filename,content_type=routes[route]
                data=(RESOURCE/filename).read_bytes()
            else:
                self.send_error(404);return
            self.send_response(200)
            self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'")
            self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    return ThreadingHTTPServer(('127.0.0.1',0),Handler)


def self_test():
    import urllib.request
    server=make_server()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    checks=[]
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/catalog') as response:
            catalog=json.load(response)
            assert len(catalog['cases'])==9
            checks.append('九条依据可加载')
        with tempfile.TemporaryDirectory(prefix='weizhi-check-') as directory:
            bridge=ExportBridge(Path(directory))
            saved=bridge.export_order('演示工单：未确认','md')
            assert Path(saved['path']).read_text(encoding='utf-8')=='演示工单：未确认'
            order={'id':str(uuid.uuid4()),'candidates':[],'answers':{},'query':'演示'}
            bridge.save_order(json.dumps(order));assert bridge.get_history()[0]['query']=='演示'
            checks.extend(['中文工单导出','本机历史保存'])
            state=bridge.save_ai_settings(json.dumps({'baseUrl':'https://api.deepseek.com','model':'deepseek-flash','apiKey':''}))
            assert not state['hasKey'] and ExportBridge(Path(directory)).get_ai_settings()['model']=='deepseek-flash'
            checks.append('AI配置入口与无密钥保存（未调用真实模型）')
            fixture=RESOURCE.parent/'fixtures'/'manual_demo.pdf' if getattr(sys,'frozen',False) else ROOT/'tests/fixtures/manual_demo.pdf'
            item=bridge._manuals.import_pdf(fixture,{'title':'模拟手册','deviceModel':'DEMO-100','edition':'1.0'})['manual']
            assert bridge._manuals.search(item['id'],'E202')['candidates'][0]['page']==2
            assert ExportBridge(Path(directory))._manuals.search(item['id'],'E202')['candidates'][0]['page']==2
            bridge._manuals.archive(item['id'],True);assert bridge._manuals.list()==[]
            bridge._manuals.archive(item['id'],False);assert len(bridge._manuals.list())==1
            checks.append('文字PDF导入、第2页检索、重启持久化与归档恢复')
            english=fixture.with_name('manual_english_demo.pdf')
            item=bridge._manuals.import_pdf(english,{'title':'English simulated manual','deviceModel':'DEMO-EN','edition':'1.0'})['manual']
            for code,page in [('E202',1),('E2020',2),('2310',5),('23100',6)]:
                assert [hit['page'] for hit in bridge._manuals.search(item['id'],code)['candidates']]==[page]
            checks.append('英文与数字报警码精确匹配，相似码保持区分')
        import webview
        checks.append('桌面窗口库可导入')
        (APP_DIR/'自检结果.json').write_text(json.dumps({'passed':True,'checks':checks,'scope':'资源、本机服务、导出和保存；窗口交互另外人工验证'},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def main():
    if '--self-test' in sys.argv:
        self_test();return
    import webview
    bridge=ExportBridge(APP_DIR)
    server=make_server(bridge._manuals)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    bridge._expected_url=url
    window=webview.create_window('维知助手 · 设备运维工作台',url,js_api=bridge,width=1360,height=900,min_size=(900,600),background_color='#f4f5f0')
    bridge._window=window
    try:
        webview.start(gui='edgechromium',private_mode=False,storage_path=str(APP_DIR/'本机数据'/'界面缓存'),debug=False)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':
    try:main()
    except Exception:
        APP_DIR.mkdir(parents=True,exist_ok=True)
        logging.basicConfig(filename=str(APP_DIR/'启动错误.log'),level=logging.ERROR,encoding='utf-8')
        logging.exception('桌面启动失败')
        if '--self-test' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'程序启动失败，详情已保存到启动错误.log。','维知助手',16)
        raise
