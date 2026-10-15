export function analyze(input={},catalog){
 const model=String(input.model??'').trim().toUpperCase().replace(/\s/g,'');
 const query=String(input.query??'').trim();const answers=input.answers&&typeof input.answers==='object'?input.answers:{};
 const base={mode:'evidence',status:'ready',candidates:[],questions:[],note:'候选条目是排查方向，实际原因需要检查确认。'};
 if(!/^ATV320(?:[A-Z0-9]+)?(?:系列)?$/.test(model))return {...base,status:'unsupported-model',note:'当前只收录ATV320系列。其他机型需使用对应手册。'};
 if(query.length>2000)return {...base,status:'too-long',note:'故障描述请控制在2000字以内。'};
 if(!query)return {...base,status:'empty',note:'请先描述故障现象，或选择一个演示案例。'};
 const cases=catalog.cases;const upper=query.toUpperCase();
 const codeAnswer=String(answers.code??'').trim().toUpperCase();
 const known=cases.filter(c=>new RegExp('(?<![A-Z0-9])'+c.code+'(?![A-Z0-9])').test(upper));
 const unknownMatch=upper.match(/(?:报警代码|故障代码|故障码|报警码|代码|报警|显示|出现)\s*[:：]?\s*([A-Z][A-Z0-9]{2,8})(?![A-Z0-9])/)
  ||upper.match(/(?<![A-Z0-9])([A-Z][A-Z0-9]{2,8})\s*(?:报警|故障|错误)/);
 let candidates=[];
 if(codeAnswer&& !['无','无代码','不确定','未知'].includes(codeAnswer)){
  const found=cases.find(c=>c.code===codeAnswer);
  if(!found)return {...base,status:'unknown-code',note:'该代码尚未收录。请核对输入，并查阅对应型号手册。'};
  candidates=[found];
 }else if(unknownMatch&&!cases.some(c=>c.code===unknownMatch[1])){
  return {...base,status:'unknown-code',note:'该代码尚未收录。请核对输入，并查阅对应型号手册。'};
 }else if(known.length){candidates=known;}
 else {
  if(/^[A-Z][A-Z0-9]{2,8}$/.test(upper)&&!cases.some(c=>c.code===upper))return {...base,status:'unknown-code',note:'该代码尚未收录。'};
  const normalized=query.toLowerCase();
  candidates=cases.map(c=>({item:c,score:c.keywords.reduce((n,k)=>n+(normalized.includes(k.toLowerCase())?k.length:0),0)}))
   .filter(c=>c.score>0).sort((a,b)=>b.score-a.score).slice(0,3).map(c=>c.item);
 }
 if(!candidates.length)return {...base,status:'no-evidence',note:'现有九个条目没有匹配依据。请补充报警代码，或查阅完整手册。',questions:[{key:'code',label:'屏幕上具体显示什么报警代码？',type:'text'}]};
 const questions=[];
 if(!known.length&&!codeAnswer)questions.push({key:'code',label:'屏幕上具体显示什么报警代码？',type:'text'});
 if(!answers.stage)questions.push({key:'stage',label:'故障发生在哪个阶段？',options:['上电时','启动或加速','持续运行','减速或停机','不确定']});
 for(const c of candidates){if(c.question&&!answers[c.question.key]&&!questions.some(q=>q.key===c.question.key))questions.push(c.question);}
 return {...base,status:known.length||codeAnswer?'code-match':'symptom-match',candidates:candidates.map(c=>({...c,sourceId:'NVE41300_05'})),questions};
}

export function makeOrder(input,result,notes={}){
 return {id:globalThis.crypto.randomUUID(),createdAt:new Date().toISOString(),model:String(input.model??''),query:String(input.query??''),
  mode:result.ai?'ai-assisted':result.mode??'evidence',ai:result.ai??null,answers:input.answers??{},candidates:(result.candidates??[]).map(c=>({code:c.code,title:c.title,page:c.page,sourceId:c.sourceId,...(c.kind==='manual-passage'?{kind:c.kind,id:c.id,manualId:c.manualId,edition:c.edition,quote:c.quote,sha256:c.sha256}: {})})),
  confirmedCause:String(notes.cause??'').trim()||'未确认',checks:String(notes.checks??'').trim()||'未记录',actions:String(notes.actions??'').trim()||'未记录',
  outcome:['待处理','排查中','已恢复（用户记录）','需专业支持'].includes(notes.outcome)?notes.outcome:'待处理'};
}

export function orderMarkdown(order){
 const text=v=>String(v??'').replace(/</g,'&lt;').replace(/>/g,'&gt;');
 const source=c=>c.kind==='manual-passage'?`${text(c.title)} · 版本 ${text(c.edition)}；PDF第${c.page}页（实际页序）`:`${text(c.code)} ${text(c.title)}；${text(c.sourceId)} 第${c.page}页`;
 const labels={code:'报警代码',stage:'发生阶段',recentChange:'参数或负载变化',cooling:'通风与环境温度',load:'负载情况',deceleration:'减速或制动情况',supply:'供电情况',connection:'通信改动',qualified:'专业检查情况'};
 return ['# 设备维修工单',`编号：${order.id}`,`时间：${order.createdAt}`,`设备：${text(order.model)}`,'',
  '## 故障描述',text(order.query),'','## 补充信息',...Object.entries(order.answers).map(([k,v])=>`- ${text(labels[k]||k)}：${text(v)}`),'',
  '## 手册候选（不是已确认原因）',...order.candidates.flatMap(c=>[`- ${source(c)}`,...(c.kind==='manual-passage'?['原文快照：',text(c.quote)]:[])]),'',
  '## 实际检查记录',text(order.checks),'','## 实际采取措施',text(order.actions),'',`确认原因：${text(order.confirmedCause)}`,`处理结果：${order.outcome}`,'',
  ...(order.ai?['## AI 辅助解释（需人工核对，不是实际检查结论）',text(order.ai.explanation),'',
   '建议补充的信息',...(order.ai.questions??[]).map(q=>'- '+text(q)),'尚未确认',...(order.ai.uncertainties??[]).map(q=>'- '+text(q)),
   ...(order.ai.sources??[]).map(c=>`- ${source(c)}`),`模型：${text(order.ai.model)}`,'']:[]),
  '本工单的实际检查、措施、确认原因及结果来自用户记录。'+(order.ai?'附有 AI 解释，须人工核对。':'本工单未使用 AI 解释。')].join('\n');
}
