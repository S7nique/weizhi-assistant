import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {analyze, makeOrder, orderMarkdown} from '../src/core.mjs';
const catalog=JSON.parse(readFileSync(new URL('../src/catalog.json',import.meta.url),'utf8'));
test('代码优先于描述中的其他症状',()=>{
 const r=analyze({model:'ATV320U15N4C',query:'显示OCF，电机发热',answers:{}},catalog);
 assert.equal(r.candidates[0].code,'OCF'); assert.equal(r.candidates.length,1);
 assert.equal(r.candidates[0].page,395);assert.equal(r.mode,'evidence');
});
test('未知代码不能用相似症状冒充识别',()=>{
 const r=analyze({model:'ATV320',query:'报警代码XYZ999，设备过热',answers:{}},catalog);
 assert.equal(r.status,'unknown-code');assert.equal(r.candidates.length,0);
});
for(const query of ['故障码 XYZ999，设备过热','XYZ999 报警，设备过热','屏幕出现 XYZ999，设备过热']){
 test('常见未知报警表达拒答：'+query,()=>{
  const r=analyze({model:'ATV320',query},catalog);assert.equal(r.status,'unknown-code');assert.equal(r.candidates.length,0);
 });
}
test('不支持型号不输出ATV320建议',()=>assert.equal(analyze({model:'ATV630',query:'OCF'},catalog).status,'unsupported-model'));
test('空输入需要补充，不给出候选',()=>assert.equal(analyze({model:'ATV320',query:''},catalog).status,'empty'));
test('模糊过热描述保留候选并追问代码',()=>{
 const r=analyze({model:'ATV320',query:'设备过热，运行一会就停机'},catalog);
 assert.ok(r.candidates.some(c=>c.code==='OHF'));assert.ok(r.questions.some(q=>q.key==='code'));
});
test('补充代码能缩小候选',()=>{
 const r=analyze({model:'ATV320',query:'设备过热',answers:{code:'OLF',stage:'持续运行'}},catalog);
 assert.equal(r.candidates[0].code,'OLF');assert.ok(!r.questions.some(q=>q.key==='code'||q.key==='stage'));
});
test('长输入返回明确错误',()=>assert.equal(analyze({model:'ATV320',query:'热'.repeat(2001)},catalog).status,'too-long'));
test('未确认根因与未处理状态不得自动填写',()=>{
 const i={model:'ATV320',query:'OCF'};const r=analyze(i,catalog);
 const o=makeOrder(i,r,{checks:'尚未检查',actions:'',outcome:'待处理',cause:''});
 assert.equal(o.confirmedCause,'未确认');assert.equal(o.outcome,'待处理');assert.equal(o.actions,'未记录');
 assert.ok(orderMarkdown(o).includes('未确认'));assert.ok(orderMarkdown(o).includes('NVE41300_05'));
});
test('用户检查文本原样保留，核心不生成可执行HTML',()=>{
 const q='<script>alert(1)</script>'; const o=makeOrder({model:'ATV320',query:q},{candidates:[]},{checks:q});
 assert.equal(o.query,q);assert.equal(o.checks,q);
});
test('工单补充信息使用中文字段名',()=>{
 const o=makeOrder({model:'ATV320',query:'OCF',answers:{stage:'启动或加速',recentChange:'负载发生变化'}},{candidates:[]},{});
 const md=orderMarkdown(o);assert.ok(md.includes('发生阶段：启动或加速'));assert.ok(!md.includes('- stage：'));
});
