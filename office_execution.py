"""AI 協作辦公室：office_execution。"""
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import sqlite3
import subprocess
import time
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo

from office_config import CONFIG
HOSTS = set(CONFIG['execution_hosts'])
PROGRAMS = {'git','rsync','cp','install','mkdir','chmod','systemctl','journalctl','python3','node','npm','pytest','curl','stat','sha256sum','test','pvesh','qm','pct','cat','head','tail','ls'}
PROTECTED = tuple(CONFIG['protected_paths'])
SECRET = re.compile(r'(?i)\b(?:Bearer\s+\S+|sk-[a-z0-9_-]{20,}|ghp_[a-z0-9]{20,}|\d{5,}:[a-z0-9_-]{25,})|-----BEGIN.*PRIVATE KEY|(?:password|token|secret)\s*=\s*[^\s]+')
PRIVATE_NAMES = {'.secrets','.ssh','.claude','.codex','.grok','.env','auth.json','capability.json','execution-capability.json'}


def stamp():return datetime.now(ZoneInfo(__import__('office_config').CONFIG['timezone'])).isoformat()
def digest(data):return hashlib.sha256(data).hexdigest()

def atomic(path,data):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temp=path.with_name('.'+path.name+'.'+secrets.token_hex(5));temp.write_text(json.dumps(data,ensure_ascii=False));temp.chmod(0o600);os.replace(temp,path)

def safe_path(value):
    if not isinstance(value,str) or len(value)>500 or '\x00' in value or any(ord(x)<32 for x in value):raise ValueError('執行範圍路徑不符')
    path=Path(value)
    if not path.is_absolute() and not value.startswith('${workspace}'):raise ValueError('執行範圍需用絕對路徑或工作區')
    if '..' in path.parts or any(x.lower() in PRIVATE_NAMES or x.lower().endswith(('.key','.pem','.api','.k','.env')) for x in path.parts):raise ValueError('執行範圍不得包含認證或工作階段檔案')
    if value in ('/etc/shadow','/etc/gshadow') or any(value==x or value.startswith(x+'/') for x in ('/proc','/sys','/dev','/run')):raise ValueError('不開放認證或程序內部資料')
    if value.startswith('/etc/pve/priv'):raise ValueError('不開放PVE私有資料')
    return value

def inside(value,roots):
    p=Path(value)
    return any(p==Path(root) or Path(root) in p.parents for root in roots)

def argv_program(argv):
    values=list(argv)
    if values[:2]==['sudo','-n']:values=values[2:]
    if not values:return '',[]
    return Path(values[0]).name,values[1:]

def validate_command(row,scope):
    if not isinstance(row,dict) or set(row)-{'id','title','host','argv','check','after_human','timeout','script_sha256'}:raise ValueError('執行步驟欄位不符')
    key=row.get('id');host=row.get('host');args=row.get('argv')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',key) or not isinstance(row.get('title'),str) or not 1<=len(row['title'])<=500:raise ValueError('步驟識別與標題不符')
    if host not in HOSTS or host not in scope:raise ValueError('步驟機器未列入計畫範圍')
    if not isinstance(args,list) or not 1<=len(args)<=60 or any(not isinstance(v,str) or not v or len(v)>1000 or any(ord(c)<32 for c in v) or SECRET.search(v) for v in args):raise ValueError('指令需為不含憑證的固定參數清單')
    if type(row.get('check')) is not bool or type(row.get('after_human',False)) is not bool:raise ValueError('查核與人工操作標記不符')
    program,rest=argv_program(args)
    if args[0] not in ('sudo',program,'/usr/bin/'+program,'/bin/'+program):raise ValueError('執行程式不得使用工作區偽裝名稱')
    if args[0]=='sudo' and (args[:2]!=['sudo','-n'] or args[2] not in (program,'/usr/bin/'+program,'/bin/'+program)):raise ValueError('sudo只接受固定程式與非互動模式')
    if program not in PROGRAMS:raise ValueError('不支援這個執行程式；請改用已支援步驟或本人操作')
    if any(v in ('--delete','--delete-excluded','--force','--hard','-e','--rsync-path','--config') or v.startswith(('--delete','--force','--rsync-path=')) for v in rest):raise ValueError('不自動執行刪除、強制覆寫或自訂傳輸程式')
    if program in ('python3','node'):
        if any(v in ('-c','-e','--eval','--print') for v in rest):raise ValueError('不接受行內程式碼')
        if program=='python3' and rest[:2] in (['-m','pytest'],['-m','py_compile']):pass
        elif not rest or not (rest[0].startswith('/') and re.fullmatch(r'[0-9a-f]{64}',row.get('script_sha256','')) or rest[0].startswith('${workspace}/') and re.fullmatch(r'[0-9a-f]{64}',row.get('script_sha256',''))):raise ValueError('執行腳本需固定絕對路徑與已核對SHA')
    if row.get('script_sha256') and host!='local':raise ValueError('遠端腳本暫不開放，請使用已支援的固定程式或操作卡')
    if program=='npm' and (not rest or rest[0] not in ('test','run')):raise ValueError('npm只接受已核准的測試或run步驟')
    if program=='git' and (any(v in ('-c','config','clean','reset','rebase','submodule','remote','checkout','switch') for v in rest)):raise ValueError('不開放更改Git認證、來源或破壞性重設')
    if program=='systemctl' and not any(v in ('show','is-active','status','restart','reload','try-restart') for v in rest):raise ValueError('服務步驟只接受查核、重啟或重載')
    if program=='pvesh' and (not rest or rest[0]!='get'):raise ValueError('PVE本輪僅開放明確唯讀get')
    if program in ('qm','pct') and (not rest or rest[0]!='status'):raise ValueError('VM／容器控制需另行具體核准，不在本執行工具內')
    if program=='curl' and (any(v in ('-d','--data','--data-binary','-F','--form','-X','--request','-H','--header','-u','--user','-K','--config','-o','--output') or v.startswith(('--data','--request=','--header=','--user=','--config=','--output=','-o','-K','-X','-H','-u')) for v in rest)):raise ValueError('curl只接受不含認證的唯讀URL查核')
    if row['check'] and program in ('cp','install','mkdir','chmod','rsync'):raise ValueError('寫入指令不能標記成唯讀驗收')
    if row['check'] and program=='systemctl' and any(v in ('restart','reload','try-restart') for v in rest):raise ValueError('重啟不能標記成唯讀查核')
    if row['check'] and program=='git' and any(v in ('add','commit','push','pull','fetch','merge','apply') for v in rest):raise ValueError('Git變更不能標記成唯讀查核')
    # 參數中的絕對路徑、工作區與rsync遠端目的地都須落在核准範圍。
    for original in rest:
        value=original.split('=',1)[1] if original.startswith('-') and '=' in original else original
        if any(x.lower() in PRIVATE_NAMES for x in Path(value).parts):raise ValueError('參數包含認證或工作階段目錄')
        if value.startswith(('/', '${workspace}')):
            safe_path(value)
            if not inside(value,scope[host]):raise ValueError('步驟路徑超出核准範圍')
        if re.match(r'[^/:]+:/',value):
            target,path=value.split(':',1)
            if target not in scope or target not in HOSTS or not inside(safe_path(path),scope[target]):raise ValueError('傳輸目的地未列入計畫範圍')
        if '..' in Path(value).parts:raise ValueError('參數不得跨出工作區')
    timeout=row.get('timeout',120)
    if type(timeout) is not int or not 1<=timeout<=300:raise ValueError('每步時限需在1至300秒')
    return {'id':key,'title':row['title'],'host':host,'argv':args,'check':row['check'],'after_human':row.get('after_human',False),'timeout':timeout,**({'script_sha256':row['script_sha256']} if row.get('script_sha256') else {})}

def normalize(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)-{'scope','commands','rollback','manual_actions','baseline_consent_required'}:raise ValueError('正式執行計畫格式不符')
    scope=value.get('scope');commands=value.get('commands');rollback=value.get('rollback');manual=value.get('manual_actions',[])
    if not isinstance(scope,dict) or not scope or len(scope)>5 or any(host not in HOSTS for host in scope):raise ValueError('執行機器需列入已知設定的入口')
    clean_scope={}
    for host,paths in scope.items():
        if not isinstance(paths,list) or not 1<=len(paths)<=20:raise ValueError('需列明每台機器的路徑範圍')
        clean_scope[host]=[safe_path(x) for x in paths]
        if any(x in ('/','/home','/etc','/usr','/var','${workspace}/..') for x in paths):raise ValueError('請把執行範圍縮到具體專案或檔案')
    if not isinstance(commands,list) or not 1<=len(commands)<=20:raise ValueError('需有1至20個固定執行步驟')
    clean=[validate_command(row,clean_scope) for row in commands]
    phases=[r['after_human'] for r in clean]
    if any(phases[i] and not phases[i+1] for i in range(len(phases)-1)):raise ValueError('人工接續步驟需放在計畫最後')
    if len({r['id'] for r in clean})!=len(clean):raise ValueError('執行步驟ID重複')
    if not any(r['check'] for r in clean):raise ValueError('正式執行需有獨立可重驗的查核步驟')
    if not isinstance(rollback,list) or not 1<=len(rollback)<=10 or any(not isinstance(v,str) or not 1<=len(v)<=2000 for v in rollback):raise ValueError('正式執行需列明回復方法')
    from office_delivery import user_actions
    manual=user_actions({'outcome':'blocked','user_actions':manual})
    baseline=any(any(inside(p,[root]) or inside(root,[p]) for root in PROTECTED for p in paths) for paths in clean_scope.values())
    if len(manual)>8:raise ValueError('人工操作最多八項，請縮小本輪範圍')
    if manual and not any(r['check'] and r['after_human'] for r in clean):raise ValueError('人工操作後需安排可重驗步驟，不能只靠勾選')
    if any(r['after_human'] for r in clean) and not manual:raise ValueError('人工操作後步驟需有對應操作卡')
    return {'scope':clean_scope,'commands':clean,'rollback':rollback,'manual_actions':manual,'baseline_consent_required':baseline}

def provision(folder,url):
    token=secrets.token_urlsafe(32)
    atomic(Path(folder)/'execution-capability.json',{'token':token,'url':url})
    return {'sha256':digest(token.encode())}

def client(handler,step_id):
    cap=json.loads((handler.jobdir/'execution-capability.json').read_text())
    payload={'token':cap['token'],'job_id':handler.job['id'],'step_id':step_id}
    if handler.job.get('remote_execution') and handler.job['kind']=='implement':
        from office_remote import files
        payload['workspace']=files(handler.workspace)
    request=urllib.request.Request(cap['url'],data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=330) as response:reply=json.load(response)
    except urllib.error.HTTPError as error:
        try:body=json.load(error);message=body.get('error','') if isinstance(body,dict) else ''
        except Exception:message=''
        if not isinstance(message,str) or len(message)>1000 or SECRET.search(message):message=''
        raise RuntimeError(message or '核准步驟未執行；先核對計畫與本輪結果') from None
    except Exception:raise RuntimeError('核准步驟回應未取得；先核對既有結果，不可盲目重跑') from None
    if not isinstance(reply,dict) or type(reply.get('passed')) is not bool:raise RuntimeError('核准步驟回應結構不符；停止依賴此結果')
    atomic(handler.jobdir/'execution-evidence'/(step_id+'.json'),reply)
    return reply

def _load(o,jid,token):
    if type(jid) is not int or not isinstance(token,str) or len(token)>200:raise ValueError('步驟身分格式不符')
    folder=Path(o.DATA_DIR)/'jobs'/str(jid);manifest=json.loads((folder/'manifest.json').read_text())
    expected=manifest.get('execution_capability',{}).get('sha256','')
    if not secrets.compare_digest(expected,digest(token.encode())):raise ValueError('步驟身分不符')
    with o.tx() as c:
        job=c.execute('SELECT * FROM office_jobs WHERE id=?',(jid,)).fetchone()
        plan=c.execute('SELECT * FROM office_plans WHERE id=?',(job['plan_id'],)).fetchone() if job else None
        controls=c.execute('SELECT * FROM office_controls WHERE task_id=?',(job['task_id'],)).fetchone() if job else None
        task=c.execute('SELECT * FROM tasks WHERE id=?',(job['task_id'],)).fetchone() if job else None
        if not job or job['state']!='running' or not plan or plan['status']!='approved' or not o.authorized_by(task)[0] or task['status'] in ('closed','dropped'):raise ValueError('本輪或計畫已失效，未執行步驟')
        if job['worker']!=manifest['worker'] or job['kind'] not in ('implement','review','check'):raise ValueError('本輪角色未開放執行')
        stored=json.loads(plan['payload']);execution=stored.get('execution')
        if not execution or digest(plan['payload'].encode())!=plan['plan_sha']:raise ValueError('核准計畫指紋不符')
        if json.loads(job['payload']).get('assignment_version',0)!=__import__('office_assignment').snapshot(c,task)['version']:raise ValueError('分工版本已變更')
        if not __import__('office_people').allowed_worker(job['worker'],task,job['kind'],o.effective_reviewers(task)):raise ValueError('本輪角色已失效')
        confirmation=human_confirmed(c,job)
        return folder,manifest,dict(job),dict(plan),dict(controls) if controls else {},execution,bool(confirmation)

def execute(o,jid,step_id,token,workspace=None,runner=None):
    folder,m,job,plan,controls,e,confirmed=_load(o,jid,token)
    step=next((r for r in e['commands'] if r['id']==step_id),None)
    if not step:raise ValueError('此步驟不在核准計畫')
    if not step['check'] and job['kind']!='implement':raise ValueError('討論／查核／複核不能執行修改步驟')
    if step['after_human'] and not confirmed:raise ValueError('請先完成人工操作並回報，由夥伴接續核對')
    if not step['check'] and (controls.get('paused') or controls.get('discussion_message',0)>(job['trigger_message'] or 0)):raise ValueError('負責人已暫停或更新討論，剩餘修改停止；先核對現況')
    if workspace is not None:
        if job['worker']!='assistant' or job['kind']!='implement':raise ValueError('工作區同步只供助理本輪實作')
        from office_remote import unpack
        unpack(workspace,Path(m['workspace']))
    root=Path(o.DATA_DIR)/'execution-ledger'/plan['plan_sha'];root.mkdir(mode=0o700,parents=True,exist_ok=True)
    receipt_file=(folder/'execution-evidence'/ (step_id+'.json')) if step['check'] else root/(step_id+'.json')
    lock=root/(step_id+'.lock')
    with lock.open('a') as guard:
        os.chmod(lock,0o600);fcntl.flock(guard,fcntl.LOCK_EX)
        if not step['check'] and receipt_file.exists():
            prior=json.loads(receipt_file.read_text());prior['already_recorded']=True
            atomic(folder/'execution-evidence'/(step_id+'.json'),prior)
            return prior
        # 依序執行，人工接續與獨立複核只重做查核；已完成修改不重跑。
        if job['kind']=='implement':
            for earlier in e['commands'][:e['commands'].index(step)]:
                if earlier['after_human'] and not confirmed:continue
                p=(folder/'execution-evidence'/(earlier['id']+'.json')) if earlier['check'] else root/(earlier['id']+'.json')
                if not p.exists() or not json.loads(p.read_text()).get('passed'):raise ValueError('先核對前一個步驟結果，未跳過失敗步驟')
        args=[v.replace('${workspace}',m['workspace']) for v in step['argv']]
        scope={host:[p.replace('${workspace}',m['workspace']) for p in paths] for host,paths in e['scope'].items()}
        # 計畫已在normalize驗過；在執行時再驗固定範圍及腳本SHA。
        expanded={**step,'argv':args}
        if step.get('script_sha256')=='workspace':
            if step['host']!='local' or not inside(argv_program(args)[1][0],[m['workspace']]):raise ValueError('候選腳本限本輪工作區')
            expanded['script_sha256']=digest(Path(argv_program(args)[1][0]).read_bytes())
        validate_command(expanded,scope)
        program,rest=argv_program(args)
        if step.get('script_sha256'):
            if step['host']!='local':raise ValueError('遠端腳本需先登記可核對的部署方法，不以檔名當驗證')
            if digest(Path(rest[0]).read_bytes())!=expanded['script_sha256']:raise ValueError('腳本在批准後已變更，請先更新計畫')
        started=time.time();base={'passed':False,'state':'started','step_id':step_id,'title':step['title'],'host':step['host'],'check':step['check'],'job_id':jid,'plan_id':plan['id'],'plan_sha256':plan['plan_sha'],'at':stamp(),'started':started}
        atomic(receipt_file,base)
        raw=Path(o.DATA_DIR)/'execution-private'/str(jid);raw.mkdir(mode=0o700,parents=True,exist_ok=True)
        command=args if step['host']=='local' else ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',step['host'],shlex.join(args)]
        if runner:
            code,state=runner(command,Path(m['workspace']),step['timeout'])
        else:
            state='finished';code=None
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','LOGNAME','LANG','LC_ALL','SSH_AUTH_SOCK','XDG_RUNTIME_DIR')};env['TZ']=CONFIG['timezone']
            with (raw/(step_id+'.stdout')).open('wb') as out,(raw/(step_id+'.stderr')).open('wb') as err:
                os.fchmod(out.fileno(),0o600);os.fchmod(err.fileno(),0o600)
                try:
                    proc=subprocess.Popen(command,cwd=m['workspace'],env=env,stdout=out,stderr=err,start_new_session=True)
                    while proc.poll() is None:
                        if time.time()-started>step['timeout'] or out.tell()+err.tell()>2_000_000:
                            os.killpg(proc.pid,signal.SIGTERM)
                            try:proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                            state='uncertain';break
                        time.sleep(.1)
                    code=proc.returncode
                except OSError:state='launch_failed'
        receipt={**base,'passed':code==0 and state=='finished','state':state if state!='finished' or code==0 else 'failed','exit_code':code,'finished':time.time(),'verified_at':stamp(),'side_effects_need_check':not step['check'] and (code!=0 or state!='finished')}
        if runner is None:
            try:
                from office_execution_outputs import project
                output = project(o.DATA_DIR, expanded, receipt)
                if output is not None:receipt['output'] = output
            except (OSError, ValueError, UnicodeError, KeyError, TypeError):
                receipt['output_warning'] = '限定查核數值尚未交付，owner需核對保護原件；不可重跑修改步驟。'
        atomic(receipt_file,receipt);atomic(folder/'execution-evidence'/(step_id+'.json'),receipt)
        return receipt

def receipts(folder):
    path=Path(folder)/'execution-evidence'
    return [json.loads(p.read_text()) for p in sorted(path.glob('*.json'))] if path.exists() else []


def enforce_result(handler,args):
    """交付不可略過固定步驟；人工回報只允許後續驗證，不把勾選當證據。"""
    e=(handler.job.get('context',{}).get('plan') or {}).get('execution')
    if not e or handler.job['kind'] not in ('implement','check','review'):return args
    rows={r['step_id']:r for r in receipts(handler.jobdir)}
    confirmed=bool(handler.job.get('context',{}).get('human_confirmed'))
    required=[r for r in e['commands'] if (handler.job['kind']=='implement' or r['check']) and (confirmed or not r['after_human'])]
    missing=[r['title'] for r in required if not rows.get(r['id'],{}).get('passed')]
    if args.get('outcome','completed')!='blocked' and not (handler.job['kind']=='review' and args.get('verdict')=='reject') and missing:
        raise ValueError('核准步驟未取得本輪成功證據：'+'；'.join(missing))
    if handler.job['kind'] in ('implement','check') and e.get('manual_actions') and not confirmed:
        if missing and args.get('outcome','completed')!='blocked':raise ValueError('先完成人工操作之前的核准步驟')
        if not missing:
            args={**args,'outcome':'blocked','verdict':'none','blockers':['等待本人操作，再由夥伴獨立核對'], 'user_actions':e['manual_actions']}
    return args


def human_confirmed(c,job):
    current=dict(job)
    for _ in range(20):
        if c.execute('SELECT 1 FROM office_human_responses WHERE continuation_job=?',(current['id'],)).fetchone():return True
        if not current.get('parent_id'):return False
        parent=c.execute('SELECT * FROM office_jobs WHERE id=?',(current['parent_id'],)).fetchone()
        if not parent or parent['plan_id']!=job['plan_id']:return False
        current=dict(parent)
    return False
