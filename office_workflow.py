"""AI 協作辦公室：office_workflow。"""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from office_plan import normalize_plan, normalize_next_actions
from office_sources import SourcesBlocked, _source_directory, _source_bytes, _source_manifest, _write_source_missing


def sha(data):return hashlib.sha256(data).hexdigest()
def initialize(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS office_supplements(
        revision TEXT PRIMARY KEY, task_id INTEGER NOT NULL, brief_sha TEXT NOT NULL,
        manifest TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS office_repairs(
        id INTEGER PRIMARY KEY,task_id INTEGER NOT NULL,origin_job INTEGER,
        worker TEXT NOT NULL,job_id INTEGER NOT NULL,revision TEXT,state TEXT NOT NULL,
        reason TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);''')


def latest_revision(c,tid,brief):
    row=c.execute('SELECT revision FROM office_supplements WHERE task_id=? AND brief_sha=? ORDER BY rowid DESC LIMIT 1',(tid,sha(brief.strip().encode()))).fetchone()
    return row[0] if row else None


def snapshot(c,tid):
    rows=[]
    for r in c.execute('SELECT * FROM office_repairs WHERE task_id=? ORDER BY id DESC LIMIT 5',(tid,)):
        row=dict(r);j=c.execute('SELECT state,result FROM office_jobs WHERE id=?',(r['job_id'],)).fetchone()
        row['job_state']=j['state'] if j else None
        if j and j['state'] in ('failed','cancelled'):row['state']=j['state']
        result=json.loads(j['result']) if j and j['result'] else {}
        row['pending_items']=result.get('pending_items',[])
        row.update(pending_routes(result))
        if row['state']=='needs_more' and not row['missing_items'] and row['workflow_actions']:
            row['state']='awaiting_next_step'
        rows.append(row)
    return rows


def validate_files(files,*,max_files=20):
    from office_worker_tools import SECRET,forbidden
    if files is None:return []
    if not isinstance(files,list) or len(files)>max_files:raise ValueError('補件檔案數量超過本輪限制')
    clean=[];names=set();size=0
    for row in files:
        if not isinstance(row,dict) or set(row)!={'name','content'}:raise ValueError('補件檔案格式不符')
        name=row['name'];content=row['content']
        if not isinstance(name,str) or not re.fullmatch(r'[^/\\\x00-\x1f]{1,160}',name) or name.startswith('.') or name=='manifest.json' or name in names or forbidden(name):raise ValueError('補件檔名不符或疑似認證檔')
        if not isinstance(content,str) or '\x00' in content or len(content.encode())>200000 or SECRET.search(content) or re.search(r'(?i)(?:Bearer\s+\S+|[\"\'](?:password|token|secret)[\"\']\s*:\s*[\"\'][^\"\']+)',content):raise ValueError('補件僅接受不含憑證的UTF-8文字，每個檔案最多200KB')
        data=content.encode();size+=len(data)
        if size>1_000_000:raise ValueError('本輪補件總量最多1MB')
        names.add(name);clean.append({'name':name,'sha256':sha(data),'content':content})
    return clean


def store(o,c,task,files,*,provider='owner'):
    if provider not in ('owner','codex'):raise ValueError('來源提供者不符')
    clean=validate_files(files,max_files=30 if provider=='codex' else 20)
    previous=latest_revision(c,task['id'],task['brief'])
    if not clean:return previous
    contents={}
    if previous:
        old,contents=load(o.DATA_DIR,task,previous)
    for row in clean:contents[row['name']]=row['content'].encode()
    if len(contents)>30 or sum(len(x) for x in contents.values())>2_000_000:raise ValueError('累積補件超過30件或2MB，請縮小來源')
    revision=uuid.uuid4().hex;target=Path(o.DATA_DIR)/'supplements'/str(task['id'])/revision
    fd=_source_directory(target,create=True)
    try:
        entries=[]
        for name,data in contents.items():
            _write_source_missing(fd,name,data);entries.append({'name':name,'sha256':sha(data),'required':True,'source':('Codex唯讀採集：' if provider=='codex' else '負責人補交：')+name,'captured_at':o.now()})
        manifest={'task_id':task['id'],'brief_sha256':sha(task['brief'].strip().encode()),'files':entries,'revision':revision,'provider':provider}
        raw=json.dumps(manifest,ensure_ascii=False).encode();_write_source_missing(fd,'manifest.json',raw)
    finally:os.close(fd)
    c.execute('INSERT INTO office_supplements VALUES(?,?,?,?,?)',(revision,task['id'],manifest['brief_sha256'],raw.decode(),o.now()))
    return revision


def load(data_dir,task,revision):
    if not isinstance(revision,str) or not re.fullmatch('[a-f0-9]{32}',revision):raise SourcesBlocked('補件版本不符')
    root=Path(data_dir)/'supplements'/str(task['id'])/revision;fd=_source_directory(root)
    try:
        raw=_source_bytes(fd,'manifest.json',100000);m=_source_manifest(raw,task)
        if m.get('revision')!=revision or m.get('provider') not in ('owner','codex'):raise SourcesBlocked('補件來源身分不符')
        contents={}
        for entry in m['files']:
            data=_source_bytes(fd,entry['name'],200000)
            if sha(data)!=entry['sha256']:raise SourcesBlocked('補件內容在交件後變更')
            data.decode('utf-8');contents[entry['name']]=data
        return m,contents
    finally:os.close(fd)


class Sources(list):
    def __init__(self,values,missing):super().__init__(values);self.missing=missing


def prepare_sources(data_dir,task,folder,parent_manifest=None,*,supplement_revision=None,partial=False,prepare,expected_revision=None):
    if not supplement_revision or (parent_manifest or {}).get('context',{}).get('sources'):
        return prepare(data_dir,task,folder,parent_manifest,expected_revision=expected_revision)
    try:
        m,contents=load(data_dir,task,supplement_revision)
        entries={row['name']:dict(row) for row in m['files']}
        package=Path(data_dir)/'sources'/str(task['id']);missing=[]
        if not package.exists():package=Path(data_dir)/'source-library'/str(task['id'])
        if package.exists():
            fd=_source_directory(package)
            try:
                original=_source_manifest(_source_bytes(fd,'manifest.json',100000),task)
                for row in original['files']:
                    if row['name'] in entries:continue
                    try:
                        data=_source_bytes(fd,row['name'])
                        if sha(data)!=row['sha256']:raise ValueError('來源指紋不符')
                    except (FileNotFoundError,ValueError):
                        if row.get('required',True):missing.append(row['name'])
                        continue
                    data.decode('utf-8');entries[row['name']]=row;contents[row['name']]=data
            finally:os.close(fd)
        if missing and not partial:raise SourcesBlocked('仍缺必要原件：'+'；'.join(missing))
        target=Path(folder)/'source-evidence';fd=_source_directory(target,create=True)
        try:
            if os.listdir(fd):raise SourcesBlocked('本輪來源快照已存在，停止重複準備')
            result=[]
            for name,row in entries.items():
                data=contents[name];_write_source_missing(fd,name,data)
                result.append({'path':str(target/name),'sha256':sha(data),'total_lines':len(data.decode().splitlines()),'required':row.get('required',True),'source':row.get('source',name),'captured_at':row.get('captured_at')})
        finally:os.close(fd)
        return Sources(result,missing)
    except SourcesBlocked:raise
    except (OSError,ValueError,KeyError,TypeError):raise SourcesBlocked('補件快照無法驗證，保留原卡點') from None


def repair(a,c,t,body,target_id,files,key):
    o=a.o;tid=t['id']
    running=c.execute("SELECT 1 FROM office_jobs WHERE task_id=? AND state='running'",(tid,)).fetchone()
    queued=c.execute("SELECT 1 FROM office_jobs j LEFT JOIN office_controls x ON x.task_id=j.task_id WHERE j.task_id=? AND j.state='queued' AND coalesce(x.paused,0)=0",(tid,)).fetchone()
    if running or (queued and not files and not body.strip()):raise o.OfficeError(409,'請等目前這一步完成，再重新補件')
    original=c.execute('SELECT * FROM office_jobs WHERE id=? AND task_id=?',(target_id,tid)).fetchone() if target_id else None
    if target_id and not original:raise o.OfficeError(409,'原缺件工作不存在')
    if original and original['state'] not in ('blocked','failed','completed'):raise o.OfficeError(409,'這一步尚未交出缺件結果')
    result=json.loads(original['result']) if original and original['result'] else {}
    routed=pending_routes(result)
    deficits=result.get('blockers',[]) or routed['missing_items']
    if not deficits and routed['workflow_actions'] and not files:
        raise o.OfficeError(409,'這些是核准或實作安排，不是缺件；請查看「下一步」的方案，沒有方案時按「整理動工計畫」。補件不會開啟實作工具。')
    if not deficits and not body.strip() and not files:raise o.OfficeError(400,'請寫明需要補哪一項資料')
    if result.get('user_actions'):raise o.OfficeError(409,'這一步需要本人操作，請用操作卡回報，不以補件跳過')
    try:revision=store(o,c,t,files)
    except ValueError as e:raise o.OfficeError(400,str(e)) from None
    worker=original['worker'] if original else None
    from office_people import allowed_worker
    if worker and not allowed_worker(worker,t,'discuss',o.effective_reviewers(t)):worker=None
    mid=o.add_msg(c,tid,o.BOSS,'control','請負責夥伴補件並核對：'+('；'.join(deficits) or body)+('\n'+body if body and deficits else '')+'\n只核對缺件與現況，不重跑舊修改；完成的成果保留。')
    prior_plan=c.execute('SELECT id FROM office_plans WHERE task_id=? ORDER BY id DESC LIMIT 1',(tid,)).fetchone()
    a.enter_discussion(c,tid,mid)
    instruction='請核對以下缺件，能在本輪核准來源與工具範圍自行取得的就補齊；不得擴大機器、檔案或操作權限。仍缺的逐項寫pending_items，列原因、誰能補、要補哪個檔或回答；完成時交意見，不把補件核對當正式施工。\n'+('；'.join(deficits) or body)+('\n負責人補充：'+body if body else '')
    jid=a.enqueue(c,tid,'discuss',key+':repair',instruction,worker=worker,trigger=mid)
    payload=json.loads(c.execute('SELECT payload FROM office_jobs WHERE id=?',(jid,)).fetchone()[0]);payload.update(supplement_revision=revision,repair_origin=target_id)
    if prior_plan:payload.update(require_plan=True,repair_plan_id=prior_plan['id'])
    c.execute('UPDATE office_jobs SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),jid))
    worker=c.execute('SELECT worker FROM office_jobs WHERE id=?',(jid,)).fetchone()[0]
    c.execute('INSERT INTO office_repairs(task_id,origin_job,worker,job_id,revision,state,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(tid,target_id,worker,jid,revision,'queued','；'.join(deficits) or body,o.now(),o.now()))


def finished(c,j,result,now):
    routes=pending_routes(result)
    pending=routes['missing_items'] or result.get('blockers') or []
    c.execute('UPDATE office_repairs SET state=?,updated_at=? WHERE job_id=?',('needs_more' if pending else 'awaiting_next_step' if routes['workflow_actions'] else 'reviewed',now,j['id']))


def plan_allowed(payload):
    """單人與整合輪可交方案；多人輪個別意見不可越過整合。"""
    return not payload.get('discussion_round') or bool(payload.get('single_discussion_round') or payload.get('integration_round') or payload.get('require_plan'))


def pending_routes(result):
    """只作流程顯示分流，不提供核准或執行授權；原文永遠保留。

    僅辨識單一且明確的流程句。夾帶缺檔、混合句或不明文字仍列資料缺口。
    """
    missing=[];actions=normalize_next_actions(result.get('next_actions'))
    for item in result.get('pending_items',[]):
        text=item.strip()
        kind=None
        if len(text)<=200 and not re.search(r'[\n]|(?:缺|補|不足|未提供|未取得|尚未取得|讀取失敗|來源|憑證|密碼|簽署)',text):
            if re.fullmatch(r'(?:等待|待|請)?負責人(?:批准|核准|確認)(?:本|這份|此)?(?:方案|計畫)(?:與執行人安排|及執行人安排)?(?:[（(][^）)]*[）)])?(?:[；，](?:想跑到盤中實測，)?(?:要|需)在[0-9/: ]+前(?:批准|核准))?',text):
                kind='approval'
            elif re.fullmatch(r'(?:批准|核准)後(?:由Codex或負責人)?(?:開一個|開放|開啟)(?:開放寫檔的|寫檔的)?實作輪給(?:Claude|Codex|助理|Grok)(?:，用來[^；。]+)?',text):
                kind='implementation'
            elif re.fullmatch(r'.{0,12}(?:盤中實測時間點|要在\d{2}-\d{2}盤中由批准後的固定步驟執行).*',text):
                kind='schedule'
        if kind:actions.append({'kind':kind,'text':item})
        else:missing.append(item)
    return {'missing_items':missing,'workflow_actions':actions}
