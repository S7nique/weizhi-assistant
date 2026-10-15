"""Local PDF library. User originals remain read-only; archiving is reversible."""
from pathlib import Path
import datetime,hashlib,json,re,sqlite3,threading,unicodedata,uuid
from contextlib import contextmanager
from pypdf import PdfReader

MAX_BYTES=50*1024*1024
def folded_text(text):
    # Some vector-font PDFs emit every Latin glyph twice (OOCCFF for OCF).
    # Normalize only whole even-length repeated-pair tokens in the search index.
    def dedouble(match):
        token=match.group(0)
        return token[::2] if len(token)%2==0 and all(token[i]==token[i+1] for i in range(0,len(token),2)) else token
    text=re.sub(r'(?<![A-Za-z0-9])[A-Za-z0-9]{6,}(?![A-Za-z0-9])',dedouble,unicodedata.normalize('NFKC',text))
    return text.casefold()

def normalized(text):return re.sub(r'\s+','',folded_text(text))
def identifier(value):
    try:return str(uuid.UUID(str(value)))
    except (ValueError,TypeError,AttributeError):raise ValueError('手册编号无效。') from None

class ManualLibrary:
    def __init__(self,root):
        self._folder=Path(root)/'本机数据'/'手册库'
        self._files=self._folder/'PDF';self._files.mkdir(parents=True,exist_ok=True)
        self._db=self._folder/'手册索引.sqlite3';self._lock=threading.RLock()
        with self._connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS manuals(id TEXT PRIMARY KEY,title TEXT NOT NULL,model TEXT NOT NULL,
              edition TEXT NOT NULL,original_name TEXT NOT NULL,sha256 TEXT UNIQUE NOT NULL,
              page_count INTEGER NOT NULL,text_page_count INTEGER NOT NULL,imported_at TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY,manual_id TEXT NOT NULL REFERENCES manuals(id),
              page INTEGER NOT NULL,ordinal INTEGER NOT NULL,text TEXT NOT NULL,normalized TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS chunks_manual ON chunks(manual_id,page);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(normalized,content='chunks',content_rowid='id',tokenize='trigram');
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
              INSERT INTO chunks_fts(rowid,normalized) VALUES(new.id,new.normalized); END;
            ''')

    @contextmanager
    def _connect(self):
        db=sqlite3.connect(self._db,timeout=30);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:yield db
        finally:db.close()

    def _public(self,row):
        return {'id':row['id'],'title':row['title'],'deviceModel':row['model'],'edition':row['edition'],
            'originalName':row['original_name'],'sha256':row['sha256'],'pageCount':row['page_count'],
            'textPageCount':row['text_page_count'],'unreadablePageCount':row['page_count']-row['text_page_count'],
            'importedAt':row['imported_at'],'archived':bool(row['archived'])}

    def list(self,include_archived=False):
        with self._connect() as db:
            rows=db.execute('SELECT * FROM manuals '+('' if include_archived else 'WHERE archived=0 ')+'ORDER BY imported_at DESC').fetchall()
        return [self._public(row) for row in rows]

    def get(self,manual_id,include_archived=False):
        manual_id=identifier(manual_id)
        with self._connect() as db:row=db.execute('SELECT * FROM manuals WHERE id=?',(manual_id,)).fetchone()
        if row is None or row['archived'] and not include_archived:raise ValueError('手册不存在或已归档，请先恢复或重新选择。')
        return self._public(row)

    def archive(self,manual_id,archived):
        item=self.get(manual_id,True)
        if not isinstance(archived,bool):raise ValueError('归档状态无效。')
        with self._lock,self._connect() as db:db.execute('UPDATE manuals SET archived=? WHERE id=?',(int(archived),item['id']))
        return self.get(item['id'],True)

    def import_pdf(self,source,metadata):
        fields={}
        for key in ['title','deviceModel','edition']:
            value=metadata.get(key)
            if not isinstance(value,str) or not value.strip() or len(value)>120:raise ValueError('请填写手册名称、适用型号和版本，每项不超过120字。')
            fields[key]=value.strip()
        source=Path(source)
        if source.suffix.lower()!='.pdf' or not source.is_file():raise ValueError('请选择有效PDF文件。')
        if source.stat().st_size>MAX_BYTES:raise ValueError('单份PDF请不超过50MB。')
        manual_id=str(uuid.uuid4());temporary=self._files/(manual_id+'.tmp');final=self._files/(manual_id+'.pdf')
        committed=False
        try:
            digest=hashlib.sha256();size=0
            with source.open('rb') as reader,temporary.open('xb') as writer:
                while data:=reader.read(1024*1024):
                    size+=len(data)
                    if size>MAX_BYTES:raise ValueError('单份PDF请不超过50MB。')
                    digest.update(data);writer.write(data)
            with temporary.open('rb') as header:
                if b'%PDF-' not in header.read(1024):raise ValueError('文件内容不是可读取的PDF。')
            sha=digest.hexdigest()
            with self._lock,self._connect() as db:
                row=db.execute('SELECT * FROM manuals WHERE sha256=?',(sha,)).fetchone()
                if row:
                    if row['archived']:db.execute('UPDATE manuals SET archived=0 WHERE id=?',(row['id'],))
                    return {'manual':{**self._public(row),'archived':False},'duplicate':True}
            try:
                reader=PdfReader(temporary)
                if reader.is_encrypted and not reader.decrypt(''):raise ValueError('PDF需要密码，请先保存为无密码副本。')
                page_count=len(reader.pages)
                if not 1<=page_count<=1200:raise ValueError('PDF页数须为1至1200页。')
                chunks=[];text_pages=0;total_chars=0
                for page_no,page in enumerate(reader.pages,1):
                    contents=page.get_contents()
                    if contents is not None and len(contents.get_data())>20*1024*1024:raise ValueError('PDF单页内容过大，请拆分后导入。')
                    text=(page.extract_text() or '').replace('\x00','').strip()
                    if not normalized(text):continue
                    text_pages+=1;total_chars+=len(text)
                    if total_chars>10000000:raise ValueError('手册文字过多，请拆分后导入。')
                    for ordinal,start in enumerate(range(0,len(text),780)):
                        quote=text[start:start+1000].strip()
                        if quote:chunks.append((manual_id,page_no,ordinal,quote,normalized(quote)))
            except ValueError:raise
            except Exception:raise ValueError('PDF读取失败，可能损坏或加密。请另存为可复制文字的PDF再导入。') from None
            if not text_pages:raise ValueError('没有读取到可检索文字，扫描件请先进行OCR文字识别后再导入。')
            stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            with self._lock,self._connect() as db:
                # Check again under the commit lock when two import calls overlap.
                row=db.execute('SELECT * FROM manuals WHERE sha256=?',(sha,)).fetchone()
                if row:return {'manual':self._public(row),'duplicate':True}
                temporary.replace(final)
                db.execute('INSERT INTO manuals VALUES(?,?,?,?,?,?,?,?,?,0)',(manual_id,fields['title'],fields['deviceModel'],fields['edition'],source.name,sha,page_count,text_pages,stamp))
                db.executemany('INSERT INTO chunks(manual_id,page,ordinal,text,normalized) VALUES(?,?,?,?,?)',chunks)
            committed=True
            return {'manual':self.get(manual_id),'duplicate':False}
        finally:
            if temporary.exists():temporary.unlink()
            if not committed and final.exists():final.unlink()

    def _terms(self,query,device_model):
        text=unicodedata.normalize('NFKC',query).casefold()
        latin=[s for s in re.findall(r'[a-z][a-z0-9_-]{1,39}',text) if s not in {'or','and','the','is','how','what',normalized(device_model)}]
        latin+=re.findall(r'(?<![a-z0-9_-])\d{2,40}(?![a-z0-9_-])',text)
        chinese=[]
        for group in re.findall(r'[\u4e00-\u9fff]{2,}',text):
            for stop in ['怎么处理','怎么办','请问','如何','怎么','出现','显示','故障码','报警代码','报警码','故障代码','设备']:
                group=group.replace(stop,' ')
            for segment in group.split():
                if 2<=len(segment)<=8:chinese.append(segment)
                if len(segment)>2:chinese.extend(segment[i:i+3] for i in range(len(segment)-2))
        return list(dict.fromkeys(latin+chinese))[:32]

    def search(self,manual_id,query):
        item=self.get(manual_id)
        if not isinstance(query,str) or not 1<=len(query.strip())<=2000:raise ValueError('请填写1至2000字的关键词或故障描述。')
        terms=self._terms(query,item['deviceModel'])
        rows={}
        with self._connect() as db:
            long=[t for t in terms if len(t)>=3]
            if long:
                expression=' OR '.join('"'+t.replace('"','""')+'"' for t in long)
                hits=db.execute('SELECT c.* FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid WHERE c.manual_id=? AND chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 80',(item['id'],expression)).fetchall()
                rows.update({r['id']:r for r in hits})
            short=[t for t in terms if len(t)==2]
            if short:
                condition=' OR '.join('instr(normalized,?)>0' for _ in short)
                hits=db.execute('SELECT * FROM chunks WHERE manual_id=? AND ('+condition+') LIMIT 80',(item['id'],*short)).fetchall()
                rows.update({r['id']:r for r in hits})
        # Explicit alarm tokens must occur in the passage, even if another symptom matches.
        explicit=re.findall(r'(?:故障码|报警代码|报警码|故障代码)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9_-]{1,20})',query)
        explicit+=re.findall(r'显示\s*[:：]?\s*([A-Za-z][A-Za-z0-9_-]{1,20})',query)
        codes=[c.casefold() for c in explicit]+[t for t in terms if re.fullmatch(r'[a-z]{1,6}[-_]?\d[a-z0-9_-]*',t)]
        if re.fullmatch(r'\d{2,40}',query.strip()):codes.append(query.strip())
        scored=[]
        for row in rows.values():
            if codes and not any(re.search(r'(?<![a-z0-9_-])'+re.escape(c)+r'(?![a-z0-9_-])',folded_text(row['text'])) for c in codes):continue
            score=sum((20 if re.search(r'[a-z0-9]',t) else len(t))*int(t in row['normalized']) for t in terms)
            if score and any(word in row['normalized'] for word in ['可能原因','解决措施','troubleshooting','correctiveaction']):score+=8
            if score:scored.append((score,row))
        scored.sort(key=lambda pair:(-pair[0],pair[1]['page'],pair[1]['ordinal']))
        chosen=[];used_pages=set()
        for score,row in scored:
            if row['page'] in used_pages:continue
            used_pages.add(row['page'])
            chosen.append({'id':f"{item['id']}:{row['page']}:{row['ordinal']}",'kind':'manual-passage','code':'PDF',
                'manualId':item['id'],'title':item['title'],'edition':item['edition'],'deviceModel':item['deviceModel'],
                'page':row['page'],'sourceId':item['id'],'sha256':item['sha256'],'quote':row['text']})
            if len(chosen)==3:break
        return {'mode':'manual-library','status':'text-match' if chosen else 'no-text-match','manualId':item['id'],
            'deviceModel':item['deviceModel'],'manualTitle':item['title'],'candidates':chosen,'questions':[],
            'note':'按关键词找到导入手册的原文片段，须核对适用型号与上下文；不是已确认的故障原因。' if chosen else '这份手册没有匹配到原文，请试试准确报警代码或更短的关键词。'}

    def pdf_path(self,manual_id):
        item=self.get(manual_id,True);path=self._files/(item['id']+'.pdf')
        if not path.is_file():raise ValueError('本机PDF副本不存在，请重新导入。')
        return path
