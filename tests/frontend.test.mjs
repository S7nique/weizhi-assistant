import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {parseHTML} from 'linkedom';
import {analyze,makeOrder,orderMarkdown} from '../src/core.mjs';

test('编辑主描述后，旧追问不能带入旧代码或已恢复结论',async()=>{
 const html=readFileSync(new URL('../src/ui.html',import.meta.url),'utf8');
 const catalog=JSON.parse(readFileSync(new URL('../src/catalog.json',import.meta.url),'utf8'));
 const {document,window}=parseHTML(html);window.scrollTo=()=>{};
 const storage=new Map();
 const context=vm.createContext({document,window,console,analyze,makeOrder,orderMarkdown,Blob,URL,
  localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)},
  setTimeout:()=>{},fetch:async()=>({ok:true,json:async()=>catalog})});
 const script=html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^import .*;\s*/m,'');
 vm.runInContext(script,context);
 await new Promise(resolve=>setImmediate(resolve));
 // 通过页面真实事件提交第一故障；用文本属性避免linkedom选择框实现差异。
 const model=document.getElementById('model');Object.defineProperty(model,'value',{writable:true,value:'ATV320'});
 const outcome=document.getElementById('outcome');Object.defineProperty(outcome,'value',{writable:true,value:'待处理'});
 document.getElementById('query').value='设备过热';
 document.getElementById('diagnoseform').dispatchEvent(new window.Event('submit',{cancelable:true}));
 assert.ok(document.getElementById('answer-code'),document.getElementById('inputError').textContent);
 const oldForm=document.getElementById('followupform');
 document.querySelectorAll('select[data-answer]').forEach(el=>Object.defineProperty(el,'value',{writable:true,value:''}));
 document.getElementById('answer-code').value='OLF';
 document.getElementById('checks').value='旧检查记录';document.getElementById('cause').value='旧确认原因';outcome.value='已恢复（用户记录）';
 document.getElementById('query').value='显示 OCF，加速停机';
 document.getElementById('query').dispatchEvent(new window.Event('input'));
 // 即使旧表单事件已排队，也不能重新拼入旧答案。
 oldForm.dispatchEvent(new window.Event('submit',{cancelable:true}));
 assert.equal(vm.runInContext('result?.candidates[0]?.code',context),'OCF');
 assert.equal(document.getElementById('cause').value,'');assert.equal(outcome.value,'待处理');
 assert.equal(document.getElementById('checks').value,'');
});
