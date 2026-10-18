"""AI 協作辦公室：office_native。"""
from datetime import datetime
import json
import re
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
from office_worker_tools import available_tools
from office_model_discovery import cli_path

ROOT=Path(__file__).resolve().parent


class ActivityWatchdog:
    """將總時間與無活動等待分開；持續輸出也不能突破總上限。"""
    def __init__(self, wall_timeout=1800, idle_timeout=480, now=None):
        self.started=time.monotonic() if now is None else now
        self.last_activity=self.started
        self.signature=None
        self.wall_timeout=wall_timeout
        self.idle_timeout=idle_timeout

    def check(self, now, signature):
        if signature != self.signature:
            self.signature=signature
            self.last_activity=now
        if now-self.started >= self.wall_timeout:return 'wall_timeout'
        if now-self.last_activity >= self.idle_timeout:return 'idle_timeout'
        return None


def activity_signature(directory):
    result=[]
    for name in ('native.stdout','native.stderr','tool-events.jsonl'):
        path=directory/name
        try:
            stat=path.stat();result.append((name,stat.st_size,stat.st_mtime_ns))
        except FileNotFoundError:result.append((name,None,None))
    return tuple(result)


def grok_turn_budget(manifest):
    """僅按本輪核准的必讀來源頁數增加回合，不擴充工具或執行時間。"""
    if not isinstance(manifest,dict):raise ValueError('Grok工作單格式不正確')
    context=manifest.get('context',{})
    if not isinstance(context,dict):raise ValueError('Grok工作脈絡格式不正確')
    sources=context.get('sources',[])
    if not isinstance(sources,list):raise ValueError('Grok來源中繼資料必須是清單')
    pages=0
    for source in sources:
        if not isinstance(source,dict) or type(source.get('required',True)) is not bool:
            raise ValueError('Grok來源必讀標記格式不正確')
        lines=source.get('total_lines')
        if type(lines) is not int or lines<0:raise ValueError('Grok來源行數必須是非負整數')
        if source.get('required',True):pages+=(lines+119)//120
    return min(64,max(16,16+pages))


def command(worker, directory, session=None):
    directory=Path(directory)
    manifest_kind=json.loads((directory/'manifest.json').read_text()).get('kind')
    tool_script='office_summary_worker.py' if manifest_kind=='summary' else 'office_worker_tools.py'
    args=['python3',str(ROOT/tool_script),str(directory/'manifest.json')]
    mcp={'mcpServers':{'office':{'command':args[0],'args':args[1:]}}}
    (directory/'mcp.json').write_text(json.dumps(mcp))
    if worker=='gemini':raise ValueError('此測試版尚未提供 Gemini CLI adapter')
    if worker in ('claude','assistant'):
        sid=session or str(uuid.uuid4())
        cmd=[cli_path(worker),'-p','--output-format','stream-json' if worker=='claude' else 'json','--tools','','--strict-mcp-config',
             '--mcp-config',str(directory/'mcp.json'),'--allowedTools','mcp__office__*',
             '--permission-mode','dontAsk','--resume' if session else '--session-id',sid]
        if worker=='claude':cmd+=['--verbose','--include-partial-messages']
    elif worker=='grok':
        sid=session or str(uuid.uuid4())
        # Grok resume會恢復原工作目錄，因此同session固定目錄，逐輪更新工作單入口。
        session_dir=directory.parent/'native-sessions'/sid
        config_dir=session_dir/'.grok';config_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
        # 只信任本程式建立且逐次查核的獨立工作目錄，以載入這一份 MCP。
        if any(p.name != 'config.toml' for p in config_dir.iterdir()):
            raise ValueError('工作目錄出現未核對的 Grok 設定')
        # 完整工作脈絡須能由核准MCP直接讀取，避免預設20KB截斷後要求額外讀CLI內部檔。
        manifest_bytes=(directory/'manifest.json').read_bytes()
        turn_budget=grok_turn_budget(json.loads(manifest_bytes))
        output_bytes=max(20000,2*len(manifest_bytes)+8192)
        (config_dir/'config.toml').write_text('[mcp]\nmax_output_bytes='+str(output_bytes)+'\n[mcp_servers.office]\ncommand="python3"\nargs='+json.dumps(args[1:])+'\n[mcp_servers.deja]\nenabled=false\n')
        cmd=[cli_path(worker),'--trust','--cwd',str(session_dir),'--prompt-file',str(directory/'prompt.txt'),
             '--output-format','json','--tools','search_tool,use_tool','--permission-mode','dontAsk','--allow','mcp__office__*',
             '--disable-web-search','--no-subagents','--max-turns',str(turn_budget),'--resume' if session else '--session-id',sid]
    elif worker=='codex':
        sid=session
        manifest=json.loads((directory/'manifest.json').read_text())
        allowed=available_tools(manifest)
        config=['-c','mcp_servers.office.command="python3"','-c','mcp_servers.office.args='+json.dumps(args[1:]),
                '-c','features.shell_tool=false','-c','mcp_servers.office.required=true',
                '-c','mcp_servers.office.enabled_tools='+json.dumps(allowed)]
        # 依負責人已授權的工作單，逐項登錄這一輪可用工具；不改全域核准政策。
        for name in allowed:config+=['-c',f'mcp_servers.office.tools.{name}.approval_mode="approve"']
        cmd=[cli_path(worker),'exec','--json','--sandbox','read-only']
        # CLI 0.159.2：resume 內層的 -c 會取代外層整批覆寫；所有設定必須放同一層。
        if session:cmd+=['resume']+config+['--skip-git-repo-check',session,'-']
        else:cmd+=config+['-C',str(directory), '--skip-git-repo-check','-']
    else:raise ValueError('不認識的CLI')
    model=json.loads((directory/'manifest.json').read_text()).get('model')
    if model is not None:
        if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:+\[\]-]{0,119}',model):raise ValueError('模型識別格式不符')
        # 明確指定這一輪的模型，連resume亦傳入，不修改全域設定。
        if worker=='codex':
            at=cmd.index('resume')+1 if session else 2
            cmd[at:at]=['--model',model]
        else:cmd+=['--model',model]
    effort=json.loads((directory/'manifest.json').read_text()).get('effort')
    if effort is not None:
        allowed=({'none','minimal','low','medium','high','xhigh','max','ultra'} if worker=='codex'
                 else {'low','medium','high','xhigh'} if worker=='grok'
                 else {'low','medium','high','xhigh','max'})
        if type(effort) is not str or effort not in allowed:raise ValueError('思考強度格式或原生支援不符')
        if worker=='codex':
            at=cmd.index('resume')+1 if session else 2
            cmd[at:at]=['-c','model_reasoning_effort='+json.dumps(effort)]
        else:cmd+=['--reasoning-effort' if worker=='grok' else '--effort',effort]
    return cmd,sid



def missing_result_reason(meta, directory):
    """沒有收據時只報已觀測的結束類型，不從模型自述猜測逾時或成功。"""
    if meta.get('watchdog_reason') == 'wall_timeout':
        return '原生CLI未交付實質結果；已達單次工作時間上限'
    if meta.get('watchdog_reason') == 'idle_timeout':
        return '原生CLI未交付實質結果；連續無新輸出或工具活動，已停止等待'
    code = meta.get('exit_code')
    if type(code) is int and code != 0:
        return f'原生CLI未交付實質結果；CLI異常結束（退出碼{code}），需核對原生錯誤紀錄'
    events = Path(directory) / 'tool-events.jsonl'
    if code == 0 and (not events.exists() or events.stat().st_size == 0):
        return '原生CLI未交付實質結果；CLI已正常結束，但沒有本輪辦公室工具呼叫紀錄（非逾時）'
    if code == 0:
        return '原生CLI未交付實質結果；CLI已正常結束，但未透過交件工具完成提交（非逾時）'
    return '原生CLI未交付實質結果；未取得可核對的交件收據與結束原因'


def run(worker,directory,session=None,on_start=None,timeout=1800,local=False,idle_timeout=480):
    if worker=='gemini':raise ValueError('此測試版尚未提供 Gemini CLI adapter')
    from office_config import CONFIG
    if not CONFIG['automation']:raise ValueError('手動測試模式未啟動模型')
    if CONFIG['workers'].get(worker,{}).get('host') and not local:
        from office_remote import run_remote
        return run_remote(directory,session,on_start,timeout,idle_timeout=idle_timeout)
    profile=CONFIG['workers'].get(worker,{})
    if not profile.get('enabled') or not profile.get('model'):
        raise ValueError('請先啟用工作者並填寫 model；本輪未啟動 CLI')
    directory=Path(directory);cmd,sid=command(worker,directory,session)
    prompt=(directory/'prompt.txt').read_bytes()
    result_path=directory/'result.json';submitted=None
    with (directory/'native.stdout').open('wb') as out,(directory/'native.stderr').open('wb') as err:
        os.fchmod(out.fileno(),0o600);os.fchmod(err.fileno(),0o600)
        child_env=os.environ.copy()
        requested_effort=json.loads((directory/'manifest.json').read_text()).get('effort')
        if worker in ('claude','assistant') and requested_effort is not None:child_env['CLAUDE_CODE_EFFORT_LEVEL']=requested_effort
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=out,stderr=err,cwd=directory,env=child_env,start_new_session=True)
        old_handlers={}
        if worker in ('assistant','claude','codex') and local:
            def terminate_child(signum,frame):
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                raise SystemExit(128+signum)
            for sig in (signal.SIGHUP,signal.SIGTERM):
                old_handlers[sig]=signal.signal(sig,terminate_child)
        if on_start:on_start(proc.pid,sid)
        if worker!='grok':proc.stdin.write(prompt);proc.stdin.flush()
        proc.stdin.close()
        watchdog=ActivityWatchdog(timeout,idle_timeout)
        watchdog.check(time.monotonic(),activity_signature(directory))
        watchdog_reason=None
        while proc.poll() is None:
            if result_path.exists() and submitted is None:submitted=time.monotonic()
            # 已透過工具提交結果與任務記憶，給CLI時間正常結束；停止重複護欄回合。
            watchdog_reason=watchdog.check(time.monotonic(),activity_signature(directory))
            if watchdog_reason or (submitted is not None and time.monotonic()-submitted>40):
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                break
            time.sleep(.25)
    for sig,handler in old_handlers.items():signal.signal(sig,handler)
    raw=(directory/'native.stdout').read_text(errors='replace')
    stop_reason=None
    if worker=='codex':
        for line in raw.splitlines():
            try:x=json.loads(line)
            except ValueError:continue
            if x.get('type')=='thread.started':sid=x.get('thread_id')
    elif worker=='claude':
        # partial事件立即落入600權限stdout，供原閒置計時器看見真輸出。
        # 完成依舊由submit_result與controller證據核對，不從片段文字推定。
        for line in raw.splitlines():
            try:x=json.loads(line)
            except ValueError:continue
            if not isinstance(x,dict):continue
            if x.get('type')=='system' and x.get('subtype')=='init':sid=x.get('session_id') or sid
            if x.get('type')=='result':
                sid=x.get('session_id') or sid
                stop_reason=x.get('subtype')
    else:
        try:
            x=json.loads(raw);sid=x.get('sessionId') or x.get('session_id') or sid
            stop_reason=x.get('stopReason') or x.get('subtype')
        except ValueError:pass
    if watchdog_reason:
        stop_reason=('CLI達'+str(timeout)+'秒單次工作上限' if watchdog_reason=='wall_timeout'
                     else 'CLI連續'+str(idle_timeout)+'秒無新輸出或工具活動')
    reported=set()
    for line in raw.splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if not isinstance(event,dict):continue
        values=list(event.get('modelUsage',{})) if isinstance(event.get('modelUsage'),dict) else []
        if isinstance(event.get('message'),dict):values.append(event['message'].get('model'))
        if event.get('type')=='system' and event.get('subtype')=='init':values.append(event.get('model'))
        for value in values:
            if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:+\[\]-]{0,119}',value):reported.add(value)
    return {'requested_effort':json.loads((directory/'manifest.json').read_text()).get('effort'),
            'requested_model':json.loads((directory/'manifest.json').read_text()).get('model'),'reported_models':sorted(reported),
            'session_id':sid,'exit_code':proc.returncode,'stop_reason':stop_reason,
            'submitted':result_path.exists(),'finished_at':datetime.now().astimezone().isoformat(),
            'watchdog_reason':watchdog_reason,'wall_timeout_seconds':timeout,'idle_timeout_seconds':idle_timeout}
