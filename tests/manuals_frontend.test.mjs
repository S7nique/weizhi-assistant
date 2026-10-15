import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {parseHTML} from 'linkedom';
import {analyze,makeOrder,orderMarkdown} from '../src/core.mjs';
const id='11111111-1111-4111-8111-111111111111';
const manual={id,title:'模拟手册',deviceModel:'DEMO-100',edition:'1.0',pageCount:2,textPageCount:2,unreadablePageCount:0,archived:false};
const hit={id:id+':2:0',kind:'manual-passage',manualId:id,code:'PDF',title:'模拟手册',edition:'1.0',deviceModel:'DEMO-100',page:2,sourceId:id,quote:'E202 温升示例，仅为导入测试。'};
const result={mode:'manual-library',status:'text-match',deviceModel:'DEMO-100',manualId:id,manualTitle:'模拟手册',candidates:[hit],questions:[],note:'关键词原文，实际原因未确认。'};
async function setup(api){
 const html=readFileSync(new URL('../src/ui.html',import.meta.url),'utf8');const catalog=JSON.parse(readFileSync(new URL('../src/catalog.json',import.meta.url),'utf8'));
 const {document,window}=parseHTML(html);window.scrollTo=()=>{};window.pywebview={api:{get_history:async()=>[],list_manuals:async()=>[manual],...api}};
 const context=vm.createContext({document,window,console,analyze,makeOrder,orderMarkdown,setTimeout:()=>{},localStorage:{getItem:()=>null},fetch:async()=>({ok:true,json:async()=>catalog})});
 vm.runInContext(html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^import .*;\s*/m,''),context);
 for(const key of ['model','outcome'])Object.defineProperty(document.getElementById(key),'value',{writable:true,value:key==='model'?'ATV320':'待处理'});
 await new Promise(resolve=>setImmediate(resolve));return {document,window,context};
}
test('选择PDF后导入登记信息，模型列表可选新手册，不传任意文件路径',async()=>{
 let payload;
 const {document,window}=await setup({choose_manual_file:async()=>({selectionId:'selected-only',fileName:'测试.pdf'}),import_manual:async text=>{payload=JSON.parse(text);return {manual,duplicate:false};}});
 assert.ok(document.getElementById('chooseManual'),'缺少手册导入界面');
 document.getElementById('chooseManual').click();await new Promise(resolve=>setImmediate(resolve));
 document.getElementById('manualTitle').value='模拟手册';document.getElementById('manualModel').value='DEMO-100';document.getElementById('manualEdition').value='1.0';
 document.getElementById('importManualForm').dispatchEvent(new window.Event('submit',{cancelable:true}));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(payload.selectionId,'selected-only');assert.equal(payload.deviceModel,'DEMO-100');assert.equal(payload.path,undefined);
 assert.ok(document.getElementById('model').innerHTML.includes('manual:'+id));assert.ok(document.getElementById('manualStatus').textContent.includes('2'));
});
test('导入手册原文的PDF页码和版本进入工单，原文按纯文本显示',async()=>{
 const malicious={...hit,quote:'E202 <script data-injected="yes">alert(1)</script> 仅为测试。'};
 const {document,window}=await setup({search_manuals:async()=>({...result,candidates:[malicious]})});
 document.getElementById('model').value='manual:'+id;document.getElementById('query').value='E202';
 document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));await new Promise(resolve=>setImmediate(resolve));
 assert.ok(document.getElementById('resultContent').textContent.includes('PDF第 2 页'));
 assert.equal(document.querySelector('[data-injected]'),null);
 document.getElementById('generateOrder').click();const preview=document.getElementById('orderPreview').textContent;
 assert.ok(preview.includes('模拟手册'));assert.ok(preview.includes('PDF第2页'));assert.ok(preview.includes('1.0'));
 assert.ok(preview.includes('确认原因：未确认'));assert.ok(preview.includes('设备：DEMO-100'));
});
test('手册异步检索期间修改成OCF，旧原文不能覆盖新故障',async()=>{
 let finish;
 const {document,window}=await setup({search_manuals:()=>new Promise(resolve=>finish=resolve)});
 document.getElementById('model').value='manual:'+id;document.getElementById('query').value='E202';
 document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));
 document.getElementById('model').value='ATV320';document.getElementById('model').dispatchEvent(new window.Event('change'));
 document.getElementById('query').value='OCF';document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));
 finish(result);await new Promise(resolve=>setImmediate(resolve));
 assert.ok(document.getElementById('resultContent').textContent.includes('过电流'));assert.ok(!document.getElementById('resultContent').textContent.includes('温升示例'));
 document.getElementById('generateOrder').click();assert.ok(!document.getElementById('orderPreview').textContent.includes('模拟手册'));
});
test('归档正在使用的手册会清空旧依据，恢复后可以重新选择',async()=>{
 let archived=false;
 const {document,window}=await setup({list_manuals:async()=>[{...manual,archived}],set_manual_archived:async(uid,value)=>{archived=value;return {...manual,archived};},search_manuals:async()=>result});
 document.getElementById('model').value='manual:'+id;document.getElementById('query').value='E202';
 document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));await new Promise(resolve=>setImmediate(resolve));
 assert.ok(document.querySelector('[data-archive-manual]'),'缺少可恢复的归档操作');
 document.querySelector('[data-archive-manual]').click();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(archived,true);assert.ok(!document.getElementById('model').innerHTML.includes('manual:'+id));
 assert.equal(document.getElementById('generateOrder').disabled,true);
 document.querySelector('[data-restore-manual]').click();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(archived,false);assert.ok(document.getElementById('model').innerHTML.includes('manual:'+id));
});
