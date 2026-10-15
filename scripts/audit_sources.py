from pathlib import Path
import json
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
catalog=json.loads((ROOT/'src/catalog.json').read_text(encoding='utf-8'))
pdf=ROOT.parent/'原始手册'/'ATV320_Programming_manual_CN_NVE41300_05.pdf'
result=[]
with pymupdf.open(pdf) as document:
    for item in catalog['cases']:
        text=document[item['page']-1].get_text()
        normalized=''.join(text.split())
        assert ''.join(item['heading'].split()) in normalized, item['code']
        assert 'NVE41300_05' in text
        result.append({'code':item['code'],'page':item['page'],'heading':item['heading'],'passed':True})
qa=ROOT/'核验'
qa.mkdir(exist_ok=True)
(qa/'来源审计.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'SOURCE_AUDIT PASS cases={len(result)}')
