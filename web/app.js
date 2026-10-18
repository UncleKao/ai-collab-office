'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const names = {claude:'Claude',codex:'Codex',grok:'Grok',assistant:'助理',gemini:'Gemini',owner:'負責人',system:'系統'};
const initials = {claude:'C',codex:'C',grok:'G',assistant:'A',gemini:'Gm',owner:'負',system:'系'};

const officeSettings={title:'AI 協作辦公室',owner_name:'負責人',timezone:'Asia/Taipei',automation:false,life_lead:'assistant',teams:{maintenance:'開發協作區',life:'助理協作區'},members:[]};
function applyOfficeSettings(data){
  if(data.settings&&typeof data.settings==='object')Object.assign(officeSettings,data.settings);
  if(data.teams&&typeof data.teams==='object')officeSettings.teams=data.teams;
  if(Array.isArray(data.members))officeSettings.members=data.members;
  names.owner=officeSettings.owner_name;initials.owner=officeSettings.owner_name.slice(0,1);
  for(const member of officeSettings.members){names[member.worker]=member.name;initials[member.worker]=member.name.slice(0,1);}
  document.title=officeSettings.title;
  const title=$('#office-title');if(title)title.textContent=officeSettings.title;
  const mode=$('#mode-note');if(mode)mode.textContent=officeSettings.automation?'AI 自動協作已啟用；模型使用自己的帳號額度。':'手動測試模式：可建立任務與留言，透過 CLI 交付及複核；不會呼叫模型。';
  for(const button of $$('[data-team]'))if(officeSettings.teams[button.dataset.team])button.textContent=officeSettings.teams[button.dataset.team];
  const groups=$('#partner-groups');if(!groups)return;groups.replaceChildren();
  for(const [team,label] of Object.entries(officeSettings.teams)){
    const group=node('section','partner-group');group.dataset.partnerTeam=team;group.append(node('h2','partner-heading',label));
    for(const member of officeSettings.members.filter(m=>m.team===team)){
      const row=node('div','team-person');row.append(avatar(member.worker));
      const description=node('div','',member.name);description.append(node('small','',member.worker));
      row.append(description,node('span','team-role',member.dispatch_enabled?'協作夥伴':'停用'));group.append(row);
    }
    groups.append(group);
  }
}
const states = {proposal:'待收件',inbox:'待分工',discuss:'討論中',working:'實作中',review:'複核中',fix:'修正中',approved:'待拍板',active:'已採用',closed:'已結案',dropped:'已擱置'};
const kinds = {new:'提出任務',say:'參與討論',claim:'認領任務',deliver:'交付成果',review:'提出複核',decide:'更新決定',accept:'收件',active:'採用成果',closed:'結案',reopen:'重新開啟'};
const paths = {
  home:['M3 10 12 3l9 7','M5 9v12h14V9','M9 21v-8h6v8'],
  inbox:['M4 4h16l2 11v5H2v-5L4 4Z','M2 14h6l2 3h4l2-3h6'],
  layers:['m12 3 10 5-10 5L2 8l10-5Z','m2 12 10 5 10-5','m2 16 10 5 10-5'],
  archive:['M3 4h18v4H3z','M5 8v12h14V8','M9 12h6'],
  sparkles:['m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z'],
  external:['M14 3h7v7','m21 3-11 11','M10 3H3v18h18v-7'],
  arrow:['M4 12h15','m14 7 5 5-5 5'],
  check:['m5 12 4 4L19 6'],
  shield:['m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z','m8 12 3 3 5-6'],
  refresh:['M20 7V3l-3 3A8 8 0 0 0 4 9','M4 17v4l3-3a8 8 0 0 0 13-3','M20 3h-5','M4 21h5'],
  search:['M10 3a7 7 0 1 1 0 14 7 7 0 0 1 0-14Z','m15 15 6 6'],
  list:['M9 5h12M9 12h12M9 19h12','M3 5h1M3 12h1M3 19h1'],
  board:['M3 4h7v16H3zM14 4h7v16h-7z','M3 9h7M14 13h7'],
  route:['M5 4v11a4 4 0 0 0 4 4h10','m15 15 4 4-4 4','M3 2h4v4H3z'],
  close:['m6 6 12 12M18 6 6 18'],
  link:['m10 13 4-4','m8 15-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0','m14 9 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0'],
  file:['M5 3h9l5 5v13H5V3Z','M14 3v6h5','M9 13h6M9 17h4'],
};
function node(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text??'');return n;}
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','icon');svg.setAttribute('aria-hidden','true');for(const d of paths[name]||paths.file){const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',d);svg.append(p);}return svg;}
$$('[data-icon]').forEach(n=>n.replaceChildren(icon(n.dataset.icon)));
function avatar(who,portrait=false){
  const n=node('span','avatar '+(names[who]?who:'unknown'),initials[who]||'—');
  return n;
}
$$('[data-portrait]').forEach(n=>n.replaceWith(avatar(n.dataset.portrait,true)));
function owner(who){const n=node('span','owner');n.append(avatar(who),node('span','',names[who]||'待分工'));return n;}
function assignmentOwner(t){const a=plainObject(t.assignment);const who=a?.worker||t.owner;const box=node('span','assignment-owner');if(a&&Number(a.version)>0&&!a.worker){const auto=owner(null);auto.lastElementChild.textContent='依額度自動';box.append(auto);}else box.append(owner(who));if(t.team==='life')box.append(node('small','','助理主責'));return box;}
function runSlot(id, detail=false){const n=node('div',detail?'execution-panel':'execution-slot');n.dataset.executionTask=id;n.dataset.executionDetail=detail?'1':'0';paintRunSlot(n);return n;}
function badge(status){const n=node('span','badge '+(states[status]?status:'dropped'));n.append(node('i'),document.createTextNode(states[status]||'未知狀態'));return n;}
function parseTime(s){return new Date((s||'').replace(' ','T')+(/Z$|[+-]\d\d:\d\d$/.test(s||'')?'':'Z'));}
function ago(s){const sec=Math.max(0,(Date.now()-parseTime(s).getTime())/1000);if(!Number.isFinite(sec))return'時間未提供';if(sec<60)return'剛剛';if(sec<3600)return Math.floor(sec/60)+' 分鐘前';if(sec<86400)return Math.floor(sec/3600)+' 小時前';return Math.floor(sec/86400)+' 天前';}
function fullTime(s){const d=parseTime(s);return Number.isNaN(d.getTime())?'時間未提供':new Intl.DateTimeFormat('zh-TW',{timeZone:officeSettings.timezone,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);}
function shortBrief(s){return String(s||'尚未提供任務說明').replace(/^#+\s*/gm,'').replace(/\*\*/g,'').replace(/\n+/g,' ').slice(0,150);}
function reviewPills(t){const box=node('span','review-pills');const rs=t.reviews||[];for(const who of t.effective_reviewers||[]){const v=rs.find(r=>r.reviewer===who)?.verdict;box.append(node('span','review-pill '+(v==='pass'?'pass':v==='reject'?'reject':''),(v==='pass'?'✓ ':v==='reject'?'↺ ':'')+(names[who]||who)));}if(!box.childElementCount)box.append(node('span','review-pill','尚未指定'));return box;}
const app={tasks:[],team:'all',view:'all',filter:'all',query:'',layout:'list',fetched:null,detailId:null,detailRequest:0,user:null,csrf:'',
  detailTask:null,detailPending:null,detailOpen:null,detailPlanId:null,detailSubmitting:false,detailSyncAt:0};
const progress=['inbox','discuss','working','fix'];
const done=['active','closed','dropped'];
const formDefaults=new WeakMap(),formSubmissions=new Set(),controlSubmissions=new Set();
let composing=false,reloadCheckQueued=false;
const uiUpdate={loaded:document.querySelector('meta[name="office-build"]')?.content||'',latest:null,reloading:false,blocked:false};
function syncTime(s){const d=parseTime(s);return Number.isNaN(d.getTime())?'尚未同步':new Intl.DateTimeFormat('zh-TW',{timeZone:officeSettings.timezone,hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(d);}
async function requestJSON(path,options={},timeout=8000){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{const response=await fetch(path,{...options,signal:controller.signal});const data=await response.json();return {response,data};}
  catch(e){if(e.name==='AbortError')throw Error(options.method==='POST'?'送出等候逾時，請先核對最新結果再決定是否重送。':'資料讀取逾時，會自動再試。');throw e;}
  finally{clearTimeout(timer);}
}
function editableFields(scope=document){return [...scope.querySelectorAll('input[name],textarea[name],select[name]')].filter(n=>n.type!=='hidden'&&!n.hasAttribute('data-assignment-field')&&!n.hasAttribute('data-retained-draft'));}
function fieldState(n){return {value:n.value,checked:['checkbox','radio'].includes(n.type)?n.checked:null};}
function stateEqual(a,b){return a.value===b.value&&a.checked===b.checked;}
function rememberDefaults(scope){for(const n of editableFields(scope))if(!formDefaults.has(n))formDefaults.set(n,fieldState(n));}
function submissionBusy(){return app.detailSubmitting||formSubmissions.size>0||controlSubmissions.size>0;}
function hasUnsentContent(){
  if(submissionBusy()||app.supplementFiles?.get(app.detailId)?.length||composing||app.assignmentDraft?.dirty||app.modelDraft?.dirty||app.retainedDrafts?.entries.size)return true;
  return editableFields().some(n=>(!n.closest('dialog')||n.closest('dialog').open)&&!n.disabled&&!n.readOnly&&(n.type==='file'?n.files.length>0:!stateEqual(fieldState(n),formDefaults.get(n)||{value:'',checked:['checkbox','radio'].includes(n.type)?false:null})));
}
function readSession(key){try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}}
function paintBuildStatus(){
  let box=$('#frontend-update-status');
  if(!uiUpdate.latest){box?.remove();return;}
  if(!box){box=node('div','frontend-update-status');box.id='frontend-update-status';box.setAttribute('role','status');box.setAttribute('aria-live','polite');}
  box.textContent=uiUpdate.blocked?'新版暫未載入成功；目前進度仍會自動更新，請重新整理網頁。':uiUpdate.reloading?'正在自動載入新版介面…':'有新版介面；未送出內容送出或清空後會自動載入，工作進度持續更新。';
  const target=$('#compose-dialog').open?$('#compose-content'):$('#task-dialog').open?$('#detail-content'):document.querySelector('main');
  if(target&&box.parentElement!==target)target.prepend(box);
}
function checkFrontendUpdate(){
  if(!uiUpdate.latest||uiUpdate.reloading)return;
  paintBuildStatus();
  if(document.hidden||hasUnsentContent())return;
  const attempt=readSession('office-ui-reload-attempt');
  if(attempt?.from===uiUpdate.loaded&&attempt?.to===uiUpdate.latest){uiUpdate.blocked=true;paintBuildStatus();return;}
  const view={team:app.team,view:app.view,filter:app.filter,query:app.query,layout:app.layout,scroll:scrollY,detailScroll:$('#task-dialog').scrollTop,open:$$('#detail-content [data-keep]').filter(n=>n.open).map(n=>n.dataset.keep)};
  try{sessionStorage.setItem('office-ui-view',JSON.stringify(view));sessionStorage.setItem('office-ui-reload-attempt',JSON.stringify({from:uiUpdate.loaded,to:uiUpdate.latest}));}
  catch{uiUpdate.blocked=true;paintBuildStatus();return;}
  uiUpdate.reloading=true;paintBuildStatus();location.reload();
}
function scheduleReloadCheck(){if(reloadCheckQueued)return;reloadCheckQueued=true;queueMicrotask(()=>{reloadCheckQueued=false;checkFrontendUpdate();});}
function observeFrontendBuild(build){
  if(!/^[a-f0-9]{64}$/.test(build||'')||!uiUpdate.loaded)return;
  if(build===uiUpdate.loaded){uiUpdate.latest=null;uiUpdate.blocked=false;try{sessionStorage.removeItem('office-ui-reload-attempt');}catch{}paintBuildStatus();return;}
  if(uiUpdate.latest!==build)uiUpdate.blocked=false;uiUpdate.latest=build;scheduleReloadCheck();
}
function afterSubmission(){
  if(submissionBusy()||composing)return;
  if(app.detailPending){const next=app.detailPending;app.detailPending=null;if(next.id===app.detailId)applyDetail(next);}
  if(app.detailId!==null)pollDetail();
  scheduleReloadCheck();
}

function pendingHuman(t){if(Array.isArray(t.human_waiting))return t.human_waiting;const a=t.automation;return listOf(a?.jobs).filter(j=>listOf(a.attention_job_ids).includes(j.id)&&listOf(j.user_actions).length&&!j.human_response&&!j.human_obsolete);}
function decision(t){return['proposal','approved'].includes(t.status)||pendingHuman(t).length>0;}
function taskBadge(t){if(!pendingHuman(t).length&&t.work_status&&['blocked','failed'].includes(t.work_status.state))return node('span','badge fix',t.work_status.state==='blocked'?'有工作待補資料':'工作待核對');return pendingHuman(t).length?node('span','badge fix','待你操作'):t.status==='inbox'&&Number(t.assignment?.version)>0?node('span','badge inbox','已分工'):badge(t.status);}
function subset(t,filter){if(filter==='all')return true;if(filter==='decision')return decision(t);if(filter==='progress')return progress.includes(t.status);if(filter==='archive')return done.includes(t.status);if(filter==='completed')return ['active','closed'].includes(t.status);return t.status===filter;}
function teamTasks(){return app.tasks.filter(t=>app.team==='all'||(t.team||'maintenance')===app.team);}
function filtered(){const scoped=teamTasks().filter(t=>app.view==='all'?!done.includes(t.status):subset(t,app.view));return scoped.filter(t=>subset(t,app.filter)).filter(t=>!app.query||[t.title,t.brief,t.id,names[t.owner],names[t.assignment?.worker],names[t.created_by],states[t.status],t.status==='inbox'&&Number(t.assignment?.version)>0?'已分工':''].join(' ').toLocaleLowerCase().includes(app.query));}
function selectView(view){app.view=view;app.filter='all';const titles={all:'工作總覽',decision:'待我決定',progress:'待處理的事',archive:'已完成與封存',review:'夥伴複核中',completed:'已採用或結案'};$('#breadcrumb-title').textContent=titles[view]||'工作總覽';$('#list-heading').replaceChildren(document.createTextNode(view==='all'?'辦公室裡的事':titles[view]||'辦公室裡的事'),node('span','soft-count',''));$('#list-heading .soft-count').id='task-count';$$('.nav-item').forEach(n=>{const active=n.dataset.view===view;n.classList.toggle('active',active);if(active)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});render();}
function taskButton(t,cls){const b=node('button',cls);b.type='button';b.dataset.taskId=t.id;b.setAttribute('aria-label','查看任務 #'+t.id+' '+t.title);b.addEventListener('click',()=>openTask(t.id));return b;}
function renderStats(){const decisions=teamTasks().filter(decision).length;const counts={decision:decisions,progress:teamTasks().filter(t=>progress.includes(t.status)).length,review:teamTasks().filter(t=>t.status==='review').length,done:teamTasks().filter(t=>['active','closed'].includes(t.status)).length};for(const [k,v]of Object.entries(counts))$('#stat-'+k).textContent=v;$('#nav-all').textContent=teamTasks().filter(t=>!done.includes(t.status)).length;$('#nav-decision').textContent=decisions;$('#nav-progress').textContent=counts.progress;$('#decision-count').textContent=decisions;
  const hour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:officeSettings.timezone,hour:'2-digit',hour12:false}).format(new Date()));$('#greeting-title').textContent=(hour<12?'早安':hour<18?'午安':'晚安')+(app.user?'，'+(names[app.user]||'夥伴')+'。':'，歡迎回辦公室。');$('#greeting-subtitle').textContent=decisions?`有 ${decisions} 件事等${app.user==='owner'?'你':'負責人'}決定，夥伴們的進度都在這裡。`:'暫時沒有等你決定的事，看看夥伴們的最新進度。';
}
function renderDecisions(){const box=$('#decision-cards');box.replaceChildren();const tasks=teamTasks().filter(decision).sort((a,b)=>(a.status==='approved'?0:1)-(b.status==='approved'?0:1)).slice(0,2);$('#decision-section').hidden=app.view!=='all'||!tasks.length;for(const t of tasks){const b=taskButton(t,'decision-card');const top=node('div','card-top');top.append(taskBadge(t),node('span','task-id','HOME / '+String(t.id).padStart(3,'0')));const title=node('h3','',t.title);const passed=(t.reviews||[]).filter(r=>r.verdict==='pass').length;const desc=node('p','card-description',pendingHuman(t).length?'待你操作：'+pendingHuman(t).flatMap(j=>j.user_actions.map(a=>a.title)).join('；'):t.status==='approved'?'夥伴已完成本輪複核，請檢視成果並逐項驗收。':shortBrief(t.brief));const bottom=node('div','card-bottom');const summary=node('span','review-summary');const stack=node('span','avatar-stack');for(const r of t.effective_reviewers||[])stack.append(avatar(r));summary.append(stack,document.createTextNode(t.status==='approved'?`${passed} 位夥伴複核通過`:'提案等待收件'));const action=node('span','card-action',pendingHuman(t).length?'查看待辦操作':t.status==='approved'?'檢視成果與驗收':'看看提案');action.append(icon('arrow'));bottom.append(summary,action);b.append(top,title,runSlot(t.id),desc,bottom);box.append(b);}}
function empty(target,text){const e=node('div','empty-state');e.append(icon('inbox'),node('div','',text));target.append(e);}
function renderList(tasks){const list=$('#task-list');list.replaceChildren();if(!tasks.length){empty(list,app.query?'沒有符合的任務，換個關鍵字試試。':'這裡目前沒有任務。');return;}const head=node('div','table-header');for(const t of ['任務','目前狀態','負責夥伴','本輪複核','最近更新'])head.append(node('span','',t));list.append(head);
  for(const t of tasks){const row=taskButton(t,'task-row');const main=node('div','row-main');const sym=node('span','task-symbol');sym.append(icon(t.status==='approved'?'shield':t.status==='proposal'?'file':'layers'));const desc=node('div');desc.append(node('div','row-title',t.title));const meta=node('div','row-meta');meta.append(node('span','',`#${String(t.id).padStart(3,'0')}`),node('span','','·'),node('span','',t.authorized?'已收件':'尚待收件'),node('span','','·'),node('span','',(names[t.created_by]||'夥伴')+' 提出'));desc.append(meta);main.append(sym,desc);const status=node('span');status.append(taskBadge(t),runSlot(t.id));const updated=node('span','updated-time',ago(t.updated_at));updated.title=fullTime(t.updated_at);row.append(main,status,assignmentOwner(t),reviewPills(t),updated);list.append(row);}}
function renderBoard(tasks){const board=$('#task-board');board.replaceChildren();const groups=[['待收件',['proposal']],['討論與實作',progress],['複核與拍板',['review','approved']],['已完成與封存',done]];for(const [title,ss]of groups){const col=node('section','board-column');const ts=tasks.filter(t=>ss.includes(t.status));const h=node('h3','',title);h.append(node('span','',ts.length));col.append(h);for(const t of ts){const b=taskButton(t,'board-card');b.append(taskBadge(t),runSlot(t.id),node('h4','',t.title),node('span','task-id','#'+t.id),assignmentOwner(t));col.append(b);}if(!ts.length)col.append(node('div','board-empty','暫時沒有任務'));board.append(col);}}
function render(){for(const group of $$('[data-partner-team]'))group.hidden=app.team!=='all'&&group.dataset.partnerTeam!==app.team;
  for(const b of $$('[data-team]')){b.classList.toggle('selected',b.dataset.team===app.team);b.setAttribute('aria-pressed',b.dataset.team===app.team);}
  $('#team-description').textContent=app.team==='all'?'依工作區檢視任務，分工與複核在各張工作單設定。':(officeSettings.teams[app.team]||app.team)+'：依管理者設定的成員與授權範圍協作。';renderAuth();renderStats();renderDecisions();const tasks=filtered();$('#task-count').textContent=tasks.length;$$('[data-filter]').forEach(n=>n.classList.toggle('selected',n.dataset.filter===app.filter));renderList(tasks);renderBoard(tasks);$('#task-list').hidden=app.layout!=='list';$('#task-board').hidden=app.layout!=='board';$('#list-view').classList.toggle('selected',app.layout==='list');$('#board-view').classList.toggle('selected',app.layout==='board');$('#list-view').setAttribute('aria-pressed',app.layout==='list');$('#board-view').setAttribute('aria-pressed',app.layout==='board');const archived=teamTasks().filter(t=>done.includes(t.status)).length;$('#result-count').textContent=app.view==='all'?`顯示 ${tasks.length} 件進行中；${archived} 件已移至完成與封存`:`顯示 ${tasks.length} 件，本區共 ${teamTasks().length} 件任務`;}
let loading=false;
async function load(){if(loading)return;loading=true;$('#refresh').disabled=true;try{const {response:r,data:d}=await requestJSON('/web/overview',{cache:'no-store'});if(!r.ok)throw Error('來源無法讀取');if(!Array.isArray(d.tasks))throw Error('資料格式異常');applyOfficeSettings(d);app.tasks=d.tasks;app.fetched=d.fetched_at;app.user=d.session?.name||null;app.csrf=d.session?.csrf||'';render();observeFrontendBuild(d.frontend_build);$('#connection-error').hidden=true;$('#sync-dot').classList.remove('failed');$('#sync-text').textContent='已同步 '+syncTime(d.fetched_at)+' · 每 20 秒更新';}catch(e){const err=$('#connection-error');err.textContent=app.fetched?'暫時無法更新辦公室資料，畫面保留上次讀取的內容。請稍後重新整理。':'目前連不到辦公室，無法載入任務。請稍後重新整理。';err.hidden=false;$('#sync-text').textContent=app.fetched?'資料未更新 · 上次 '+syncTime(app.fetched):'辦公室資料暫時無法讀取';$('#sync-dot').classList.add('failed');if(!app.fetched){$('#decision-section').hidden=true;$('#task-list').replaceChildren();empty($('#task-list'),'任務尚未載入');$('#result-count').textContent='尚未取得任務資料';}}finally{loading=false;$('#refresh').disabled=false;}}
function metaItem(label,content){const n=node('div','meta-item');n.append(node('span','',label));const body=node('div');body.append(typeof content==='string'?document.createTextNode(content):content);n.append(body);return n;}
async function openTask(id){
  id=Number(id);if(!Number.isSafeInteger(id)||id<1)return;
  const dialog=$('#task-dialog'),preserve=app.detailId===id&&app.detailTask&&dialog.open;
  if(app.detailId!==id)app.detailOpen=null;
  app.detailId=id;app.detailPending=null;app.detailEpoch=(app.detailEpoch||0)+1;
  const request=++app.detailRequest;const anchor=location.pathname==='/t/'+id&&['#next-step','#missing-items','#human-actions','#results'].includes(location.hash)?location.hash:'';history.replaceState(null,'','/t/'+id+anchor);
  $('#detail-id').textContent='HOME / '+String(id).padStart(3,'0');const content=$('#detail-content');
  if(!preserve)content.replaceChildren(node('div','timeline-loading','正在整理這件事的前因後果…'));
  if(!dialog.open)dialog.showModal();document.body.classList.add('detail-open');
  try{
    const {response:r,data:t}=await requestJSON('/web/tasks/'+id,{cache:'no-store'});
    if(!r.ok||!plainObject(t)||t.id!==id)throw Error('無法讀取');if(request!==app.detailRequest)return;
    if(app.team!=='all'&&t.team&&app.team!==t.team){app.team=t.team;render();}
    app.detailSyncAt=Date.now();if(preserve)applyDetail(t,true);else renderDetail(t);
  }catch{
    if(request!==app.detailRequest)return;
    if(preserve){detailFailures++;paintDetailSync();return;}
    const text=node('div','empty-state','這項任務暫時無法讀取，請稍後再試。');const retry=node('button','text-button','重新讀取');retry.addEventListener('click',()=>openTask(id));content.replaceChildren(text,retry);
  }
}
function renderDetail(t){if(app.retainedDrafts?.taskId!==t.id)app.retainedDrafts={taskId:t.id,entries:new Map()};renderDetailContent(t);rememberDefaults($('#detail-content'));paintRetainedDrafts();paintBuildStatus();}
// 只以 DOM 節點排版文字；不載入HTML、圖片或執行原文。
function inlineText(parent,text){
  const rx=/(\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\))/g;let last=0,m;
  while((m=rx.exec(text))){parent.append(document.createTextNode(text.slice(last,m.index)));if(m[2])parent.append(node('strong','',m[2]));else if(m[3])parent.append(node('code','',m[3]));else{const a=node('a','',m[4]);a.href=m[5];a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}last=rx.lastIndex;}
  parent.append(document.createTextNode(text.slice(last)));
}
function readableText(text){
  const out=node('div','readable-text');const lines=String(text||'').split('\n');let para=[],list=null;
  const flush=()=>{if(para.length){const p=node('p');inlineText(p,para.join('\n'));out.append(p);para=[];}list=null;};
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(line.trim().startsWith('```')){flush();const code=[];while(++i<lines.length&&!lines[i].trim().startsWith('```'))code.push(lines[i]);const pre=node('pre');pre.append(node('code','',code.join('\n')));out.append(pre);continue;}
    if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){
      flush();const wrap=node('div','reading-table'),table=node('table');const cells=s=>s.trim().replace(/^\||\|$/g,'').split('|').map(x=>x.trim());const head=node('thead'),tr=node('tr');for(const s of cells(line)){const th=node('th');inlineText(th,s);tr.append(th);}head.append(tr);table.append(head);i++;const body=node('tbody');
      while(i+1<lines.length&&lines[i+1].includes('|')&&lines[i+1].trim()){const row=node('tr');for(const s of cells(lines[++i])){const td=node('td');inlineText(td,s);row.append(td);}body.append(row);}table.append(body);wrap.append(table);out.append(wrap);continue;
    }
    const heading=line.match(/^#{1,6}\s+(.+)/),li=line.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)/);
    if(heading){flush();const h=node('h3');inlineText(h,heading[1]);out.append(h);}
    else if(li){if(para.length)flush();if(!list){list=node('ul');out.append(list);}const item=node('li');inlineText(item,li[1]);list.append(item);}
    else if(!line.trim()){flush();}
    else if(/^\s*---+\s*$/.test(line)){flush();out.append(node('hr'));}
    else{if(list)list=null;para.push(line);}
  }flush();return out;
}
function revealMessage(id){
  const article=$('#detail-content').querySelector(`[data-message-id="${Number(id)}"]`);if(!article)return;
  for(let p=article.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
  const full=article.querySelector('.message-full');if(full)full.open=true;article.classList.add('message-highlight');article.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>article.classList.remove('message-highlight'),2200);
}
function summaryRefs(ids,t){const wrap=node('span','summary-refs');for(const id of ids||[]){const m=listOf(t.messages).find(x=>x.id===id);if(!m)continue;const b=node('button','text-button',`${person(m.author)} · ${fullTime(m.created_at)}`);b.type='button';b.addEventListener('click',()=>revealMessage(id));wrap.append(b);}return wrap;}
function summaryPanel(t){
  const s=t.summary||{owner:t.team==='life'?officeSettings.life_lead:'codex',state:'empty'};const box=node('section','work-panel summary-panel');
  const head=node('div','summary-head');head.append(node('h2','','目前結論'),node('span','summary-by',person(s.owner)+' 統整'));box.append(head);
  const active=['queued','running'].includes(s.state);let status=active?(s.state==='running'?'正在整理本輪討論…':'已排入總結，等待這輪工作完成'):s.stale?'有新發言或進度，這份結論待更新':s.result?'整理至 '+fullTime(s.created_at):'這輪還沒有主責總結';
  box.append(node('p','summary-freshness'+(s.stale?' stale':''),status));
  if(s.model_selection?.model)box.append(node('p','summary-note','這份結論使用：'+s.model_selection.model+(s.model_selection.effort?' · 思考強度：'+effortLabel(s.model_selection.effort):'')));
  if(s.result){box.append(readableText(s.result.overview),summaryRefs(s.result.refs,t));const labels={consensus:'目前共識',difference:'不同意見',next:'建議下一步',decision:'需要你決定'};
    for(const category of Object.keys(labels)){const points=listOf(s.result.points).filter(p=>p.category===category);if(!points.length)continue;const section=node('div','summary-section');section.append(node('h3','',labels[category]));for(const p of points){const item=node('div','summary-point');item.append(readableText(p.text),summaryRefs(p.refs,t));section.append(item);}box.append(section);}
  }else box.append(node('p','summary-empty','先看下方各人的說法。由主責整理共識、分歧與下一步，原文會完整保留。'));
  if(s.error)box.append(node('p','summary-error',s.error));
  if(officeSettings.automation&&app.user==='owner'&&!['closed','dropped','proposal'].includes(t.status)){
    const row=node('div','summary-actions');const select=node('select');select.name='summary_owner';select.setAttribute('aria-label','總結主責');
    for(const who of t.team==='life'?['assistant']:['codex','claude']){const option=node('option','',person(who)+' 總結');option.value=who;select.append(option);}select.value=s.owner;select.disabled=active;
    const button=node('button','work-button',s.result?'更新本輪結論':'整理本輪結論');button.type='button';button.disabled=active||listOf(t.automation?.jobs).some(j=>['queued','running'].includes(j.state));
    button.addEventListener('click',()=>sendControl(t,'summarize',button,{summary_owner:select.value}));row.append(select,button);box.append(row);
  }
  box.append(node('p','summary-note','由主責整理本輪公開討論；結論不會代你拍板或開始實作。'));const error=node('p','form-error');error.hidden=true;error.setAttribute('role','alert');box.append(error);return box;
}
function readingMessage(m){
  const article=node('article','message');article.dataset.messageId=m.id;article.append(avatar(m.author,true));const box=node('div');const head=node('div','message-head');const when=node('time','',fullTime(m.created_at));when.dateTime=parseTime(m.created_at).toISOString();head.append(node('strong','',person(m.author)),node('span','kind',kinds[m.kind]||'更新紀錄'),when);box.append(head);
  const original=m.body||'（沒有附加說明）';const text=original.replace(/^\[原生CLI工作[^\n]*\]\s*\n/,'');const split=text.indexOf('## 查核細節');const lead=split>=0?text.slice(0,split).trim():text;
  const body=node('div','message-body');const long=text.length>700||split>=0||text!==original;
  if(long){const excerpt=lead.length>600?lead.slice(0,600)+'…':lead;body.append(readableText(excerpt));if(lead.length>600)body.append(node('p','excerpt-label','原文節錄'));const details=keepable(node('details','message-full'),'message-'+m.id,false);details.append(node('summary','',split>=0&&lead.length<=600?'查看查核細節與完整原文':'展開完整發言'),readableText(original));body.append(details);}
  else body.append(readableText(text));box.append(body);
  if(m.ref){const details=node('details','message-ref');details.append(node('summary','','查看來源紀錄'),node('span','',m.ref));box.append(details);}article.append(box);return article;
}
function readingDiscussion(t,content){
  const messages=listOf(t.messages).filter(m=>m.kind!=='new');const boundary=t.automation?.discussion_message||0;const current=messages.filter(m=>m.id>=boundary),past=messages.filter(m=>m.id<boundary);const substantive=current.filter(m=>!['control','system','decide','claim'].includes(m.kind));const events=current.filter(m=>!substantive.includes(m));
  const heading=node('div','timeline-heading');heading.append(node('h2','','一起討論'),node('span','',substantive.length+' 則本輪發言'));content.append(heading);
  const older=substantive.slice(0,-6),latest=substantive.slice(-6);
  if(older.length){const earlier=keepable(node('details','reading-history'),'earlier-current',false);earlier.append(node('summary','',`本輪較早的 ${older.length} 則發言`));older.forEach(m=>earlier.append(readingMessage(m)));content.append(earlier);}
  latest.forEach(m=>content.append(readingMessage(m)));
  if(!latest.length)content.append(node('p','reading-empty','還沒有這輪的回覆，可以先說說你的想法。'));
  return {past,events};
}
function renderDetailContent(t){
  const content=$('#detail-content');content.replaceChildren();app.detailTask=t;app.detailPending=null;
  const state=node('div','detail-state');state.append(workStatus(t.automation)||taskBadge(t),node('span','detail-auth',t.authorized?'已收件':'提案待收件'));content.append(state,node('h1','',t.title));content.querySelector('h1').id='detail-title';
  content.append(summaryPanel(t));
  const human=humanPanel(t);if(human){human.id='human-actions';content.append(human);}
  const continuation=continuationPanel(t);if(continuation)content.append(continuation);
  const next=nextStepPanel(t);if(next)content.append(next);
  const missing=missingPanel(t);if(missing)content.append(missing);
  const delivery=deliveryPanel(t);if(delivery){delivery.id='results';content.append(delivery);}
  const discussion=keepable(node('details','reading-controls'),'current-discussion',!delivery&&!t.summary);
  discussion.append(node('summary','','本輪討論與留言'));
  const {past,events}=readingDiscussion(t,discussion);renderActions(t,discussion);content.append(discussion);
  const settings=keepable(node('details','reading-controls'),'settings',false);settings.append(node('summary','','模型、思考強度與其他操作'),modelPanel(t));
  if(workActionsReady(t)){const choices=node('section','work-panel intent-panel');choices.append(workActions(t,t.automation));settings.append(choices);}content.append(settings);
  const progress=keepable(node('details','reading-controls'),'work-progress',false);progress.append(node('summary','','查看執行進度與分工'),workPanel(t));const assignment=assignmentPanel(t);if(assignment)progress.append(assignment);content.append(progress);
  const brief=keepable(node('details','brief-block'),'brief',false);brief.append(node('summary','','原始需求'),readableText(t.brief||'尚無說明'));content.append(brief);
  if(events.length){const log=keepable(node('details','reading-history'),'work-events',false);log.append(node('summary','',`本輪操作紀錄（${events.length}）`));events.forEach(m=>log.append(readingMessage(m)));content.append(log);}
  if(past.length){const history=keepable(node('details','reading-history'),'past-discussion',false);history.append(node('summary','',`先前討論與紀錄（${past.length}）`));past.forEach(m=>history.append(readingMessage(m)));content.append(history);}
}

function clearDetail(){app.detailEpoch=(app.detailEpoch||0)+1;app.detailId=null;app.detailRequest++;app.detailTask=null;app.detailPending=null;app.detailOpen=null;app.assignmentDraft=null;app.modelDraft=null;app.retainedDrafts=null;document.body.classList.remove('detail-open');history.replaceState(null,'','/'+location.search);scheduleReloadCheck();}
function closeDetail(){clearDetail();if($('#task-dialog').open)$('#task-dialog').close();}
$('#task-dialog').addEventListener('cancel',e=>{e.preventDefault();closeDetail();});
$('#task-dialog').addEventListener('close',()=>{if(!$('#task-dialog').open&&app.detailId!==null)clearDetail();});
$('#close-detail').addEventListener('click',closeDetail);
$('#task-dialog').addEventListener('click',e=>{if(e.target===$('#task-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeDetail();}});
let toastTimer;
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,3500);}
$('#copy-link').addEventListener('click',async()=>{const url=location.origin+'/t/'+app.detailId;try{if(navigator.clipboard){await navigator.clipboard.writeText(url);toast('任務連結已複製');return;}}catch{}const input=node('input','copy-fallback');input.value=url;input.readOnly=true;input.setAttribute('aria-label','任務連結，請複製');$('#detail-content').prepend(input);input.select();try{if(document.execCommand('copy')){input.remove();toast('任務連結已複製');return;}}catch{}toast('連結已選取，可手動複製');});
$$('[data-view]').forEach(n=>n.addEventListener('click',()=>selectView(n.dataset.view)));
$$('[data-filter]').forEach(n=>n.addEventListener('click',()=>{app.filter=n.dataset.filter;render();}));
$$('[data-team]').forEach(b=>b.addEventListener('click',()=>{app.team=b.dataset.team;app.view='all';app.filter='all';render();}));
$('#search').addEventListener('input',e=>{app.query=e.target.value.trim().toLocaleLowerCase();render();});
$('#see-decisions').addEventListener('click',()=>{selectView('decision');$('.tasks-section').scrollIntoView({behavior:'smooth',block:'start'});});
$('#list-view').addEventListener('click',()=>{app.layout='list';render();});$('#board-view').addEventListener('click',()=>{app.layout='board';render();});
$('#refresh').addEventListener('click',load);
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)&&!$('#task-dialog').open){e.preventDefault();$('#search').focus();}});
window.addEventListener('hashchange',()=>{const id=location.hash.match(/^#task-(\d+)$/)?.[1];if(id)openTask(id);else if(['#next-step','#missing-items','#human-actions','#results'].includes(location.hash))document.getElementById(location.hash.slice(1))?.scrollIntoView();else closeDetail();});
$('#today').textContent=new Intl.DateTimeFormat('zh-TW',{timeZone:officeSettings.timezone,month:'long',day:'numeric',weekday:'long'}).format(new Date());
load().then(async()=>{const restored=readSession('office-ui-view');if(restored){try{sessionStorage.removeItem('office-ui-view');}catch{}if(['all','maintenance','life'].includes(restored.team))app.team=restored.team;if(['all','decision','progress','archive','review','completed'].includes(restored.view))selectView(restored.view);if(typeof restored.filter==='string')app.filter=restored.filter;if(typeof restored.query==='string'){app.query=restored.query.slice(0,200);$('#search').value=app.query;}if(['list','board'].includes(restored.layout))app.layout=restored.layout;render();}const initialId=location.hash.match(/^#task-(\d+)$/)?.[1]||location.pathname.match(/^\/t\/(\d+)$/)?.[1];if(initialId){await openTask(initialId);if(['#next-step','#missing-items','#human-actions','#results'].includes(location.hash))document.getElementById(location.hash.slice(1))?.scrollIntoView();if(restored){for(const n of $$('#detail-content [data-keep]'))n.open=Array.isArray(restored.open)&&restored.open.includes(n.dataset.keep);$('#task-dialog').scrollTop=Number(restored.detailScroll)||0;}}if(restored)window.scrollTo({top:Number(restored.scroll)||0,behavior:'instant'});if(location.pathname==='/login')showLogin();if(location.pathname==='/new')showNewTask();});
setInterval(()=>{if(!document.hidden)load();},20000);


// 正式網頁操作：同源 cookie + CSRF；狀態與權限仍由後端裁定。
function renderAuth(){
  const me=app.user;$('#auth-button').textContent=me?'登出':'登入';
  $('#user-avatar').textContent=initials[me]||'訪';$('#user-avatar').title=me?'目前身分：'+names[me]:'訪客，登入後才能操作';
  $('#new-task-button').hidden=!me;$('#new-task-top').hidden=!me;
}
function field(label,name,opts={}){
  const wrap=node('label','form-field');wrap.append(node('span','',label));
  const input=node(opts.multiline?'textarea':'input');input.name=name;
  if(!opts.multiline)input.type=opts.type||'text';else input.rows=opts.rows||3;
  input.required=Boolean(opts.required);input.maxLength=opts.maxLength||2000;
  if(opts.placeholder)input.placeholder=opts.placeholder;
  if(opts.type==='password')input.autocomplete='off';
  wrap.append(input);return wrap;
}
function formActions(form,label){const row=node('div','form-actions');const err=node('p','form-error');err.setAttribute('role','alert');err.hidden=true;const button=node('button','primary-button',label);button.type='submit';row.append(err,button);form.append(row);return err;}
async function postWeb(path,payload){
  const {response,data}=await requestJSON(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),credentials:'same-origin'},20000);
  if(!response.ok)throw Error(data.error||'操作未完成，請重新整理後再試');return data;
}
function wireForm(form,path,after){
  form.method='post';form.action=path;rememberDefaults(form);
  form.addEventListener('submit',async e=>{
    e.preventDefault();const button=form.querySelector('[type="submit"]');const error=form.querySelector('.form-error');
    if(button.disabled||submissionBusy())return;button.disabled=true;error.hidden=true;formSubmissions.add(form);app.detailEpoch=(app.detailEpoch||0)+1;app.detailPending=null;
    const values=Object.fromEntries(new FormData(form));values.csrf=app.csrf;
    const controls=[...form.querySelectorAll('input,textarea,select')],wasDisabled=new Map(controls.map(n=>[n,n.disabled]));controls.forEach(n=>{n.disabled=true;});
    try{const data=await postWeb(path,values);await after(data);}
    catch(e){error.textContent=e.message;error.hidden=false;}
    finally{button.disabled=false;controls.forEach(n=>{if(n.isConnected)n.disabled=wasDisabled.get(n);});formSubmissions.delete(form);afterSubmission();}
  });
}
function closeCompose(){if($('#compose-dialog').open)$('#compose-dialog').close();$('#compose-content').replaceChildren();document.body.classList.toggle('detail-open',$('#task-dialog').open);scheduleReloadCheck();}
function showCompose(title){$('#compose-label').textContent=title;$('#compose-content').replaceChildren();if(!$('#compose-dialog').open)$('#compose-dialog').showModal();document.body.classList.add('detail-open');return $('#compose-content');}
function showLogin(){
  const returnTo=app.detailId;closeDetail();const content=showCompose('登入AI 協作辦公室');
  content.append(node('h2','','回到我們的工作空間'),node('p','form-hint','使用本次安裝產生的個人登入碼。登入後就能提出事情、參與討論。'));
  const form=node('form');form.id='login-form';form.append(field('個人登入碼','token',{type:'password',required:true,maxLength:1024,placeholder:'貼上你的登入碼'}));formActions(form,'登入辦公室');
  wireForm(form,'/web/login',async()=>{form.reset();closeCompose();await load();toast('登入成功，'+(names[app.user]||'歡迎回來'));if(returnTo)await openTask(returnTo);else history.replaceState(null,'','/');});content.append(form);
}
function showNewTask(){
  if(!app.user)return showLogin();closeDetail();const content=showCompose('提出一件事');
  content.append(node('h2','','把想法放到桌上'),node('p','form-hint',app.user==='owner'?'寫下想做的事，以及你認為做好的樣子。':'你提出的想法會先成為提案，等待負責人收件。'));
  const form=node('form');form.id='new-task-form';
  const teamLabel=node('label','form-field');teamLabel.append(node('span','','放在哪一區'));const teamSelect=node('select');teamSelect.name='team';
  for(const [v,label] of Object.entries(officeSettings.teams)){const opt=node('option','',label);opt.value=v;teamSelect.append(opt);}
  teamSelect.value=app.team==='life'?'life':'maintenance';teamLabel.append(teamSelect);form.append(teamLabel);
  form.append(field('這件事的名稱','title',{required:true,maxLength:200,placeholder:'用一句話說明'}),field('需求與完成條件','brief',{multiline:true,rows:5,required:true,maxLength:100000,placeholder:'想解決什麼？希望最後看到什麼成果？'}));
  const wrap=node('label','form-field');wrap.append(node('span','','複核夥伴'));const select=node('select');select.name='reviewers';
  function reviewerOptions(){
    select.replaceChildren();
    const fallback=node('option','','由本區其他夥伴複核');fallback.value='';select.append(fallback);
    for(const member of officeSettings.members.filter(m=>m.dispatch_enabled)){
      const opt=node('option','',person(member.worker));opt.value=member.worker;select.append(opt);
    }
  }
  reviewerOptions();teamSelect.addEventListener('change',reviewerOptions);wrap.append(select);form.append(wrap);formActions(form,app.user==='owner'?'交給辦公室':'提出想法');
  wireForm(form,'/web/tasks',async data=>{closeCompose();await load();await openTask(data.id);app.team=data.team||'maintenance';render();toast('這件事已放進辦公室');});content.append(form);
}
function renderActions(t,content){
  if(!app.user){const box=node('div','source-action');box.append(node('span','','登入後才能閱讀任務與參與討論。'));const login=node('button','text-button','登入辦公室');login.addEventListener('click',showLogin);box.append(login);content.append(box);return;}
  const section=node('section','task-actions');section.append(node('h2','','你的想法'));
  if(app.user==='owner'){
    const form=node('form','decision-form');form.id='decision-form';const wrap=node('label','form-field');wrap.append(node('span','','你的決定'));const select=node('select');select.name='decision';select.required=true;
    const placeholder=node('option','','選擇這次的決定');placeholder.value='';placeholder.disabled=true;placeholder.selected=true;select.append(placeholder);
    const choices=[];if(t.status==='proposal')choices.push(['accept','收下這個提案']);if(t.status==='approved')choices.push(['active','採用這版成果（記錄決定）']);
    if(['approved','active','closed','dropped','review'].includes(t.status))choices.push(['reopen','重開，請夥伴再修正']);
    choices.push(['closed','結案'],['dropped','作廢']);for(const [value,text]of choices){const option=node('option','',text);option.value=value;select.append(option);}
    wrap.append(select);form.append(wrap,field('補充說明（選填）','body',{maxLength:4000,placeholder:'留下一句話，讓夥伴知道你的想法'}));formActions(form,'送出決定');
    wireForm(form,'/web/tasks/'+t.id+'/decide',async()=>{form.reset();await load();await openTask(t.id);toast('決定已記錄');});
    if(t.status==='approved')form.append(node('p','form-hint','採用成果會記錄你的決定。部署、輸入密碼與啟用後驗證，須由這張單的實際工作完成。'));
    // 收件與拍板照樣好按；工作走得動的時候，結案與作廢收進次要區塊。
    const holder=keepable(node('details','secondary-decisions'),'decide',['proposal','approved'].includes(t.status)||!workActionsReady(t));
    holder.append(node('summary','','負責人的決定：收件、採用成果、重開、結案或作廢'),form);section.append(holder);
  }
  const form=node('form','reply-form');form.id='reply-form';form.append(field('說說你的想法','body',{multiline:true,rows:3,required:true,maxLength:100000,placeholder:'補充需求、回覆夥伴，或留下新的進度…'}));formActions(form,'送出留言');
  wireForm(form,'/web/tasks/'+t.id+'/say',async()=>{form.reset();await load();await openTask(t.id);toast('留言已送出');});section.append(form);content.append(section);
  if(app.user==='owner')section.append(node('p','form-hint','有工作排隊或進行時，留言只記錄，後續夥伴可讀；待複核、待拍板或已啟用時，留言也只記錄。只有收件／討論／修正且目前沒有工作時，留言會開新討論。要重來請按「回到討論」。'));
}
$('#auth-button').addEventListener('click',async()=>{if(!app.user)return showLogin();try{const result=await postWeb('/web/logout',{csrf:app.csrf});if(result.redirect){location.assign(result.redirect);return;}closeDetail();closeCompose();await load();toast('已登出');}catch(e){toast(e.message);}});
$('#user-avatar').addEventListener('click',()=>{if(!app.user)showLogin();else toast('目前身分：'+names[app.user]);});
$('#new-task-button').addEventListener('click',showNewTask);$('#new-task-top').addEventListener('click',showNewTask);
$('#close-compose').addEventListener('click',closeCompose);
$('#compose-dialog').addEventListener('cancel',e=>{e.preventDefault();closeCompose();});
$('#compose-dialog').addEventListener('close',()=>{document.body.classList.toggle('detail-open',Boolean(document.querySelector('dialog[open]')));});


// 實際執行回報與提案／拍板狀態各自顯示。
const executionNames={idle:'目前無執行',queued:'等待執行',running:'執行中',returned:'回覆待核對',completed:'已完成',blocked:'待Codex處理',failed:'執行失敗',unknown:'狀態待確認'};
let executionRuns=[],executionHealthy=false,executionFetched=0,executionLoading=false;
function executionState(r){return(!executionHealthy||Date.now()-executionFetched>20000)&&['running','queued'].includes(r.state)?'unknown':r.state;}
function runMark(state){const mark=node('span','execution-mark '+state);if(state==='running'){mark.setAttribute('aria-label','執行中');}else{mark.append(icon(state==='completed'?'check':state==='failed'?'close':state==='returned'?'file':'refresh'));}return mark;}
function runElapsed(r){const start=parseTime(r.started_at).getTime();const end=r.finished_at?parseTime(r.finished_at).getTime():Date.now();const secs=Math.max(0,Math.floor((end-start)/1000));if(!Number.isFinite(secs))return'';return secs<60?`${secs} 秒`:`${Math.floor(secs/60)} 分 ${secs%60} 秒`;}
function taskRuns(id){const all=executionRuns.filter(r=>r.task_id===Number(id));const latest=new Map();for(const r of all){const prev=latest.get(r.worker);if(!prev||r.started_at>prev.started_at)latest.set(r.worker,r);}return [...latest.values()];}
function paintRunSlot(slot){slot.replaceChildren();
  const task=app.tasks.find(t=>Number(t.id)===Number(slot.dataset.executionTask)),flow=task?.work_status;
  if(slot.dataset.executionDetail!=='1'&&flow&&executionNames[flow.state]){slot.hidden=false;const badge=node('span','execution-badge '+flow.state),label=flow.state==='blocked'&&pendingHuman(task).length?'待你操作':executionNames[flow.state];badge.append(runMark(flow.state),node('span','',flow.state==='idle'?executionNames.idle:`${flow.count} 項${label}`));slot.append(badge);return;}
  const represented=new Set(slot.dataset.executionDetail==='1'?JSON.parse(slot.dataset.jobRunIds||'[]'):[]);const runs=taskRuns(slot.dataset.executionTask).filter(r=>!represented.has(r.id));if(!runs.length){slot.hidden=true;return;}slot.hidden=false;
  if(slot.dataset.executionDetail==='1'){
    const title=node('div','execution-heading','派工執行狀態');slot.append(title);
    for(const r of runs){const state=executionState(r);const row=node('div','execution-person');row.append(avatar(r.worker,true));const text=node('div','execution-description');text.append(node('strong','',(names[r.worker]||'夥伴')+' · '+executionNames[state]),node('span','',r.label+(r.finished_at?' · '+fullTime(r.finished_at)+' 結束':'')));const mark=node('span','execution-person-status');mark.append(runMark(state),node('span','',runElapsed(r)));row.append(text,mark);row.title='最後回報 '+fullTime(r.updated_at);slot.append(row);}
    if(!executionHealthy)slot.append(node('p','execution-note','執行狀態暫時無法更新，保留最後收到的紀錄。'));
    slot.append(node('p','execution-note','顯示已接入回報的派工；各自視窗的其他工作不在此判定。提案收件與採用成果仍由負責人決定。'));
  }else{
    const priority=['running','unknown','failed','queued','returned','completed'];const state=priority.find(s=>runs.some(r=>executionState(r)===s));const count=runs.filter(r=>executionState(r)===state).length;const badge=node('span','execution-badge '+state);badge.append(runMark(state),node('span','',`${count} 項${executionNames[state]}`));badge.title=runs.map(r=>(names[r.worker]||r.worker)+'：'+executionNames[executionState(r)]).join('；');slot.append(badge);
  }
}
function paintExecutions(){for(const n of $$('[data-execution-task]'))paintRunSlot(n);
  let hint=$('#execution-feed-note');if(!hint){hint=node('span','execution-note');hint.id='execution-feed-note';hint.setAttribute('role','status');$('.list-footer').append(hint);}hint.hidden=executionHealthy;hint.textContent=executionFetched?'執行狀態暫時無法更新':'正在確認執行狀態';
  const currentRuns=[...new Set(executionRuns.map(r=>r.task_id))].flatMap(taskRuns);
  for(const row of $$('.team-person')){const av=row.querySelector('.avatar');const who=['claude','codex','grok','assistant','gemini'].find(w=>av?.classList.contains(w));const role=row.querySelector('.team-role');if(!role||!who)continue;const running=currentRuns.some(r=>r.worker===who&&executionState(r)==='running');const unknown=currentRuns.some(r=>r.worker===who&&executionState(r)==='unknown');role.replaceChildren();if(running){role.append(runMark('running'),document.createTextNode('執行中'));}else{role.textContent=who==='gemini'?'未允許派工':unknown?'狀態待確認':who==='assistant'?'生活主責':'協作夥伴';}role.classList.toggle('executing',running);}
}
async function loadExecutions(){if(!app.user||executionLoading)return;executionLoading=true;const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),6000);
  try{const r=await fetch('/web/executions',{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error('回報不可用');const d=await r.json();if(!Array.isArray(d.runs))throw Error('回報格式不符');executionRuns=d.runs;executionHealthy=!d.incomplete;executionFetched=Date.now();}
  catch{executionHealthy=false;}finally{clearTimeout(timeout);executionLoading=false;paintExecutions();}
}
loadExecutions();
setInterval(()=>{paintExecutions();if(!document.hidden)loadExecutions();},5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){paintExecutions();loadExecutions();}});


// 工作進度、派工操作與用量摘要：能不能動由後端裁定，這裡只呈現與送出。
const jobStates={queued:'排隊中',running:'執行中',blocked:'卡住等處理',completed:'已完成',failed:'執行失敗',cancelled:'已取消'};
const jobKinds={discuss:'討論',check:'檢查',implement:'實作',review:'複核'};
const planStates={draft:'草稿',approved:'已核准啟動',ready:'可以開始',active:'進行中',used:'已採用',superseded:'已被新版取代',rejected:'未採用',cancelled:'已取消'};
const controlLabels={assign:'儲存分工',accept_delivery:'驗收通過',request_changes:'要求修正',complete_action:'我已完成，請核對並接續',reviewers:'儲存複核名單',discuss:'繼續討論',restart_discussion:'回到討論',plan:'整理動工計畫',check:'先檢查',start:'開始執行',pause:'目前這一步完成後暫停',resume:'繼續往下做',retry:'核對後接續',summarize:'整理本輪結論',models:'儲存模型選擇',repair:'重新補件並核對'};
const capacityStates={disabled:'不派工',implementation:'可接實作',small_review:'只接小複核',reserve:'保留額度',unknown:'狀態未知'};
function plainObject(v){return v&&typeof v==='object'&&!Array.isArray(v)?v:null;}
function listOf(v){return Array.isArray(v)?v:[];}
function labelOf(map,key,fallback){return typeof key==='string'&&Object.prototype.hasOwnProperty.call(map,key)?map[key]:fallback;}
function clip(v,n){const s=v===null||v===undefined?'':String(v);return s.length>n?s.slice(0,n)+'…':s;}
function knownWorker(w){return labelOf(names,w,null)?w:null;}
function person(w){return labelOf(names,w,clip(w,12)||'夥伴');}
function percentText(v){return typeof v==='number'&&Number.isFinite(v)?Math.max(0,Math.min(100,Math.round(v)))+'%':'未知';}
function keepable(details,key,fallback){details.dataset.keep=key;details.open=app.detailOpen?app.detailOpen.has(key):fallback;return details;}
function workActionsReady(t){return officeSettings.automation&&app.user==='owner'&&Boolean(plainObject(t.automation))&&Boolean(t.authorized)&&!['closed','dropped'].includes(t.status);}

// -- 指定分工：人選草稿與正式版本分開，儲存不啟動工作。 --
function assignmentEditable(t){
  if(app.user!=='owner')return false;
  const requiresAcceptance=t.assignment?.requires_acceptance===true&&['proposal','inbox'].includes(t.status);
  if(!t.authorized&&!requiresAcceptance)return false;
  if(typeof t.assignment?.can_edit==='boolean')return t.assignment.can_edit;
  const auto=plainObject(t.automation);
  return Boolean(auto)&&(Boolean(t.authorized)||requiresAcceptance)&&!auto.active&&(requiresAcceptance||['inbox','discuss','working','fix'].includes(t.status))
    &&!listOf(auto.jobs).some(j=>['queued','running'].includes(j.state))&&(!auto.delivery||t.status==='discuss');
}
function assignmentValue(t){
  const a=plainObject(t.assignment)||{};const life=t.team==='life';
  return {taskId:t.id,version:Number.isSafeInteger(a.version)?a.version:0,worker:typeof a.worker==='string'?a.worker:'',integrator:typeof a.integrator==='string'?a.integrator:(life?'assistant':'claude'),
    discussion_workers:Array.isArray(a.discussion_workers)?[...a.discussion_workers]:life?['assistant','claude','codex']:['claude','codex'],
    reviewers:Array.isArray(a.reviewers)?[...a.reviewers]:listOf(t.effective_reviewers).length?[...t.effective_reviewers]:['claude','grok'],dirty:false};
}
function assignmentSame(a,b){return a.worker===b.worker&&a.integrator===b.integrator&&JSON.stringify([...a.discussion_workers].sort())===JSON.stringify([...b.discussion_workers].sort())&&JSON.stringify([...a.reviewers].sort())===JSON.stringify([...b.reviewers].sort());}
function assignmentPanel(t){
  const current=assignmentValue(t),editable=assignmentEditable(t),saved=current.version>0;
  const requiresAcceptance=t.assignment?.requires_acceptance===true;
  if(!saved&&!editable&&!(app.assignmentDraft?.taskId===t.id&&app.assignmentDraft.dirty))return null;
  const panel=node('section','work-panel assignment-panel');panel.setAttribute('aria-label','指定分工');
  const head=node('div','work-head');head.append(node('h2','',saved?'這件事的分工':'指定這件事的分工'));
  if(saved)head.append(node('span','work-state idle','已儲存'));panel.append(head);
  if(saved){
    const summary=node('dl','assignment-summary');
    for(const [label,value]of [['本輪執行',current.worker?person(current.worker):'依額度自動'],['討論參與',current.discussion_workers.map(person).join('、')||'未指定'],['意見整合',person(current.integrator)],['獨立複核',current.reviewers.map(person).join('、')||'未指定']])summary.append(node('dt','',label),node('dd','',value));
    panel.append(summary);
    const at=t.assignment?.updated_at;panel.append(node('p','work-hint',(at?'儲存於 '+fullTime(at)+'。':'')+'儲存分工不會啟動工作。'));
  }
  if(t.team==='life')panel.append(node('p','work-hint','助理維持生活主責；本輪執行人可另指定。'));
  if(!editable){
    if(t.assignment?.edit_reason)panel.append(node('p','work-hint',t.assignment.edit_reason));
    const draft=app.assignmentDraft;
    if(draft?.taskId===t.id&&draft.dirty){
      const held=node('div','assignment-conflict');held.append(node('p','','你尚未送出的分工暫存：本輪執行 '+(draft.worker?person(draft.worker):'依額度自動')+'；討論 '+draft.discussion_workers.map(person).join('、')+'；整合 '+person(draft.integrator)+'；複核 '+draft.reviewers.map(person).join('、')+'。目前無法調整分工，草稿仍保留，待可編輯時再核對版本。'));
      const discard=node('button','work-button','放棄未送出的分工草稿');discard.type='button';discard.addEventListener('click',()=>{app.assignmentDraft=null;applyDetail(app.detailTask);scheduleReloadCheck();});held.append(discard);panel.append(held);
    }
    return panel;
  }
  if(!app.assignmentDraft||app.assignmentDraft.taskId!==t.id||!app.assignmentDraft.dirty)app.assignmentDraft=assignmentValue(t);
  const draft=app.assignmentDraft;
  const edit=keepable(node('details','assignment-editor'),'assignment-edit',!saved||draft.dirty);edit.append(node('summary','',saved?'調整分工':'選擇本輪人選'));
  const form=node('form','assignment-form');form.id='assignment-form-'+t.id;form.noValidate=true;
  const fields=node('div','assignment-fields');
  const workerLabel=node('label','form-field');workerLabel.append(node('span','','本輪執行人'));
  const worker=node('select');worker.name='assignment_worker';worker.dataset.assignmentField='worker';worker.setAttribute('aria-label','本輪執行人');
  for(const who of ['', 'claude','codex',...(t.team==='life'?['assistant']:[])]){const option=node('option','',who?person(who):'依額度自動');option.value=who;worker.append(option);}worker.value=draft.worker;workerLabel.append(worker);fields.append(workerLabel);
  const integratorLabel=node('label','form-field');integratorLabel.append(node('span','','討論整合者'));const integrator=node('select');integrator.name='assignment_integrator';integrator.dataset.assignmentField='integrator';
  for(const who of (t.team==='life'?['assistant','claude','codex']:['claude','codex'])){const option=node('option','',person(who));option.value=who;integrator.append(option);}integrator.value=draft.integrator;integratorLabel.append(integrator);fields.append(integratorLabel);
  const discussionNames=t.team==='life'?['assistant','claude','codex']:['claude','codex'];
  const reviewerNames=['claude','codex','grok','assistant'];
  const discussionInputs=[],reviewerInputs=[];
  function choices(title,kind,people,chosen,inputs){
    const group=node('fieldset','assignment-choices');group.append(node('legend','',title));const row=node('div','assignment-checks');
    for(const who of people){const label=node('label','assignment-check');const input=node('input');input.type='checkbox';input.name='assignment_'+kind+'_'+who;input.value=who;input.dataset.assignmentField=kind;input.checked=chosen.includes(who);const text=person(who)+(who==='assistant'&&t.team!=='life'?'・跨區複核':'');input.setAttribute('aria-label',title+'：'+text);label.append(input,node('span','',text));row.append(label);inputs.push(input);}group.append(row);return group;
  }
  fields.append(choices('討論參與（可複選）','discussion',discussionNames,draft.discussion_workers,discussionInputs),choices('獨立複核（可複選）','reviewer',reviewerNames,draft.reviewers,reviewerInputs));
  form.append(fields,node('p','work-hint','討論至少 1 位；獨立複核至少 1 位且排除執行人。Grok 可參與討論、總結及第三方複核。'));
  form.append(node('p','assignment-save-note',requiresAcceptance?'這張單尚未收件；按下後會收下提案並儲存人選，不會開始討論、檢查或實作。':'儲存只更新人選，不會開始討論、檢查或實作。'));
  const error=node('p','form-error');error.setAttribute('role','alert');error.hidden=true;
  const row=node('div','work-buttons');const save=node('button','work-button primary',requiresAcceptance?'收件並儲存分工':'儲存分工');save.type='submit';row.append(save);form.append(error,row);
  function syncDraft(){
    draft.worker=worker.value;draft.integrator=integrator.value;draft.discussion_workers=discussionInputs.filter(n=>n.checked).map(n=>n.value);
    for(const input of reviewerInputs){const excluded=input.value===draft.worker;const required=t.team==='life'&&Boolean(draft.worker)&&draft.worker!=='assistant'&&input.value==='assistant';input.disabled=excluded||required;if(excluded)input.checked=false;if(required)input.checked=true;input.closest('label').classList.toggle('assignment-excluded',excluded);}
    draft.reviewers=reviewerInputs.filter(n=>n.checked&&! (n.value===draft.worker)).map(n=>n.value);
    draft.dirty=!assignmentSame(draft,current);const conflict=draft.version!==current.version;
    save.disabled=!draft.discussion_workers.length||!draft.reviewers.length||conflict||(saved&&!draft.dirty&&!requiresAcceptance);
  }
  worker.addEventListener('change',syncDraft);integrator.addEventListener('change',syncDraft);[...discussionInputs,...reviewerInputs].forEach(input=>input.addEventListener('change',syncDraft));
  syncDraft();
  if(draft.version!==current.version){
    const warning=node('div','assignment-conflict');warning.append(node('p','','分工已有更新。你的草稿仍保留，請載入最新分工後再調整。'));
    const reload=node('button','work-button','放棄草稿，載入最新分工');reload.type='button';reload.addEventListener('click',()=>{app.assignmentDraft=null;applyDetail(app.detailTask);});warning.append(reload);form.prepend(warning);
  }
  form.addEventListener('submit',event=>{event.preventDefault();syncDraft();if(save.disabled)return;sendControl(t,'assign',save,{accept_proposal:requiresAcceptance,assignment:{worker:draft.worker||null,integrator:draft.integrator,discussion_workers:[...draft.discussion_workers],reviewers:[...draft.reviewers],version:draft.version}});});
  edit.append(form);panel.append(edit);return panel;
}

// -- 工作進度 --
function sortedJobs(auto){const key=j=>{const d=parseTime(j.created_at||j.started_at).getTime();return Number.isFinite(d)?d:0;};return listOf(auto.jobs).filter(plainObject).sort((a,b)=>key(b)-key(a)||Number(b.id)-Number(a.id));}
function sourceRecovery(auto){return plainObject(auto?.source_recovery)||sortedJobs(auto||{}).map(j=>plainObject(j.source_recovery)).find(Boolean)||null;}
function sourceHistory(job,auto){const recovery=plainObject(job.source_recovery)||sourceRecovery(auto);return Boolean(recovery&&Number(recovery.origin_job_id)===Number(job.id)&&Number(recovery.resumed_job_id)>0&&!listOf(job.user_actions).length);}
function jobHistory(job,auto){return Boolean(job.retry_job_id)||job.state==='cancelled'||job.superseded===true||sourceHistory(job,auto)||(['failed','blocked'].includes(job.state)&&Array.isArray(auto?.attention_job_ids)&&!auto.attention_job_ids.includes(job.id));}
function currentJobs(auto){return listOf(auto?.jobs).filter(j=>plainObject(j)&&!jobHistory(j,auto));}
function workPaused(auto){return auto?.paused===true;}
function needsAttention(auto){if(Array.isArray(auto.attention_job_ids))return auto.attention_job_ids.some(id=>{const job=listOf(auto.jobs).find(j=>j.id===id);return !job||!jobHistory(job,auto);});return currentJobs(auto).some(j=>['failed','blocked'].includes(j.state));}
function sourceJob(job,auto){const recovery=sourceRecovery(auto);return Boolean(plainObject(job.source_recovery)||(recovery&&[recovery.origin_job_id,recovery.resumed_job_id].some(id=>Number(id)===Number(job.id))));}
function blockedLabel(auto){const blocked=currentJobs(auto).filter(j=>j.state==='blocked');return blocked.length&&blocked.every(j=>sourceJob(j,auto))?'待Codex補交來源':blocked.length+' 件待補資料';}
function workStatus(auto){
  if(!auto)return node('span','work-state none','派工資訊未提供');
  const jobs=currentJobs(auto);
  if(jobs.some(j=>listOf(auto.attention_job_ids).includes(j.id)&&listOf(j.user_actions).length&&!j.human_response&&!j.human_obsolete))return node('span','work-state stuck','有一件待你操作');
  if(workPaused(auto)&&jobs.some(j=>j.state==='blocked'&&listOf(j.blockers).length))return node('span','work-state paused',blockedLabel(auto));
  if(workPaused(auto))return node('span','work-state paused','已暫停 · 這一步做完就停');
  if(jobs.some(j=>j.state==='running'))return node('span','work-state running','有工作正在執行');
  if(jobs.some(j=>j.state==='queued'))return node('span','work-state running','排隊等執行');
  if(jobs.some(j=>j.state==='blocked'))return node('span','work-state stuck',jobs.filter(j=>j.state==='blocked').length+' 件待補資料');
  if(needsAttention(auto))return node('span','work-state stuck','上次工作待核對');
  return node('span','work-state idle',jobs.length?'目前沒有進行中的工作':'還沒派工');
}
function blockerDetails(job){
  const items=listOf(job.blockers);if(!items.length)return null;
  const details=keepable(node('details','job-blockers'),'job-blockers-'+job.id,false);details.append(node('summary','','缺件明細（'+items.length+'項）'));
  const list=node('ul');for(const item of items)list.append(node('li','',String(item??'')));details.append(list);return details;
}
function jobRow(job,auto){
  const row=node('div','job-row');row.append(avatar(knownWorker(job.worker)||'unknown'));
  const text=node('div','job-text');const state=typeof job.state==='string'?job.state:'';
  const head=node('div','job-head');
  head.append(node('strong','',person(job.worker)+' · '+(job.integration?'整合':labelOf(jobKinds,job.kind,clip(job.kind,12)||'工作'))),
              node('span','job-state '+(labelOf(jobStates,state,null)?state:'unknown'),state==='blocked'?(listOf(job.user_actions).length&&!job.human_response&&!job.human_obsolete?'待你操作':sourceHistory(job,auto)?'先前缺件紀錄':jobHistory(job,auto)?'先前卡點紀錄':sourceJob(job,auto)?'待Codex補交來源':'待Codex處理'):labelOf(jobStates,state,'狀態待確認')));
  text.append(head);
  const bits=[];
  if(job.model_selection?.model)bits.push('本次指定：'+job.model_selection.model);
  if(job.model_selection?.effort)bits.push('思考強度：'+effortLabel(job.model_selection.effort));
  if(job.stage)bits.push(clip(job.stage,60));
  if(state==='running'&&job.started_at)bits.push('已跑 '+runElapsed(job));
  const runtime=job.run_id&&executionRuns.find(r=>r.id===job.run_id);
  if(runtime&&state==='running')bits.push(executionState(runtime)==='unknown'?'執行回報待確認':'最後回報 '+fullTime(runtime.updated_at));
  if(state==='queued'&&Number.isInteger(job.queue_ahead))bits.push(job.queue_ahead?'佇列前方 '+job.queue_ahead+' 件':'等待空出執行位置');
  if(job.finished_at)bits.push('結束 '+fullTime(job.finished_at));
  else if(job.started_at)bits.push('開始 '+fullTime(job.started_at));
  else if(job.created_at)bits.push('建立 '+fullTime(job.created_at));
  if(bits.length)text.append(node('span','job-meta',bits.join(' · ')));
  if(job.error)text.append(node('span','job-error',clip(job.error,300)));
  const blockers=blockerDetails(job);if(blockers)text.append(blockers);
  row.append(text);return row;
}
function sourceRecoverySummary(auto){
  const recovery=sourceRecovery(auto);if(!recovery)return null;
  const box=node('section','source-recovery-summary');const labels={queued:'來源已補接 · 已排入接續工作',running:'來源已補接 · 正在接續核對',completed:'來源接續工作已回報結果',blocked:'待Codex補交來源',failed:'來源接續失敗 · 待Codex處理'};
  box.append(node('h3','',labelOf(labels,recovery.state,'待Codex處理來源')),node('p','','處理夥伴：'+person(recovery.owner||'codex')));
  if(recovery.reason)box.append(node('p','',String(recovery.reason)));
  if(recovery.state==='completed')box.append(node('p','','來源接續的結果已保留；這件事是否完成，仍依本輪交付與獨立複核結果判斷。'));
  const refs=listOf(recovery.reference_tasks).filter(r=>plainObject(r)&&r.relation==='reference'&&Number.isSafeInteger(r.id)&&r.id>0);
  if(refs.length){const line=node('p','','參考來源：');for(const ref of refs){const link=node('a','source-reference','任務 #'+ref.id+' · '+clip(ref.title,120));link.href='/t/'+ref.id;link.target='_blank';link.rel='noopener noreferrer';line.append(link);}box.append(line,node('p','source-reference-note','參考任務提供來源，不代表這件事已完成或已獲准實作。'));}
  return box;
}
function planGroup(label,items,full=false){
  const box=node('div','plan-group');box.append(node('span','',label));
  const values=listOf(items).slice(0,20).map(v=>full?String(v??''):clip(v,200)).filter(Boolean);
  if(!values.length){box.append(node('p','job-meta','（未提供）'));return box;}
  const list=node('ul');for(const v of values)list.append(node('li','',v));box.append(list);return box;
}
function planSteps(steps){
  const box=node('div','plan-group');box.append(node('span','','怎麼分工（依序）'));
  const values=listOf(steps).filter(plainObject).slice(0,20);
  if(!values.length){box.append(node('p','job-meta','（未提供）'));return box;}
  const list=node('ol');
  for(const s of values){const li=node('li','',clip(s.title,150)||'（未命名步驟）');
    li.append(node('span','plan-step-role',' — '+person(s.worker)+' · '+labelOf(jobKinds,s.kind,clip(s.kind,12)||'工作')));list.append(li);}
  box.append(list);return box;
}
function planBlock(plan){
  const box=keepable(node('details','plan-block'),'plan',true);
  if(app.detailPlanId!==plan.id){box.open=true;app.detailPlanId=plan.id;}
  box.append(node('summary','','要照著做的計畫：'+(clip(plan.summary,120)||'（未附摘要）')));
  const body=node('div','plan-body');
  body.append(planGroup('要做的範圍',plan.scope));
  if(listOf(plan.disagreements).length)body.append(planGroup('各家分歧（保留原主張）',plan.disagreements,true));
  if(listOf(plan.absences).length)body.append(planGroup('這輪沒有意見的夥伴',plan.absences,true));
  if(listOf(plan.assumptions).length)body.append(planGroup('暫採假設',plan.assumptions));
  if(listOf(plan.missing_items??plan.pending_items).length)body.append(planGroup('待補資料',plan.missing_items??plan.pending_items));
  if(listOf(plan.workflow_actions).length)body.append(planGroup('接續安排（非缺件）',plan.workflow_actions.map(x=>x.text)));
  body.append(planSteps(plan.steps),planGroup('做完要看到什麼（驗收）',plan.acceptance));
  if(plan.execution){body.append(planGroup('正式執行的機器與範圍',Object.entries(plan.execution.scope||{}).map(([host,paths])=>host+'：'+listOf(paths).join('、'))));const ops=node('ol','execution-commands');for(const step of listOf(plan.execution.commands)){const li=node('li');li.append(node('strong','',step.title+' · '+step.host+' · '+(step.check?'重新驗證':'實際變更')+(step.after_human?' · 人工操作後':'')),node('code','',listOf(step.argv).join(' ')));ops.append(li);}body.append(ops,planGroup('回復方法',plan.execution.rollback));}
  else if(listOf(plan.steps).some(x=>x.kind==='implement'))body.append(node('p','work-hint','這份是候選檔案計畫，尚未包含正式部署步驟。若目標是更新正式服務，請先整理含正式執行的方案。'));
  const meta=['計畫 '+clip(plan.id,24),labelOf(planStates,plan.status,clip(plan.status,20)||'狀態未提供')];
  if(plan.created_at)meta.push(fullTime(plan.created_at)+' 提出');
  if(plan.plan_sha)meta.push('指紋 '+clip(plan.plan_sha,12));
  body.append(node('p','plan-meta',meta.join(' · ')));box.append(body);return box;
}

// -- 送出派工：每次提交都帶新的 request_id，避免重送變成兩件工作。 --
function requestId(){try{if(self.crypto&&crypto.randomUUID)return crypto.randomUUID();}catch{}return 'req-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10);}
async function sendControl(t,action,button,extra){
  if(submissionBusy())return;
  const panel=button.closest('.work-panel,.handover-panel');const error=panel?.querySelector('.form-error');
  const buttons=panel?[...panel.querySelectorAll(action==='assign'?'.work-button,[data-assignment-field]':action==='models'?'.work-button,select[name^=model_]':'.work-button')]:[button];
  const note=panel?.querySelector('[name="work_note"]');
  const deliveryNote=['accept_delivery','request_changes'].includes(action)?panel?.querySelector('[name="acceptance_note_'+extra?.target_id+'"]'):null;
  if(note)buttons.push(note);if(deliveryNote)buttons.push(deliveryNote,...panel.querySelectorAll('[name^="accept_'+extra.target_id+'_"]'));
  const disabledBefore=new Map(buttons.map(b=>[b,b.disabled]));
  controlSubmissions.add(button);app.detailSubmitting=true;app.detailEpoch=(app.detailEpoch||0)+1;app.detailPending=null;buttons.forEach(b=>{b.disabled=true;});if(error)error.hidden=true;
  const payload={action,csrf:app.csrf,request_id:requestId(),...(extra||{})};
  const body=(extra&&Object.prototype.hasOwnProperty.call(extra,'body'))?extra.body:(note?.value||'').trim();if(body||action==='reviewers')payload.body=body;
  try{
    const data=await postWeb('/web/tasks/'+t.id+'/control',payload);
    if(note)note.value='';
    if(deliveryNote)deliveryNote.value='';
    if(action==='repair'){app.supplementFiles?.delete(t.id);const repairNote=panel?.querySelector('[name=repair_note_'+t.id+']');if(repairNote)repairNote.value='';}
    if(action==='assign')app.assignmentDraft=null;
    if(action==='models'){app.modelDraft=null;for(const n of panel.querySelectorAll('select[name^=model_],select[name^=effort_]'))formDefaults.set(n,fieldState(n));}
    if(plainObject(data)&&data.id!==undefined)applyDetail(data,true);else await openTask(t.id);
    toast(action==='models'?'模型已儲存，新排入的工作才會使用':action==='assign'?(payload.accept_proposal===true?'已收件並儲存分工，沒有啟動工作':'分工已儲存，沒有啟動工作'):labelOf(controlLabels,action,'指令')+'：已送出');load();
  }catch(e){
    const message=e instanceof SyntaxError?'辦公室回應看不懂，請重新整理後再試':(e.message||'操作未完成，請稍後再試');
    if(error){error.textContent=message;error.hidden=false;}else toast(message);
  }finally{buttons.forEach(b=>{if(b.isConnected)b.disabled=disabledBefore.get(b);});controlSubmissions.delete(button);app.detailSubmitting=false;afterSubmission();}
}
function workButton(t,action,extra,primary){
  const b=node('button','work-button'+(primary?' primary':''),labelOf(controlLabels,action,action));b.type='button';
  b.addEventListener('click',()=>sendControl(t,action,b,extra));return b;
}
function workActions(t,auto){
  const box=node('div','work-actions');
  const jobs=currentJobs(auto);const paused=workPaused(auto);
  const running=jobs.some(j=>j.state==='running'),queued=jobs.some(j=>j.state==='queued');
  const stuck=needsAttention(auto);
  const missing=paused&&jobs.some(j=>j.state==='blocked'&&listOf(j.blockers).length);
  const plan=listOf(auto.plans).filter(plainObject)[0];
  const usable=auto.start_ready===true&&Boolean(plan)&&plan.id!==undefined;
  if(t.team==='life'&&!plainObject(t.assignment)){
    const pick=node('div','reviewer-picker');pick.append(node('span','','複核夥伴（交付者會自動排除）'));
    const select=node('select');select.setAttribute('aria-label','指定複核夥伴');
    for(const [v,label] of [['','其他協作夥伴'],['codex,claude,grok','Claude、Codex與Grok'],['codex','Codex'],['claude','Claude'],['grok','Grok'],['codex,claude','Codex與Claude'],['codex,grok','Codex與Grok'],['claude,grok','Claude與Grok']]){const opt=node('option','',label);opt.value=v;select.append(opt);}
    select.value=t.reviewers||'';
    const button=node('button','work-button','儲存複核名單');button.type='button';button.disabled=running||queued;button.addEventListener('click',()=>sendControl(t,'reviewers',button,{body:select.value}));
    pick.append(select,button,node('small','','助理維持主責；由其他夥伴交付時，助理會參與複核。調整後重新整理計畫。'));box.append(pick);
  }
  const note=node('label','work-note');note.append(node('span','','附一句話給夥伴（選填）'));
  const input=node('input');input.type='text';input.name='work_note';input.maxLength=2000;input.placeholder='例如：先確認這份來源版本與驗收條件再往下';
  note.append(input);box.append(note);
  const choices=node('div','work-choices');
  for(const [action,title,description,label] of [
    ['discuss','只討論','交換想法、分析做法，不開始修改。','開始一輪討論'],
    ['check','先檢查','實際讀取現況並交付查核結果，不修改目標。','先做唯讀檢查'],
    ['plan','正式實作','先整理要改哪裡、要交什麼、怎麼驗收；你確認計畫後才動手。','準備正式實作']]){
    if(action==='discuss'&&(running||queued))continue;
    const card=node('div','work-choice');card.dataset.workChoice=action;
    card.append(node('h3','',title),node('p','',description));
    const button=workButton(t,action);button.textContent=label;button.disabled=action!=='discuss'&&(running||queued);card.append(button);
    if(action==='discuss'&&(running||queued))card.append(node('small','','會取消尚未開始的後續工作，已在執行的這一步會先做完。'));
    choices.append(card);
  }
  box.append(choices);
  if(running||queued||['review','approved','active','working'].includes(t.status)){const restart=workButton(t,'restart_discussion');box.append(node('p','work-hint','要明確重來，可用「回到討論」取消排隊工作、作廢草稿計畫並開新討論；已在執行的工作會保留結果。'),restart);}
  if(plan){
    const execution=node('div','execution-choice');execution.append(planBlock(plan));
    const readonly=listOf(plan.steps).length>0&&listOf(plan.steps).every(s=>s.kind==='check');
    execution.append(node('p','',readonly?'這份計畫只有唯讀檢查，確認後也不會修改目標。':'確認後會依這份計畫的範圍實際修改、交付，再由其他夥伴複核。'));
    const start=workButton(t,'start',{plan_id:plan.id},true);start.textContent=readonly?'確認這份計畫，執行唯讀檢查':'確認這份計畫，開始實作';
    if(plan.execution?.baseline_consent_required){start.disabled=true;start.textContent='請使用上方核准計畫操作，明確確認受保護路徑改動';}else start.disabled=!usable;start.title=auto.start_reason||'請先整理最新動工計畫';execution.append(start);box.append(execution);
  }else box.append(node('p','work-hint','要實際動手，先選「準備正式實作」。計畫出來後，這裡會顯示改動範圍與確認按鈕。'));
  const row=node('div','work-buttons');
  if(paused&&queued&&!missing&&!pendingHuman(t).length)row.append(workButton(t,'resume',null,true));
  else if(running||queued)row.append(workButton(t,'pause'));
  if(stuck&&!running&&!queued&&!missing)row.append(workButton(t,'retry'));
  box.append(row);
  const hints=[];
  if(Number(t.assignment?.version)>0)hints.push('本輪討論參與：'+listOf(t.assignment.discussion_workers).map(person).join('、')+'。');
  else if(t.team==='life')hints.push('生活區由助理主責；討論完由指定整合者（預設助理）整理一份計畫。');
  hints.push(auto.start_reason||'先整理動工計畫，再確認開始。');
  hints.push('工作進行中或待複核／待拍板／已啟用時，留言只加入紀錄；收件／討論／修正且沒有工作時才開新討論。');
  if(stuck&&!running&&!queued)hints.push('核對後接續會先確認結果與副作用，不直接重跑修改。');
  if(queued)hints.push('工作已排入佇列，最多同時處理 '+(auto.max_parallel||1)+' 件不同任務；不需要重試。');
  if(missing&&!pendingHuman(t).length)hints.push(blockedLabel(auto)==='待Codex補交來源'?'來源缺件由Codex處理，補接狀態與缺件明細列在下方。':'這一步由Codex核對卡點，缺件明細保留在下方。');
  else if(paused)hints.push('目前是暫停狀態，按「繼續往下做」才會接著跑。');
  if(hints.length)box.append(node('p','work-hint',hints.join(' ')));
  const error=node('p','form-error');error.setAttribute('role','alert');error.hidden=true;box.append(error);
  return box;
}
function handoverError(panel){const error=node('p','form-error');error.hidden=true;error.setAttribute('role','alert');panel.append(error);}
function checklist(panel,items,prefix,disabled){
  const box=node('div','acceptance-checklist');const inputs=[];
  listOf(items).forEach((item,index)=>{const label=node('label');const input=node('input');input.type='checkbox';input.name=prefix+'_'+index;input.disabled=disabled;label.append(input,node('span','',item));box.append(label);inputs.push(input);});panel.append(box);return inputs;
}
function downloadLink(label,url){const a=node('a','work-button',label);a.href=url;a.setAttribute('download','');return a;}
// 成果直接在頁面上看：HTML 放進不給任何權限的沙箱框（只顯示靜態畫面、不跑 script），SVG 當圖片，文字類按需展開。
const PREVIEW_HTML=/\.html?$/i,PREVIEW_SVG=/\.svg$/i,PREVIEW_TEXT=/\.(md|markdown|txt|py|js|mjs|ts|json|css|sh|ya?ml|toml|csv|tsv|log|conf|ini|service|timer|sql|xml|diff|patch)$/i;
const PREVIEW_TEXT_LIMIT=100000,PREVIEW_TEXT_AUTO=2048;
function previewFrame(url,name){
  const frame=document.createElement('iframe');
  frame.className='delivery-preview-frame';frame.setAttribute('sandbox','');frame.referrerPolicy='no-referrer';frame.loading='lazy';frame.title='成果預覽：'+name;frame.src=url;return frame;
}
function artifactPreview(base,file,index,firstHtml){
  const name=String(file?.name||''),size=Number.isFinite(file?.bytes)?file.bytes:null,url=base+'/preview/'+index,raw=base+'/files/'+index;
  const label=name+(size==null?'':'，'+size+' bytes');
  if(PREVIEW_HTML.test(name)){
    const note=node('small','delivery-preview-note','靜態預覽：不執行頁面裡的程式，互動效果請下載後在本機開啟。');
    if(firstHtml){const box=node('div','delivery-preview');box.append(previewFrame(url,name),note);return box;}
    const box=node('details','delivery-preview-more');const summary=node('summary','','預覽（'+label+'）');box.append(summary);
    box.addEventListener('toggle',()=>{if(box.open&&!box.dataset.loaded){box.dataset.loaded='1';box.append(previewFrame(url,name),note);}});
    return box;
  }
  if(PREVIEW_SVG.test(name)){
    const wrap=node('div','delivery-preview-svg');const img=document.createElement('img');img.className='delivery-preview-image';img.loading='lazy';img.alt='成果預覽：'+name;
    // 只寫 viewBox、沒寫寬度的 SVG，瀏覽器會縮成 300px 寬：改讀根節點的 viewBox 寬度當顯示寬度（120〜1600px），太寬就左右滑。
    img.addEventListener('load',()=>{
      fetch(raw,{credentials:'same-origin',cache:'no-store'}).then(r=>r.ok?r.text():'').then(text=>{
        const root=(/<svg\b[^>]*>/i.exec(text.slice(0,4000))||[''])[0];
        if(!root||/\swidth\s*=\s*["']\s*[\d.]+\s*(px)?\s*["']/i.test(root))return;
        const m=/viewBox\s*=\s*["']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(root);
        const w=m?Number(m[1]):NaN;if(Number.isFinite(w)&&w>0)img.style.width=Math.min(1600,Math.max(120,w))+'px';}).catch(()=>{});},{once:true});
    img.src=url;wrap.append(img);return wrap;
  }
  if(PREVIEW_TEXT.test(name)){
    const box=node('details','delivery-preview-text');const summary=node('summary','','展開內容（'+label+'）');const pre=node('pre');box.append(summary,pre);
    const load=()=>{if(pre.dataset.loaded)return;pre.dataset.loaded='1';pre.textContent='讀取中…';
      fetch(raw,{credentials:'same-origin',cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.text();})
        .then(text=>{pre.textContent=text.length>PREVIEW_TEXT_LIMIT?text.slice(0,PREVIEW_TEXT_LIMIT)+'\n…（已截斷，完整內容請下載）':text;})
        .catch(()=>{pre.textContent='讀取失敗，收起再展開可重試，或改用下載。';delete pre.dataset.loaded;});};
    box.addEventListener('toggle',()=>{if(box.open)load();});
    if(size!=null&&size<=PREVIEW_TEXT_AUTO)box.open=true;
    return box;
  }
  return null;
}
function deliveryPanel(t){
  const d=plainObject(t.automation?.delivery);if(!d)return null;
  const panel=node('section','handover-panel delivery-panel');panel.append(node('h2','','成果與驗收'));
  panel.append(node('p','handover-subtitle',(d.kind==='check'?'唯讀查核報告':d.kind==='implement'?(listOf(d.execution_receipts).some(x=>!x.check)?'實作成果 · 已執行正式步驟':'實作成果 · 候選工作區'):'交付紀錄')+' · '+person(d.worker)+' · '+fullTime(d.created_at)));
  const base='/web/tasks/'+t.id+'/deliveries/'+d.delivery_id;
  panel.append(downloadLink('下載本輪成果報告',base+'/report'));
  const report=keepable(node('details','delivery-report'),'delivery-'+d.delivery_id,false);report.append(node('summary','','展開本輪成果報告'),node('div','',d.report||'沒有報告內容'));panel.append(report);
  const files=node('div','delivery-files');
  let htmlShown=false;
  listOf(d.artifacts).forEach((file,index)=>{const row=node('div','delivery-file');row.append(node('strong','',file.name),node('small','',file.bytes+' bytes · SHA256 '+clip(file.sha256,12)),downloadLink('下載檔案',base+'/files/'+index));
    const isHtml=PREVIEW_HTML.test(String(file?.name||''));const preview=artifactPreview(base,file,index,isHtml&&!htmlShown);if(isHtml)htmlShown=true;if(preview)row.append(preview);files.append(row);});
  if(files.childElementCount)panel.append(files);
  else panel.append(node('p','handover-subtitle',d.kind==='check'?'本輪交付為查核報告；是否符合需求，請依下列項目驗收。':'這版沒有登記可下載的實作檔案，請先核對報告與來源。'));
  panel.append(evidenceCards(t,d));
  if(listOf(d.evidence).length)panel.append(planGroup('已做的檢查與證據',d.evidence));
  if(listOf(d.limitations).length)panel.append(planGroup('尚未驗證或需要後續處理',d.limitations));
  const accepted=d.acceptance?.decision==='accepted';
  panel.append(node('h3','',accepted?'這版已由你驗收':'逐項驗收這版成果'));
  if(accepted)panel.append(node('p','acceptance-result','驗收通過 · '+fullTime(d.acceptance.created_at)));
  const busy=listOf(t.automation?.jobs).some(j=>['queued','running'].includes(j.state));
  const canAct=workActionsReady(t)&&!busy&&!accepted;
  const inputs=checklist(panel,d.criteria,'accept_'+d.delivery_id,!canAct||t.status!=='approved');
  if(accepted)inputs.forEach(n=>{n.checked=true;});
  panel.append(node('p','handover-subtitle','驗收只確認這版成果符合需求；正式環境是否已更新，依交付證據判斷。'));
  if(workActionsReady(t)&&!accepted){
    const note=node('textarea');note.name='acceptance_note_'+d.delivery_id;note.maxLength=4000;note.rows=2;note.placeholder='需要修正的地方，或驗收補充說明';note.setAttribute('aria-label','驗收意見');panel.append(note);
    const row=node('div','work-buttons');
    // 每次點擊取目前勾選與意見，並綁定這版交付。
    const pass=node('button','work-button primary','驗收通過');pass.type='button';
    const changes=node('button','work-button','要求修正');changes.type='button';
    const refresh=()=>{pass.disabled=!canAct||t.status!=='approved'||!inputs.length||inputs.some(n=>!n.checked);changes.disabled=busy||!note.value.trim();};
    inputs.forEach(n=>n.addEventListener('change',refresh));note.addEventListener('input',refresh);refresh();
    pass.addEventListener('click',()=>sendControl(t,'accept_delivery',pass,{target_id:d.delivery_id,checked:inputs.flatMap((n,i)=>n.checked?[i]:[]),body:note.value.trim()}));
    changes.addEventListener('click',()=>sendControl(t,'request_changes',changes,{target_id:d.delivery_id,body:note.value.trim()}));row.append(pass,changes);panel.append(row);
    if(t.status!=='approved')panel.append(node('p','handover-subtitle','待本輪獨立複核通過後，即可勾選並送出驗收。'));
  }
  handoverError(panel);return panel;
}
// 本人回報之後仍顯示實際接續狀態；不把勾選或程序完成當成正式可用。
function continuationPanel(t){
  if(pendingHuman(t).length)return null;
  const jobs=listOf(t.automation?.jobs);
  const original=jobs.filter(j=>j.human_response&&!j.human_obsolete).sort((a,b)=>b.id-a.id)[0];
  if(!original)return null;
  const next=jobs.find(j=>j.id===original.human_response.continuation_job);
  const panel=node('section','handover-panel continuation-panel');
  panel.append(node('h2','','操作已回報，夥伴接續處理'));
  const statuses={queued:'已排入核對佇列',running:'正在核對並接續原工作',completed:'接續工作已回報結果',blocked:'接續工作仍有卡點',failed:'接續工作執行失敗',cancelled:'這次接續已取消'};
  panel.append(node('p','continuation-status',person(next?.worker||original.worker)+' · '+labelOf(statuses,next?.state,'接續狀態待確認')));
  panel.append(node('p','handover-subtitle','你回報的操作：'+listOf(original.user_actions).map(a=>a.title).join('；')));
  if(next?.state==='queued'||next?.state==='running')panel.append(node('p','handover-subtitle','夥伴會先核對操作結果，再依原計畫接續；不用再按一次開始。'));
  else if(next?.state==='completed')panel.append(node('p','handover-subtitle','請看本輪成果與實測結果。正式可用還需要啟用後的驗證，執行結束本身不代表通過。'));
  else panel.append(node('p','handover-subtitle','請看下方目前進度與卡點；操作回報已保留。'));
  if(next&&listOf(next.blockers).length)panel.append(planGroup('接下來要處理',next.blockers));
  return panel;
}
function humanPanel(t){
  const jobs=pendingHuman(t);if(!jobs.length)return null;
  const panel=node('section','handover-panel human-panel');panel.append(node('h2','','待你操作'));
  panel.append(node('p','handover-subtitle','這一件工作待你操作；其他工作會繼續。完成後回報，夥伴會先核對結果，再沿原工作接續。'));
  for(const job of jobs){
    const group=node('div','human-job');group.append(node('h3','',person(job.worker)+'需要你協助'));
    const actions=listOf(job.user_actions);
    for(const action of actions){const card=node('div','human-action');card.append(node('strong','',action.title),node('p','','操作位置：'+action.where),node('p','action-instructions',action.instructions),node('p','','完成條件：'+action.done_when));
      if(action.url){try{const url=new URL(action.url);if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password){const a=node('a','work-button','開啟操作入口');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';card.append(a);}}catch{}}
      if(['password','login'].includes(action.kind))card.append(node('small','','請在原登入頁或指定終端輸入；辦公室不收取密碼。'));group.append(card);
    }
    const inputs=checklist(group,actions.map(a=>'已完成：'+a.title),'human_'+job.id,!workActionsReady(t));
    if(workActionsReady(t)){const button=node('button','work-button primary','我已完成，請核對並接續');button.type='button';button.disabled=true;const refresh=()=>{button.disabled=inputs.some(n=>!n.checked);};inputs.forEach(n=>n.addEventListener('change',refresh));button.addEventListener('click',()=>sendControl(t,'complete_action',button,{target_id:job.id,checked:inputs.flatMap((n,i)=>n.checked?[i]:[]),body:''}));group.append(button);}
    panel.append(group);
  }
  handoverError(panel);return panel;
}
function workPanel(t){
  const auto=plainObject(t.automation);const panel=node('section','work-panel');
  const head=node('div','work-head');head.append(node('h2','','這件事現在的進度'),workStatus(auto));panel.append(head);
  if(auto){
    const missing=currentJobs(auto).some(j=>j.state==='blocked'&&listOf(j.blockers).length),recovery=sourceRecovery(auto);
    panel.append(node('p','work-mode',workPaused(auto)?'已暫停 · 等待核對後接續':currentJobs(auto).some(j=>['queued','running'].includes(j.state))?'仍有工作排隊或進行中':pendingHuman(t).length?'有一件待你操作 · 請看上方操作卡':missing?blockedLabel(auto):t.status==='approved'?(auto.delivery?.acceptance?.decision==='accepted'?'這版成果已驗收 · 是否可正式使用，請核對實測結果':'夥伴複核通過 · 等你驗收成果'):recovery&&currentJobs(auto).some(j=>['queued','running'].includes(j.state))?'正在接續本輪工作 · 最新進度如下':auto.mode==='execute'?'動工中 · 依核准範圍執行與複核':'討論中 · 看過最新計畫後再開始'));
    const recovered=sourceRecoverySummary(auto);if(recovered)panel.append(recovered);
    const jobs=sortedJobs(auto);
    if(jobs.length){
      const current=jobs.filter(j=>!jobHistory(j,auto));
      const active=current.filter(j=>['queued','running'].includes(j.state)).sort((a,b)=>(a.state==='running'?0:1)-(b.state==='running'?0:1)||Number(a.id)-Number(b.id));
      const attention=current.filter(j=>listOf(auto.attention_job_ids).includes(j.id));
      const visible=active.length?[...active,...attention.filter(j=>!active.includes(j))]:current.slice(0,5);
      const history=jobs.filter(j=>!visible.includes(j));
      const box=node('div','work-jobs');for(const j of visible)box.append(jobRow(j,auto));
      panel.append(box);
      if(history.length){const archive=keepable(node('details','work-history'),'work-history-'+t.id,false);archive.append(node('summary','','先前工作紀錄（'+history.length+'項）'));const rows=node('div','work-jobs');for(const j of history)rows.append(jobRow(j,auto));archive.append(rows);panel.append(archive);}
    }else panel.append(node('p','work-empty','還沒有派出去的工作。'));
  }else panel.append(node('p','work-empty','辦公室還沒回報這件事的派工資訊，先看下面的討論紀錄。'));
  const runtime=runSlot(t.id,true);runtime.dataset.jobRunIds=JSON.stringify(listOf(auto?.jobs).map(j=>j.run_id).filter(Boolean));panel.append(runtime);
  const strip=capacityBlock();if(strip)panel.append(strip);
  const sync=node('p','work-sync');sync.id='detail-sync-note';panel.append(sync);
  paintDetailSync(sync);
  return panel;
}

// -- 用量摘要：百分比都是剩餘，只作建議，未自動限制派工。 --
const capacity={agents:[],mode:'advisory',at:null,fetched:0,ok:false,available:false,absent:false,misses:0};
let capacityLoading=false;
function capacityStale(){
  if(!capacity.ok)return true;
  if(Date.now()-capacity.fetched>300000)return true;
  const at=capacity.at?parseTime(capacity.at).getTime():NaN;
  return Number.isFinite(at)?Date.now()-at>900000:true;
}
function capacityRow(a,stale){
  const row=node('div','capacity-row');const worker=typeof a.worker==='string'?a.worker:'';
  row.append(avatar(knownWorker(worker)||'unknown'));
  const text=node('div','capacity-text');const line=node('div','capacity-line');
  const percent=node('span','capacity-percent'+(stale?' stale':''),percentText(a.remaining_percent)+(stale?'（待更新）':''));
  line.append(node('strong','',clip(a.label,24)||person(worker)),percent,
              node('span','capacity-state '+(labelOf(capacityStates,a.state,null)?a.state:'unknown'),labelOf(capacityStates,a.state,'狀態未知')));
  text.append(line);
  const windows=listOf(a.windows).filter(plainObject).slice(0,3)
    .map(w=>(clip(w.label,12)||'視窗')+' 剩 '+percentText(w.remaining)+(w.resets_at?'（'+fullTime(w.resets_at)+' 重置）':'')).join(' · ');
  if(windows)text.append(node('span','capacity-meta',windows));
  if(worker==='claude'||worker==='assistant')text.append(node('span','capacity-meta','共用帳號池：Claude與助理同一個 Claude 帳號'));
  if(typeof a.reason==='string'&&a.reason.trim())text.append(node('span','capacity-meta',clip(a.reason,120)));
  if(worker==='codex'){
    const reserve=plainObject(a.reset_credits);
    const valid=!stale&&reserve?.status==='ok'&&Number.isInteger(reserve.available_count);
    text.append(node('span','capacity-meta reset-credits',valid?'重置券 '+reserve.available_count+' 張'+(reserve.next_expiry?' · 最近到期 '+fullTime(reserve.next_expiry):''):'重置券待確認'));
    if(valid)text.append(node('span','capacity-meta',clip(reserve.suggestion,180)));
  }
  if(a.at){row.title='來源更新 '+fullTime(a.at);text.append(node('span','capacity-meta','來源更新 '+fullTime(a.at)));}
  row.append(text);return row;
}
function capacityBlock(){
  if(!capacity.available)return null;
  const box=node('div','capacity-strip');const stale=capacityStale();
  const head=node('div','capacity-head');head.append(node('span','','夥伴剩餘用量'));
  if(stale)head.append(node('span','capacity-flag','待更新'));
  box.append(head);
  for(const a of capacity.agents.filter(a=>!a.team||app.team==='all'||(a.teams||[a.team]).includes(app.team)))box.append(capacityRow(a,stale));
  if(!capacity.agents.length)box.append(node('p','capacity-meta','目前沒有可顯示的夥伴用量。'));
  box.append(node('p','capacity-note','百分比是剩餘額度，'+(capacity.mode==='advisory'?'只作派工建議，系統不會自動擋。':'依後端規則處理。')+
    (stale?'資料待更新，最後一次是 '+(capacity.at?fullTime(capacity.at):'時間未提供')+'，不代表現在的狀況。':'')));
  return box;
}
function paintCapacity(){
  for(const row of $$('.team-person')){
    const av=row.querySelector('.avatar');const who=['claude','codex','grok','assistant','gemini'].find(w=>av?.classList.contains(w));
    let chip=row.querySelector('.capacity-chip');
    const agent=capacity.available&&who?capacity.agents.find(a=>a.worker===who):null;
    if(!agent){if(chip)chip.remove();continue;}
    if(!chip){chip=node('span','capacity-chip');row.append(chip);}
    const stale=capacityStale();
    chip.className='capacity-chip'+(stale?' stale':'');
    chip.textContent=who==='gemini'?'需允許':stale?'待更新':percentText(agent.remaining_percent);
    chip.title=(clip(agent.label,24)||person(who))+'：'+(agent.basis_label?agent.basis_label+'剩餘 ':'剩餘 ')+percentText(agent.remaining_percent)+' · '+
      labelOf(capacityStates,agent.state,'狀態未知')+(stale?'（資料待更新）':'');
  }
  const strip=$('#detail-content .capacity-strip');const next=capacityBlock();
  if(strip){if(next)strip.replaceWith(next);else strip.remove();return;}
  const sync=$('#detail-sync-note');
  if(next&&sync&&sync.parentElement)sync.parentElement.insertBefore(next,sync);
}
async function loadCapacity(force){
  if(!app.user)return;
  if(capacityLoading||(capacity.absent&&!force))return;
  capacityLoading=true;const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),6000);
  try{
    const r=await fetch('/web/capacity',{cache:'no-store',signal:controller.signal});
    if(r.status===404){capacity.ok=false;capacity.misses++;if(capacity.misses>=3)capacity.absent=true;return;}
    if(!r.ok)throw Error('讀不到用量');
    const d=await r.json();
    if(!Array.isArray(d.agents))throw Error('用量格式不符');
    capacity.agents=d.agents.filter(plainObject).slice(0,8);
    capacity.mode=typeof d.mode==='string'?d.mode:'advisory';
    capacity.at=typeof d.fetched_at==='string'?d.fetched_at:null;
    capacity.fetched=Date.now();capacity.ok=true;capacity.available=true;capacity.misses=0;capacity.absent=false;
  }catch{capacity.ok=false;}
  finally{clearTimeout(timer);capacityLoading=false;paintCapacity();}
}

// -- 詳情自動更新：資料照常前進，已編輯欄位、游標與交付版本各自保留。 --
function taskSignature(t){
  if(!plainObject(t))return '';
  return JSON.stringify([t.status,t.title,t.brief,t.updated_at,t.owner,t.authorized,t.reviewers,t.effective_reviewers,t.assignment,t.messages,t.reviews,t.automation,t.human_waiting,t.summary,t.models]);
}
function detailFields(){return editableFields($('#detail-content'));}
function fieldKey(n){return (n.form?.id||'')+'#'+n.name+(['checkbox','radio'].includes(n.type)?'#'+n.value:'');}
function retainedLabel(n){
  const delivery=n.name.match(/^acceptance_note_(\d+)$/)?.[1];
  const label=delivery?'交付 #'+delivery+' 的驗收意見':n.name==='work_note'?'上一階段給夥伴的附註':n.getAttribute('aria-label')||n.closest('label')?.querySelector('span')?.textContent||'上一階段的補充文字';
  return '任務 #'+app.detailId+' · '+label+'（未送出）';
}
function paintRetainedDrafts(){
  $('#retained-drafts')?.remove();const drafts=app.retainedDrafts;
  if(!drafts?.entries.size||drafts.taskId!==app.detailId)return;
  const section=node('section','work-panel retained-drafts');section.id='retained-drafts';
  section.append(node('h2','','先前階段的文字草稿'),node('p','form-hint','進度已更新，以下文字保留在原本的任務與交付下，沒有送出或套到新版。可選取複製，確認不需要後再清除；清除前會暫緩載入新版介面。關閉這件事會捨棄這些草稿。'));
  for(const [key,draft] of drafts.entries){
    const wrap=node('div','retained-draft');wrap.append(node('p','',draft.label));
    const area=node('textarea');area.readOnly=true;area.rows=3;area.value=draft.value;area.dataset.retainedDraft=key;area.dataset.originalKey=draft.originalKey;area.setAttribute('aria-label',draft.label);
    const clear=node('button','text-button','清除這份草稿');clear.type='button';clear.addEventListener('click',()=>{drafts.entries.delete(key);paintRetainedDrafts();scheduleReloadCheck();});
    wrap.append(area,clear);section.append(wrap);
  }
  const content=$('#detail-content');content.insertBefore(section,content.querySelector('.timeline-heading'));
}
function detailBusyTyping(){return composing||submissionBusy();}
function selectionEndpoint(root,target,offset){
  const element=target.nodeType===1?target:target.parentElement;
  const anchor=element?.closest('[data-message-id],[data-keep],[id]');if(!anchor||!root.contains(anchor))return null;
  const range=document.createRange();range.selectNodeContents(anchor);range.setEnd(target,offset);
  return {message:anchor.dataset.messageId,keep:anchor.dataset.keep,id:anchor.id,offset:range.toString().length};
}
function selectionNode(root,point){
  if(!point)return null;
  const anchor=point.message?[...root.querySelectorAll('[data-message-id]')].find(n=>n.dataset.messageId===point.message):point.keep?[...root.querySelectorAll('[data-keep]')].find(n=>n.dataset.keep===point.keep):document.getElementById(point.id);
  if(!anchor||!root.contains(anchor))return null;
  const walker=document.createTreeWalker(anchor,NodeFilter.SHOW_TEXT);let remaining=point.offset,last=null;
  while(walker.nextNode()){last=walker.currentNode;if(remaining<=last.textContent.length)return [last,remaining];remaining-=last.textContent.length;}
  return last?[last,last.textContent.length]:[anchor,0];
}
function applyDetail(t,fromResponse=false){
  if(t.id!==app.detailId)return;
  if(composing||(submissionBusy()&&!fromResponse)){showPending(t);return;}
  const dialog=$('#task-dialog'),content=$('#detail-content'),scroll=dialog.scrollTop,pageScroll={x:scrollX,y:scrollY};
  const active=document.activeElement,focused=content.contains(active)?{id:active.id,key:active.name?fieldKey(active):null,retained:active.dataset.retainedDraft,start:active.selectionStart,end:active.selectionEnd,direction:active.selectionDirection}:null;
  let selection=null;try{const current=window.getSelection();if(current&&!current.isCollapsed)selection={anchor:selectionEndpoint(content,current.anchorNode,current.anchorOffset),focus:selectionEndpoint(content,current.focusNode,current.focusOffset)};}catch{}
  const values=new Map(detailFields().map(n=>{const value=fieldState(n),baseline=formDefaults.get(n)||value;return [fieldKey(n),{...value,baseline,dirty:!stateEqual(value,baseline),scroll:n.scrollTop,text:n.tagName==='TEXTAREA'||(n.tagName==='INPUT'&&['text','search','url','email','tel'].includes(n.type)),label:retainedLabel(n)}];}));
  app.detailOpen=new Set($$('#detail-content [data-keep]').filter(n=>n.open).map(n=>n.dataset.keep));
  renderDetail(t);
  const restored=new Set();
  for(const n of detailFields()){
    const kept=values.get(fieldKey(n));if(!kept||!kept.dirty||n.disabled||n.readOnly)continue;
    if(['checkbox','radio'].includes(n.type))n.checked=kept.checked;
    else if(n.tagName!=='SELECT'||[...n.options].some(option=>option.value===kept.value))n.value=kept.value;
    restored.add(fieldKey(n));
    formDefaults.set(n,kept.baseline);n.scrollTop=kept.scroll;
    n.dispatchEvent(new Event(n.type==='checkbox'||n.type==='radio'||n.tagName==='SELECT'?'change':'input',{bubbles:true}));
  }
  for(const [key,kept] of values){
    if(!kept.dirty||!kept.text||!kept.value.trim()||restored.has(key))continue;
    const drafts=app.retainedDrafts.entries;if([...drafts.values()].some(d=>d.originalKey===key&&d.value===kept.value))continue;
    let retainedKey=key;while(drafts.has(retainedKey))retainedKey+=':previous';
    drafts.set(retainedKey,{originalKey:key,value:kept.value,label:kept.label});
  }
  paintRetainedDrafts();
  if(focused){
    const retained=[...content.querySelectorAll('[data-retained-draft]')];
    const next=focused.retained?retained.find(n=>n.dataset.retainedDraft===focused.retained):focused.key?detailFields().find(n=>fieldKey(n)===focused.key&&!n.disabled)||retained.find(n=>n.dataset.originalKey===focused.key):focused.id?document.getElementById(focused.id):null;
    if(next&&content.contains(next)&&!next.disabled){next.focus({preventScroll:true});try{if(focused.start!==null&&focused.start!==undefined)next.setSelectionRange(focused.start,focused.end,focused.direction);}catch{}}
  }
  if(selection)try{const anchor=selectionNode(content,selection.anchor),focus=selectionNode(content,selection.focus);if(anchor&&focus)window.getSelection().setBaseAndExtent(...anchor,...focus);}catch{}
  dialog.scrollTop=scroll;window.scrollTo({left:pageScroll.x,top:pageScroll.y,behavior:'instant'});paintDetailSync();scheduleReloadCheck();
}
function showPending(t){
  app.detailPending=t;let bar=$('#detail-pending');
  if(!bar){bar=node('div','detail-pending');bar.id='detail-pending';bar.setAttribute('role','status');$('#detail-content').prepend(bar);}
  bar.replaceChildren(icon('refresh'),node('span','',composing?'已收到新進度，完成目前組字後會自動更新。':'已收到新進度，送出完成後會自動更新。'));paintDetailSync();
}
function paintDetailSync(target){
  const note=target||$('#detail-sync-note');if(!note)return;
  const failing=detailFailures>0;note.classList.toggle('stale',failing);
  note.textContent=failing?'進度暫時無法更新，保留最後資料並自動再試。'+(app.detailSyncAt?' · 上次成功 '+syncTime(new Date(app.detailSyncAt).toISOString()):'')
    :'每 5 秒自動更新'+(app.detailSyncAt?' · 已同步 '+syncTime(new Date(app.detailSyncAt).toISOString()):'');
}
let detailPolling=false,detailFailures=0;
async function pollDetail(){
  const id=app.detailId;
  if(id===null||document.hidden||!$('#task-dialog').open)return;
  if(detailPolling||submissionBusy()){app.detailNeedsRefresh=true;return;}
  detailPolling=true;app.detailNeedsRefresh=false;const epoch=app.detailEpoch||0,request=app.detailRequest;
  try{
    const {response:r,data:t}=await requestJSON('/web/tasks/'+id,{cache:'no-store'});
    if(!r.ok||!plainObject(t)||t.id!==id)throw Error('讀取失敗');
    if(app.detailId!==id||!$('#task-dialog').open||request!==app.detailRequest)return;
    if(epoch!==(app.detailEpoch||0)){app.detailNeedsRefresh=true;return;}
    detailFailures=0;app.detailSyncAt=Date.now();
    if(taskSignature(t)===taskSignature(app.detailTask)){app.detailTask=t;paintDetailSync();return;}
    if(detailBusyTyping())showPending(t);else applyDetail(t);
  }catch{detailFailures++;paintDetailSync();}
  finally{detailPolling=false;if(app.detailNeedsRefresh&&!submissionBusy()){app.detailNeedsRefresh=false;queueMicrotask(pollDetail);}}
}
for(const name of ['input','change'])document.addEventListener(name,scheduleReloadCheck);
document.addEventListener('reset',()=>setTimeout(scheduleReloadCheck,0));
document.addEventListener('compositionstart',()=>{composing=true;});
document.addEventListener('compositionend',()=>{composing=false;queueMicrotask(afterSubmission);});
loadCapacity();
setInterval(pollDetail,5000);
setInterval(()=>{if(!document.hidden)loadCapacity();},60000);
// 回到頁面立即補資料，也重新判斷是否可以載入新版。
document.addEventListener('visibilitychange',()=>{if(!document.hidden){load();pollDetail();loadCapacity();scheduleReloadCheck();}});


function missingInfo(t){
  const a=t.automation||{},jobs=listOf(a.jobs),repair=listOf(a.repairs)[0];
  const blocked=jobs.find(j=>listOf(a.attention_job_ids).includes(j.id)&&!listOf(j.user_actions).length&&['blocked','failed'].includes(j.state)&&!j.superseded);
  if(blocked)return {job:blocked,items:listOf(blocked.blockers).length?blocked.blockers:[blocked.error||'本輪工作失敗，需核對原因']};
  if(repair){const next=jobs.find(j=>j.id===repair.job_id);if(['queued','running'].includes(next?.state))return {job:jobs.find(j=>j.id===repair.origin_job)||next,items:[repair.reason],repair};if(repair.state==='needs_more'&&listOf(repair.missing_items??repair.pending_items).length)return {job:next,items:listOf(repair.missing_items??repair.pending_items),repair};if(repair.state==='reviewed'&&!jobs.some(j=>j.kind==='discuss'&&j.state==='completed'&&!j.superseded&&j.id>repair.job_id))return null;}
  const latest=jobs.find(j=>j.kind==='discuss'&&j.state==='completed'&&!j.superseded);
  if(latest&&listOf(latest.missing_items??latest.pending_items).length)return {job:latest,items:listOf(latest.missing_items??latest.pending_items)};
  const plan=listOf(a.plans)[0];if(plan?.status==='draft'&&listOf(plan.missing_items??plan.pending_items).length)return {job:latest||jobs.find(j=>j.state==='completed'),items:listOf(plan.missing_items??plan.pending_items)};
  return null;
}
function missingPanel(t){
  const info=missingInfo(t);if(!info)return null;
  const panel=node('section','handover-panel missing-panel');panel.id='missing-items';panel.append(node('h2','','夥伴待處理'),node('p','handover-subtitle','負責人：'+person(info.job?.worker||t.assignment?.worker||'codex')));
  for(const item of info.items){const card=node('div','missing-card');card.append(node('strong','',item),node('p','','由負責人取得原件並核對。需要你決定或親自操作時，會另外列操作卡。'));panel.append(card);}
  const busy=listOf(t.automation?.jobs).some(j=>j.state==='running'||j.state==='queued'&&!t.automation?.paused);
  if(info.job?.source_collection?.state==='collected')panel.append(node('p','work-hint','Codex已取得 '+info.job.source_collection.files+' 份來源快照；核對結果與尚缺項目見下方。'));
  if(info.repair)panel.append(node('p','work-hint',({queued:'補件核對已排隊',running:'負責人正在核對補件',needs_more:'本輪尚有待處理項目，由負責人接續核對',reviewed:'補件核對已收到，可整理新的執行方案',failed:'補件核對失敗，可重新提交',cancelled:'這輪補件已取消'})[info.repair.job_state]||({needs_more:'必要資料由負責人接續取得'})[info.repair.state]||'補件處理紀錄已保留'));
  if(workActionsReady(t)){
    const extra=node('details','optional-supplement');extra.append(node('summary','','補充資料（選填）'));panel.append(extra);
    const note=node('textarea');note.name='repair_note_'+t.id;note.maxLength=4000;note.rows=2;note.placeholder='補充答案，或寫明要負責人補哪一件；請勿填密碼';note.setAttribute('aria-label','補件說明');extra.append(note);
    const label=node('label','upload-label');label.append(node('span','','補交文字檔案（選填，每個200KB）'));const upload=node('input');upload.type='file';upload.multiple=true;upload.accept='.txt,.md,.py,.js,.json,.yaml,.yml,.csv,.log,.conf,.ini,.toml,.diff,.patch';upload.setAttribute('aria-label','補件檔案');upload.disabled=busy;label.append(upload);extra.append(label);
    const selected=node('p','work-hint');const drafts=app.supplementFiles||(app.supplementFiles=new Map());const showFiles=()=>{selected.textContent=(drafts.get(t.id)||[]).map(x=>x.name).join('、');};showFiles();extra.append(selected);
    upload.addEventListener('change',async()=>{submit.disabled=true;request.disabled=true;try{const files=[...upload.files];if(files.length>20||files.some(f=>f.size>200000)||files.reduce((n,f)=>n+f.size,0)>1000000)throw Error('補件最多20個檔案、每個200KB、合計1MB');const values=[];for(const f of files)values.push({name:f.name,content:new TextDecoder('utf-8',{fatal:true}).decode(await f.arrayBuffer())});drafts.set(t.id,values);showFiles();}catch(e){toast(e.message||'請選擇UTF-8文字檔');upload.value='';drafts.delete(t.id);showFiles();}finally{submit.disabled=busy;request.disabled=busy;}});
    const row=node('div','work-buttons');const request=node('button','work-button','交給負責人接續');request.type='button';request.disabled=busy;request.addEventListener('click',()=>sendControl(t,'repair',request,{target_id:info.job?.id,body:note.value.trim(),files:[]}));
    const submit=node('button','work-button primary','補上資料，重新核對');submit.type='button';submit.disabled=busy;submit.addEventListener('click',async()=>{const files=drafts.get(t.id)||[];if(!note.value.trim()&&!files.length){toast('請填補件說明或選擇檔案');return;}await sendControl(t,'repair',submit,{target_id:info.job?.id,body:note.value.trim(),files});});row.append(request);extra.append(submit);panel.append(row,node('p','handover-subtitle','由負責人取得技術資料，保留已完成成果；你有額外資料時才需展開補充。'));
  }
  handoverError(panel);return panel;
}
function nextStepPanel(t){
  if(!workActionsReady(t))return null;
  const a=t.automation,panel=node('section','work-panel next-panel');panel.id='next-step';panel.append(node('h2','','下一步'));
  const jobs=currentJobs(a),active=jobs.some(j=>['running','queued'].includes(j.state)&&!a.paused),missing=missingInfo(t),plan=listOf(a.plans)[0];
  if(pendingHuman(t).length)panel.append(node('p','','先完成上方操作卡，再按「我已完成，請核對並接續」。'));
  else if(active){panel.append(node('p','','夥伴正在處理，結果或需要你操作時會由 TG 提醒。'),workButton(t,'pause'));}
  else if(missing&&!(plan?.execution&&a.start_ready&&listOf(plan.execution.commands).length&&listOf(plan.execution.commands).every(c=>c.check===true)))panel.append(node('p','','由負責人處理下方卡點。技術原件不需要你找；你可按「交給負責人接續」要求接續核對。'));
  else if(t.status==='approved')panel.append(node('p','','先查看成果與驗收證據，再於下方逐項驗收。'));
  else if(plan&&a.start_ready){
    if(missing)panel.append(node('p','','尚有待補資料；這份方案只執行列出的唯讀查核，其他缺項保留。'));
    panel.append(planBlock(plan));
    const b=node('button','work-button primary',plan.execution?'照這個方案做':listOf(plan.steps).every(x=>x.kind==='check')?'照方案查核':'照方案產出候選檔案');b.type='button';
    let consent=null;if(plan.execution?.baseline_consent_required){const label=node('label','baseline-consent');consent=node('input');consent.type='checkbox';consent.name='baseline_consent_'+plan.id;label.append(consent,node('span','','我同意本方案修改列出的受保護路徑，並已閱讀操作卡與回復方法'));panel.append(label);b.disabled=true;consent.addEventListener('change',()=>{b.disabled=!consent.checked;});}
    b.addEventListener('click',()=>sendControl(t,'start',b,{plan_id:plan.id,checked:consent?.checked?['baseline']:[]}));panel.append(b);
    if(!plan.execution&&listOf(plan.steps).some(x=>x.kind==='implement')){const update=workButton(t,'plan');update.textContent='整理含正式部署的方案';panel.append(update);}
  }else if(a.paused&&jobs.some(j=>j.state==='queued')){panel.append(node('p','','目前已暫停，排隊工作保留。'),workButton(t,'resume',null,true));}
  else {panel.append(node('p','',a.start_reason||'先把討論整理成能執行、能驗收的方案。'),workButton(t,'plan',null,true));}
  const workflow=jobs.find(j=>j.kind==='discuss'&&j.state==='completed'&&!j.superseded);
  if(listOf(workflow?.workflow_actions).length){if(!listOf(plan?.workflow_actions).length)panel.append(planGroup('接續安排（非缺件）',workflow.workflow_actions.map(x=>x.text)));panel.append(node('p','work-hint','核准、開啟實作輪與時間安排不是缺件，請依上方方案接續；補件不會啟動實作。'));}
  handoverError(panel);return panel;
}
function evidenceCards(t,d){
  const box=node('div','evidence-cards');const rows=listOf(d.execution_receipts);
  const card=(title,state,detail)=>{const n=node('article','evidence-card');n.append(node('strong','',title),node('span','evidence-state',state),node('p','',detail));box.append(n);};
  for(const row of rows)card(row.title,row.passed?'命令已完成':row.state==='started'||row.state==='uncertain'?'結果待核對':'未通過',row.host+' · '+fullTime(row.verified_at||row.at)+' · '+(row.check?'本輪重驗':'實際變更')+' · 退出碼 '+(row.exit_code??'未取得'));
  card('獨立複核',t.status==='approved'?'本輪複核通過':'等待本輪複核',t.status==='approved'?'仍需你確認下列驗收條件。':'由交付者以外的夥伴核對本輪成果與證據。');
  const limits=listOf(d.limitations);card('驗證範圍',limits.length?'有尚未驗證項目':'請核對驗收條件',limits.length?limits.join('；'):'命令成功、語法檢查或本人勾選，均不能單獨代表功能、安全或HMAC驗證通過。');
  return box;
}
