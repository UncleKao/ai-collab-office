"""AI 協作辦公室：office_remote。"""
import base64,hashlib,json,os,re,signal,subprocess,sys,time,uuid
from pathlib import Path,PurePosixPath
from office_config import CONFIG
SEATS={w:p for w,p in CONFIG['workers'].items() if p.get('host')}
def seat(worker):
    if worker not in SEATS:raise ValueError('未允許的遠端夥伴')
    value=SEATS[worker]
    return value,Path(value.get('remote_dir') or str(Path(value['home'])/'.local/state/ai-collab-office'))

LIMIT=12_000_000
OMIT={'native.stdout','native.stderr','mcp.json','.git','.ssh','.secrets','.claude','.codex','.grok','execution-capability.json'}
def digest(value):return hashlib.sha256(value).hexdigest()
def files(root):
    root=Path(root);out={};size=0
    if not root.exists():return out
    for p in root.rglob('*'):
        if any(x in OMIT for x in p.relative_to(root).parts):continue
        if p.is_symlink():raise ValueError('工作區不傳符號連結')
        if not p.is_file():continue
        value=p.read_bytes();size+=len(value)
        if size>4_000_000 or len(out)>=100:raise ValueError('工作區過大，請縮小本輪範圍')
        out[p.relative_to(root).as_posix()]=base64.b64encode(value).decode()
    return out

def unpack(values,root):
    if not isinstance(values,dict) or len(values)>100:raise ValueError('檔案清單格式不符')
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=True);total=0
    for name,encoded in values.items():
        rel=PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or any(x in OMIT for x in rel.parts):raise ValueError('檔案路徑不在核准範圍')
        p=root/name
        if not p.resolve().is_relative_to(root.resolve()):raise ValueError('路徑越界')
        data=base64.b64decode(encoded,validate=True);total+=len(data)
        if total>4_000_000:raise ValueError('檔案總量過大')
        p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        temp=p.with_name('.'+p.name+'.office-tmp');temp.write_bytes(data);temp.chmod(0o600);os.replace(temp,p)

def map_paths(value,mapping):
    if isinstance(value,dict):return {k:map_paths(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [map_paths(v,mapping) for v in value]
    if isinstance(value,str):
        for source,target in sorted(mapping.items(),key=lambda pair:-len(pair[0])):value=value.replace(source,target)
    return value

def run_remote(directory,session=None,on_start=None,timeout=1800,idle_timeout=480):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    profile,REMOTE=seat(manifest['worker'])
    if manifest['worker']=='assistant' and (manifest.get('baseline') or manifest.get('desktop_probe')):raise ValueError('助理入口不接受此維運工作單')
    workspace=Path(manifest['workspace']);before=files(workspace)
    payload={'manifest':manifest,'manifest_sha256':digest((directory/'manifest.json').read_bytes()),'prompt':(directory/'prompt.txt').read_text(),
             'session':session,'workspace':before,'refs':[files(p) for p in manifest.get('read_roots',[])],'timeout':timeout,'idle_timeout':idle_timeout}
    if manifest.get('execution_capability'):payload['execution_capability']=json.loads((directory/'execution-capability.json').read_text())
    encoded=json.dumps(payload,ensure_ascii=False).encode()
    if len(encoded)>LIMIT:raise ValueError('工作單過大')
    cmd=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',profile['host'],'python3',str(REMOTE/'adapter/office_remote.py'),'--worker']
    with (directory/'remote-response.json').open('wb') as output,(directory/'remote-error.txt').open('wb') as error:
        os.fchmod(output.fileno(),0o600);os.fchmod(error.fileno(),0o600)
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=output,stderr=error,start_new_session=True)
        if on_start:on_start(p.pid,session)
        try:p.communicate(encoded,timeout=timeout+30)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=8);raise RuntimeError('遠端原生接單逾時；未重複派工，遠端亦有同輪時限')
    if p.returncode:raise RuntimeError('遠端原生接單通道未完成；錯誤留在本輪受保護檔案')
    response=json.loads((directory/'remote-response.json').read_text())
    if response.get('source_manifest_sha256')!=payload['manifest_sha256']:raise ValueError('遠端回覆與本輪工作單不符')
    # 依固定路徑映射重建遠端工作單，保留原始工具回應雜湊。
    remote_run=Path(response['meta']['remote_run'])
    if remote_run.parent!=REMOTE/'runs' or not re.fullmatch(r'[a-f0-9]{32}',remote_run.name):raise ValueError('遠端工作區識別不符')
    mapping={manifest['workspace']:str(remote_run/'workspace')}
    refs=[str(remote_run/'refs'/str(i)) for i in range(len(manifest.get('read_roots',[])))]
    mapping.update(zip(manifest.get('read_roots',[]),refs))
    remote_manifest=map_paths(manifest,mapping);remote_manifest['workspace']=str(remote_run/'workspace');remote_manifest['read_roots']=refs
    if manifest.get('execution_capability'):remote_manifest['remote_execution']=True
    remote_bytes=json.dumps(remote_manifest,ensure_ascii=False).encode()
    if 'result.json' in response.get('job_files',{}):
        returned=json.loads(base64.b64decode(response['job_files']['result.json'],validate=True))
        if returned.get('remote_manifest_sha256')!=digest(remote_bytes):raise ValueError('遠端工作單映射與交付雜湊不符')
    (directory/'remote-manifest.json').write_bytes(remote_bytes);(directory/'remote-manifest.json').chmod(0o600)
    if not manifest.get('execution_capability') and files(workspace)!=before:raise ValueError('本機工作區已變更，保留遠端成果待核對')
    after=response['workspace']
    if manifest['kind']!='implement' and after!=before:raise ValueError('唯讀工作出現未允許的修改')
    if manifest['kind']=='implement':unpack(after,workspace)
    for name in ('result.json','tool-events.jsonl','worker-memory.json','web-evidence.json'):
        data=response.get('job_files',{}).get(name)
        if data is not None:
            (directory/name).write_bytes(base64.b64decode(data,validate=True));(directory/name).chmod(0o600)
    return response['meta']

def worker():
    os.umask(0o077)
    import socket
    hostname=socket.gethostname()
    raw=sys.stdin.buffer.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError('工作單過大')
    payload=json.loads(raw);original=payload['manifest']
    profile,REMOTE=seat(original.get('worker'))
    if Path.home()!=Path(profile['home']) or hostname.lower()!=profile['hostname'].lower():raise ValueError('工作單與夥伴座位不符')
    if original.get('worker') not in SEATS or original.get('kind') not in ('discuss','check','implement','review','summary'):raise ValueError('未允許的工作單')
    if original['worker']=='assistant' and (original.get('baseline') or original.get('desktop_probe')):raise ValueError('助理入口不接受此維運工作單')
    session=payload.get('session')
    if session is not None and not re.fullmatch(r'[a-fA-F0-9-]{36}',session):raise ValueError('原生session格式不符')
    requested_session=session
    if session and original['worker']=='codex':
        import sqlite3
        db=Path.home()/'.codex/state_5.sqlite'
        if db.is_file():
            conn=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
            try:present=conn.execute('SELECT 1 FROM threads WHERE id=?',(session,)).fetchone() is not None
            finally:conn.close()
        else:present=False
        if not present:session=None
    elif session and original['worker']=='claude':
        if not any((Path.home()/'.claude/projects').glob('*/'+session+'.jsonl')):session=None
    root=REMOTE/'runs'/uuid.uuid4().hex;root.mkdir(mode=0o700,parents=True)
    job=root/'job';job.mkdir(mode=0o700);work=root/'workspace';unpack(payload['workspace'],work)
    mapping={original['workspace']:str(work)};refs=[]
    for index,values in enumerate(payload['refs']):
        target=root/'refs'/str(index);unpack(values,target);refs.append(str(target));mapping[original['read_roots'][index]]=str(target)
    manifest=map_paths(original,mapping);manifest['workspace']=str(work);manifest['read_roots']=refs
    if original.get('execution_capability'):
        manifest['remote_execution']=True
        cap=payload.get('execution_capability')
        if not isinstance(cap,dict) or digest(cap.get('token','').encode())!=original['execution_capability']['sha256']:raise ValueError('本輪固定步驟身分不符')
        (job/'execution-capability.json').write_text(json.dumps(cap));(job/'execution-capability.json').chmod(0o600)
    (job/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
    prompt=map_paths(payload['prompt'],mapping)
    if requested_session and not session:prompt='上一座位原生session未移轉。本輪依附帶工作單與公開辦公室脈絡新開接續，不宣稱已取得完整原生歷史。\n'+prompt
    (job/'prompt.txt').write_text(prompt)
    import office_native
    meta=office_native.run(original['worker'],job,session,timeout=min(1800,max(30,int(payload['timeout']))),local=True,
                          idle_timeout=min(480,max(30,int(payload.get('idle_timeout',480)))))
    meta['previous_session_unavailable']=bool(requested_session and not session)
    exported={}
    for name in ('result.json','tool-events.jsonl','worker-memory.json','web-evidence.json'):
        p=job/name
        if p.exists():
            if name=='result.json':
                result=json.loads(p.read_text());assert result['manifest_sha256']==digest((job/'manifest.json').read_bytes())
                result['remote_manifest_sha256']=result['manifest_sha256'];result['manifest_sha256']=payload['manifest_sha256']
                result=map_paths(result,{v:k for k,v in mapping.items()});data=json.dumps(result,ensure_ascii=False).encode()
            else:data=p.read_bytes()
            exported[name]=base64.b64encode(data).decode()
    answer={'source_manifest_sha256':payload['manifest_sha256'],'workspace':files(work),'job_files':exported,'meta':{**meta,'host':hostname,'remote_run':str(root)}}
    print(json.dumps(answer,ensure_ascii=False))
if __name__=='__main__':worker()
