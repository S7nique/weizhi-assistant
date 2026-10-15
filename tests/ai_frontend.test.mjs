import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {parseHTML} from 'linkedom';
import {analyze,makeOrder,orderMarkdown} from '../src/core.mjs';

async function setup(api){
 const html=readFileSync(new URL('../src/ui.html',import.meta.url),'utf8');
 const catalog=JSON.parse(readFileSync(new URL('../src/catalog.json',import.meta.url),'utf8'));
 const {document,window}=parseHTML(html); window.scrollTo=()=>{};window.pywebview={api};
 const context=vm.createContext({document,window,console,analyze,makeOrder,orderMarkdown,
  setTimeout:()=>{},localStorage:{getItem:()=>null},fetch:async()=>({ok:true,json:async()=>catalog})});
 vm.runInContext(html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^import .*;\s*/m,''),context);
 for(const id of ['model','outcome'])Object.defineProperty(document.getElementById(id),'value',{writable:true,value:id==='model'?'ATV320':'待处理'});
 await new Promise(resolve=>setImmediate(resolve));
 return {document,window,context};
}
const status={baseUrl:'https://api.deepseek.com',model:'deepseek-flash',hasKey:false};
const baseAPI={get_history:async()=>[],get_ai_settings:async()=>status};

test('AI设置可保存无密钥配置，密钥字段保存后清空，未连接不会声称AI已启用',async()=>{
 let received;
 const {document,window}=await setup({...baseAPI,save_ai_settings:async text=>{received=JSON.parse(text);return {...status,hasKey:!!received.apiKey};}});
 assert.ok(document.getElementById('aiSettingsForm'),'缺少AI设置入口');
 document.getElementById('apiKey').value='only-session-secret';
 document.getElementById('aiSettingsForm').dispatchEvent(new window.Event('submit',{cancelable:true}));
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(received.apiKey,'only-session-secret');
 assert.equal(document.getElementById('apiKey').value,'');
 assert.ok(document.getElementById('aiStatus').textContent.includes('未测试'));
 assert.ok(!document.body.textContent.includes('only-session-secret'));
});

test('新故障丢弃延迟AI回答，不把旧解释写入新工单',async()=>{
 let finish;
 const {document,window}=await setup({...baseAPI,get_ai_settings:async()=>({...status,hasKey:true}),explain_ai:()=>new Promise(resolve=>finish=resolve)});
 const query=document.getElementById('query');query.value='显示 OCF';
 document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));
 assert.ok(document.getElementById('aiExplain'),'缺少AI解释功能');
 document.getElementById('aiExplain').click();
 query.value='显示 OHF';query.dispatchEvent(new window.Event('input'));
 document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));
 finish({explanation:'过流旧回答',questions:[],uncertainties:[],sources:[{code:'OCF',page:395,sourceId:'NVE41300_05'}],model:'deepseek-flash'});
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok(!document.getElementById('resultContent').textContent.includes('过流旧回答'));
 document.getElementById('generateOrder').click();
 assert.ok(!document.getElementById('orderPreview').textContent.includes('过流旧回答'));
 assert.ok(document.getElementById('orderPreview').textContent.includes('OHF'));
});

test('AI解释作为独立参考进入工单，实际原因与措施保持用户填写',async()=>{
 const answer={explanation:'手册指出应核对负载匹配。',questions:['最近加负载了吗？'],uncertainties:['尚未检查'],sources:[{code:'OCF',title:'过电流',page:395,sourceId:'NVE41300_05'}],model:'deepseek-flash'};
 const {document,window}=await setup({...baseAPI,get_ai_settings:async()=>({...status,hasKey:true}),explain_ai:async()=>answer});
 document.getElementById('query').value='显示 OCF';document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));
 assert.ok(document.getElementById('aiExplain'),'缺少AI解释功能');
 document.getElementById('aiExplain').click();await new Promise(resolve=>setImmediate(resolve));
 assert.ok(document.getElementById('aiOutput').textContent.includes('负载匹配'));
 document.getElementById('checks').value='演示：未现场检查';document.getElementById('generateOrder').click();
 const preview=document.getElementById('orderPreview').textContent;
 assert.ok(preview.includes('负载匹配'));assert.ok(preview.includes('确认原因：未确认'));
 assert.ok(preview.includes('处理结果：待处理'));assert.ok(preview.includes('实际采取措施\n未记录'));
});
