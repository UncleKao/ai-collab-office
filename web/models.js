'use strict';
function effortLabel(value){return ({none:'不啟用（none）',minimal:'最低（minimal）',low:'低（low）',medium:'中（medium）',high:'高（high）',xhigh:'特高（xhigh）',max:'最高（max）',ultra:'極致（ultra）'})[value]||value;}
function effortChoices(row,model){const item=listOf(row.options).find(x=>x.id===model);return item?listOf(item.supported_efforts).filter(x=>typeof x==='string'):[];}
function modelChoice(row){return typeof row.selected==='string'?row.selected:null;}
function modelLabel(row,id){
  const hit=listOf(row.options).find(item=>plainObject(item)&&item.id===id);
  return hit&&typeof hit.label==='string'&&hit.label?hit.label:(id||'');
}
function modelValue(t){
  const snap=plainObject(t.models)||{};
  const models={},efforts={},rows={};
  for(const worker of ['codex','claude','grok','assistant']){
    const found=listOf(snap.workers).find(item=>plainObject(item)&&item.worker===worker);
    const row=found||{worker,selected:null,default_model:'',options:[]};
    rows[worker]={worker,selected:modelChoice(row),default_model:typeof row.default_model==='string'?row.default_model:'',verified_at:row.verified_at,host:row.host,source:row.source,stale:row.stale,refresh_error:row.refresh_error,options:listOf(row.options).filter(item=>plainObject(item)&&typeof item.id==='string')};
    models[worker]=rows[worker].selected;
    efforts[worker]=typeof row.selected_effort==='string'?row.selected_effort:null;
  }
  return {taskId:t.id,version:Number.isSafeInteger(snap.version)?snap.version:0,models,efforts,rows,verified_at:typeof snap.verified_at==='string'?snap.verified_at:null,dirty:false};
}
function modelSame(a,b){return ['codex','claude','grok','assistant'].every(w=>a[w]===b[w]);}
function modelPanel(t){
  const current=modelValue(t);
  const readonly=app.user!=='owner'||!t.authorized||['closed','dropped','proposal'].includes(t.status);
  if(!app.modelDraft||app.modelDraft.taskId!==t.id||!app.modelDraft.dirty)app.modelDraft=modelValue(t);
  const draft=app.modelDraft;
  const conflict=draft.version!==current.version;
  const box=keepable(node('details','reading-controls'),'models',false);
  box.setAttribute('aria-label','這張單的模型選擇');
  box.append(node('summary','','這張單的模型選擇'));
  const panel=node('section','work-panel models-panel');
  const head=node('div','work-head');
  head.append(node('h2','','這張單的模型選擇'));
  if(current.version>0)head.append(node('span','work-state idle','已儲存'));
  panel.append(head);
  panel.append(node('p','work-hint','模型與思考強度可分別選擇；跟隨預設會使用 CLI 的設定。儲存只影響這張單的新工作與總結，已排隊或執行中的工作保留原設定。'));
  if(current.verified_at)panel.append(node('p','work-hint','模型設定最近讀取於 '+fullTime(current.verified_at)+'。'));
  if(app.user==='owner'){
    const refresh=node('button','work-button','立即更新模型清單');refresh.type='button';refresh.disabled=Boolean(t.models&&t.models.refreshing);
    if(refresh.disabled)refresh.textContent='正在更新模型清單…';
    refresh.addEventListener('click',async()=>{
      refresh.disabled=true;refresh.textContent='正在更新模型清單…';
      try{await postWeb('/web/models/refresh',{csrf:app.csrf});toast('已開始更新，完成後會自動顯示新清單。');}
      catch(error){toast(error.message||'更新未完成');refresh.disabled=false;refresh.textContent='立即更新模型清單';}
    });panel.append(refresh);
  }
  const fields=node('div','models-fields');
  const selects={},effortSelects={},effortHints={};
  for(const worker of ['codex','claude','grok','assistant']){
    const row=current.rows[worker];
    const wrap=node('div','form-field');
    wrap.append(node('span','',person(worker)));
    const select=node('select');
    select.name='model_'+worker;
    select.setAttribute('aria-label',person(worker)+' 的模型');
    const fallback=node('option','','跟隨夥伴目前設定（'+(modelLabel(row,row.default_model)||row.default_model||'目錄預設')+'）');
    fallback.value='';
    select.append(fallback);
    const seen=new Set();
    for(const item of row.options){
      if(!item.id||seen.has(item.id))continue;
      seen.add(item.id);
      const opt=node('option','',typeof item.label==='string'&&item.label?item.label:item.id);
      opt.value=item.id;
      select.append(opt);
    }
    const chosen=draft.models[worker];
    if(chosen&&!seen.has(chosen)){
      const extra=node('option','',chosen);
      extra.value=chosen;
      select.append(extra);
    }
    select.value=chosen||'';
    select.disabled=readonly;
    wrap.append(select);
    const effortWrap=node('label','form-field');effortWrap.append(node('span','','思考強度'));
    const effortSelect=node('select');effortSelect.name='effort_'+worker;effortSelect.setAttribute('aria-label',person(worker)+' 的思考強度');
    effortWrap.append(effortSelect);wrap.append(effortWrap);effortSelects[worker]=effortSelect;
    const effortHint=node('small','');wrap.append(effortHint);effortHints[worker]=effortHint;
    if(row.verified_at)wrap.append(node('small','',(row.host?row.host+' · ':'')+'設定讀取於 '+fullTime(row.verified_at)+(row.stale?' · 更新未完成，保留上次清單':'')));
    fields.append(wrap);
    selects[worker]=select;
  }
  function populateEffort(worker,modelChanged=false){
    const selected=effortSelects[worker],row=current.rows[worker];
    const choices=effortChoices(row,selects[worker].value||row.default_model);
    if(modelChanged&&draft.efforts[worker]&&!choices.includes(draft.efforts[worker])){
      draft.efforts[worker]=null;toast('新模型不支援原思考強度，已改為跟隨預設；儲存後生效。');
    }
    selected.replaceChildren();const fallback=node('option','','跟隨預設');fallback.value='';selected.append(fallback);
    for(const value of choices){const option=node('option','',effortLabel(value));option.value=value;selected.append(option);}
    const chosen=draft.efforts[worker];
    if(chosen&&!choices.includes(chosen)){const option=node('option','',effortLabel(chosen)+'（已儲存，尚需確認模型支援）');option.value=chosen;selected.append(option);}
    selected.value=chosen||'';selected.disabled=readonly||(!choices.length&&!chosen);
    effortHints[worker].textContent=!choices.length?'此模型未提供可調整的思考強度。':(chosen==='ultra'?'極致強度可能啟用模型的自動分工，仍受本單工具限制。':'強度越高，通常思考越久、使用更多額度。');
  }
  for(const worker of ['codex','claude','grok','assistant'])populateEffort(worker);
  panel.append(fields);
  const error=node('p','form-error');
  error.setAttribute('role','alert');
  error.hidden=true;
  panel.append(error);
  if(readonly){
    if(app.user!=='owner')panel.append(node('p','work-hint','只有負責人能改這張單的模型選擇。'));
    else if(!t.authorized||t.status==='proposal')panel.append(node('p','work-hint','請先收件後再指定模型。'));
    else panel.append(node('p','work-hint','這張單已封存，不能改模型。'));
    box.append(panel);
    return box;
  }
  if(conflict){
    const warning=node('div','assignment-conflict');
    warning.append(node('p','','模型選擇已有更新。你的草稿仍保留，請載入最新選擇後再調整。'));
    const reload=node('button','work-button','放棄草稿，載入最新選擇');
    reload.type='button';
    reload.addEventListener('click',()=>{for(const select of [...Object.values(selects),...Object.values(effortSelects)])formDefaults.set(select,fieldState(select));app.modelDraft=null;applyDetail(app.detailTask);});
    warning.append(reload);
    panel.append(warning);
  }
  const row=node('div','work-buttons');
  const save=node('button','work-button primary','儲存模型選擇');
  save.type='button';
  function syncDraft(){
    for(const worker of ['codex','claude','grok','assistant']){draft.models[worker]=selects[worker].value||null;draft.efforts[worker]=effortSelects[worker].value||null;}
    draft.dirty=!modelSame(draft.models,current.models)||!modelSame(draft.efforts,current.efforts);
    save.disabled=conflict||!draft.dirty;
  }
  for(const worker of ['codex','claude','grok','assistant']){selects[worker].addEventListener('change',()=>{populateEffort(worker,true);syncDraft();});effortSelects[worker].addEventListener('change',()=>{draft.efforts[worker]=effortSelects[worker].value||null;populateEffort(worker);syncDraft();});}
  syncDraft();
  save.addEventListener('click',()=>{
    syncDraft();
    if(save.disabled)return;
    sendControl(t,'models',save,{model_settings:{version:draft.version,models:{codex:draft.models.codex,claude:draft.models.claude,grok:draft.models.grok,assistant:draft.models.assistant},efforts:{codex:draft.efforts.codex,claude:draft.efforts.claude,grok:draft.efforts.grok,assistant:draft.efforts.assistant}}});
  });
  row.append(save);
  panel.append(row);
  box.append(panel);
  return box;
}
