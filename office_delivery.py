"""AI 協作辦公室：office_delivery。"""
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def initialize(c):
    c.executescript('''
      CREATE TABLE IF NOT EXISTS office_acceptances(
        delivery_id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL,
        decision TEXT NOT NULL, criteria TEXT NOT NULL, body TEXT NOT NULL,
        created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS office_human_responses(
        job_id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL,
        created_at TEXT NOT NULL, continuation_job INTEGER NOT NULL);
    ''')


def user_actions(result):
    actions = result.get('user_actions', [])
    if not isinstance(actions, list) or len(actions) > 8:
        raise ValueError('本人操作最多八項')
    if actions and result.get('outcome') != 'blocked':
        raise ValueError('尚待本人操作時必須回報 blocked，不能當成完成')
    clean = []
    for item in actions:
        if not isinstance(item, dict) or item.get('kind') not in ('login', 'password', 'confirm', 'manual'):
            raise ValueError('本人操作類型不符')
        row = {'kind': item['kind']}
        for key in ('title', 'where', 'instructions', 'done_when'):
            value = item.get(key)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
                raise ValueError('本人操作需列明標題、操作位置、步驟與完成條件')
            row[key] = value.strip()
        url = item.get('url', '')
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError('操作入口格式不符')
        if url:
            parsed = urlsplit(url)
            if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('操作入口只能使用不含帳密的 HTTP(S) 網址')
            # 不把暫時登入碼／憑證透過網址寫入辦公室紀錄。
            if parsed.query or parsed.fragment:
                raise ValueError('操作入口請填不帶查詢參數或片段的固定網址')
            row['url'] = url
        clean.append(row)
    return clean


def relative_file(name):
    if not isinstance(name, str):
        raise ValueError('成果檔名格式不符')
    rel = PurePosixPath(name)
    if (not rel.parts or rel.is_absolute() or str(rel) != name
            or any(x.startswith('.') or x in ('native.stdout', 'native.stderr', 'mcp.json') for x in rel.parts)
            or len(name) > 500):
        raise ValueError('成果檔案必須位於本輪工作區，且不是內部設定')
    return rel


def artifact_events(job, events, artifacts):
    if not isinstance(artifacts, list) or len(artifacts) > 40:
        raise ValueError('成果檔案清單格式不符')
    if job.get('delivery_protocol') and job['kind'] == 'implement' and not artifacts and not (job.get('context',{}).get('plan') or {}).get('execution'):
        raise ValueError('實作必須交付實際檔案，文字報告不能代替產物')
    seen = set()
    for item in artifacts:
        name = str(relative_file(item['name']))
        if name in seen:
            raise ValueError('成果檔案重複')
        seen.add(name)
        path = str(Path(job['workspace']) / name)
        writes = [e['file_write'] for e in events if e.get('success') and e.get('tool') == 'write_file'
                  and e.get('file_write', {}).get('path') == path]
        if not writes or writes[-1].get('sha256') != item.get('sha256'):
            raise ValueError('成果缺少本輪相同版本的寫入證據：' + name)
        if not any(e.get('success') and e.get('tool') == 'check_file'
                   and e.get('file_check', {}).get('path') == path
                   and e['file_check'].get('sha256') == item['sha256']
                   and e['file_check'].get('passed') is True for e in events):
            raise ValueError('成果缺少相同版本的檔案檢查：' + name)


def collect_artifacts(job, events):
    if job['kind'] != 'implement' or not job.get('delivery_protocol'):
        return []
    workspace = Path(job['workspace']).resolve()
    writes = {}
    for event in events:
        item = event.get('file_write', {})
        if event.get('success') and event.get('tool') == 'write_file' and item.get('path'):
            writes[item['path']] = item
    artifacts = []
    for name, written in writes.items():
        path = Path(name)
        rel = str(relative_file(path.relative_to(workspace).as_posix()))
        if path.is_symlink() or path.resolve() != path or not path.is_file() or path.stat().st_size > 200000:
            raise ValueError('成果不存在、越界或超過大小限制：' + rel)
        data = path.read_bytes()
        if sha(data) != written['sha256']:
            raise ValueError('成果已變更，需重新核對：' + rel)
        artifacts.append({'name': rel, 'sha256': sha(data), 'bytes': len(data)})
    artifact_events(job, events, artifacts)
    return artifacts


def seal_artifacts(folder, workspace, artifacts):
    """只固定本輪已驗證的產物，不掃描或公布任意資料夾。"""
    root = Path(workspace).resolve()
    destination = Path(folder) / 'artifacts'
    destination.mkdir(mode=0o700, exist_ok=True)
    total = 0
    for index, item in enumerate(artifacts):
        path = root / str(relative_file(item['name']))
        if path.resolve() != path or not path.is_file() or path.stat().st_size > 200000:
            raise ValueError('交付原件不存在或路徑變更')
        data = path.read_bytes()
        total += len(data)
        if total > 2000000 or len(data) != item['bytes'] or sha(data) != item['sha256']:
            raise ValueError('交付原件與工具證據不符')
        target = destination / str(index)
        if target.exists():
            if target.is_symlink() or target.read_bytes() != data:
                raise ValueError('既有交付快照不能覆蓋')
        else:
            target.write_bytes(data)
            target.chmod(0o600)


def snapshot(c, tid):
    task = c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
    mid = task['delivery_id']
    if not mid:
        return None
    message = c.execute('SELECT * FROM messages WHERE id=? AND task_id=?', (mid, tid)).fetchone()
    job = c.execute("SELECT * FROM office_jobs WHERE task_id=? AND delivery_id=? AND kind IN ('check','implement') ORDER BY id DESC LIMIT 1", (tid, mid)).fetchone()
    result = json.loads(job['result']) if job and job['result'] else {}
    plan = c.execute('SELECT payload FROM office_plans WHERE id=?', (job['plan_id'],)).fetchone() if job and job['plan_id'] else None
    criteria = json.loads(plan['payload'])['acceptance'] if plan else ['核對本輪成果、證據與限制是否符合需求']
    acceptance = c.execute('SELECT * FROM office_acceptances WHERE task_id=? AND delivery_id=?', (tid, mid)).fetchone()
    return {'delivery_id': mid, 'job_id': job['id'] if job else None,
            'kind': job['kind'] if job else 'legacy', 'worker': message['author'],
            'created_at': message['created_at'], 'report': result.get('message', message['body']),
            'execution_receipts':result.get('execution_receipts',[]),'artifacts': result.get('artifacts', []), 'evidence': result.get('evidence', []),
            'limitations': result.get('limitations', []), 'criteria': criteria,
            'acceptance': dict(acceptance) if acceptance else None}


def read_artifact(data_dir, job_id, index, item):
    root = Path(data_dir).resolve() / 'jobs' / str(job_id) / 'artifacts'
    path = root / str(index)
    if path.resolve() != path or not path.is_file() or path.stat().st_size > 200000:
        raise ValueError('交付快照不存在或路徑變更')
    data = path.read_bytes()
    if sha(data) != item['sha256'] or len(data) != item['bytes']:
        raise ValueError('交付快照已變更，不能當成原驗收版本')
    return data


def control(automation, c, task, action, body, target_id, checked, key):
    o = automation.o
    tid = task['id']
    if not isinstance(target_id, int) or isinstance(target_id, bool):
        raise o.OfficeError(400, '缺少本輪成果或操作識別碼')
    busy = c.execute("SELECT 1 FROM office_jobs WHERE task_id=? AND state IN ('queued','running')", (tid,)).fetchone()
    if busy:
        raise o.OfficeError(409, '請等目前工作完成，避免核對到變動中的結果')
    if action in ('accept_delivery', 'request_changes'):
        delivery = snapshot(c, tid)
        if not delivery or target_id != delivery['delivery_id']:
            raise o.OfficeError(409, '交付已更新，請重新檢視本輪成果')
        if action == 'accept_delivery':
            if task['status'] != 'approved':
                raise o.OfficeError(409, '請先完成本輪獨立複核，再由負責人驗收')
            expected = list(range(len(delivery['criteria'])))
            if not isinstance(checked, list) or any(type(x) is not int for x in checked) or sorted(checked) != expected:
                raise o.OfficeError(400, '請逐項確認本輪驗收條件')
            decision = 'accepted'
        else:
            if not body.strip():
                raise o.OfficeError(400, '請寫明哪裡需要修正')
            decision = 'changes_requested'
        c.execute('INSERT OR REPLACE INTO office_acceptances VALUES(?,?,?,?,?,?)',
                  (target_id, tid, decision, json.dumps(delivery['criteria'], ensure_ascii=False), body, o.now()))
        mid = o.add_msg(c, tid, o.BOSS, 'control', ('本人驗收通過；正式環境是否已更新，依本輪執行與獨立複核證據判斷。' if decision == 'accepted'
                           else '驗收要求修正，請接續討論與更新計畫。') + ('\n' + body if body else ''))
        if decision == 'changes_requested':
            automation.on_human_message(c, task, o.BOSS, mid, body)
        return

    original = c.execute('SELECT * FROM office_jobs WHERE id=? AND task_id=?', (target_id, tid)).fetchone()
    if not original or original['state'] != 'blocked' or not original['result']:
        raise o.OfficeError(409, '這項待操作工作已更新，請重新檢視')
    response = c.execute('SELECT 1 FROM office_human_responses WHERE job_id=?', (target_id,)).fetchone()
    if response:
        raise o.OfficeError(409, '已收到完成回報，不會重複派工')
    result = json.loads(original['result'])
    actions = user_actions(result)
    if not actions or not isinstance(checked, list) or any(type(x) is not int for x in checked) or sorted(checked) != list(range(len(actions))):
        raise o.OfficeError(400, '請先完成並勾選本輪列出的操作')
    from office_automation import attention_jobs, process_identity
    if target_id not in attention_jobs(c, tid):
        raise o.OfficeError(409, '這項操作已有後續結果，請看最新進度')
    if original['native_pid'] and process_identity(original['native_pid']) == original['process_start']:
        raise o.OfficeError(409, '原程序尚未結束，請先核對，避免重複施工')
    control_row = c.execute('SELECT * FROM office_controls WHERE task_id=?', (tid,)).fetchone()
    if control_row and control_row['discussion_message'] > (original['trigger_message'] or 0):
        raise o.OfficeError(409, '需求已更新，請先依新討論整理計畫')
    if original['plan_id']:
        plan = c.execute('SELECT id,status FROM office_plans WHERE task_id=? ORDER BY id DESC LIMIT 1', (tid,)).fetchone()
        if not plan or plan['id'] != original['plan_id'] or plan['status'] != 'approved':
            raise o.OfficeError(409, '原動工計畫已更新，不能沿用舊操作回報施工')
    if original['kind'] == 'review' and original['delivery_id'] != task['delivery_id']:
        raise o.OfficeError(409, '待複核的成果版本已更新')
    labels = '；'.join(x['title'] for x in actions)
    mid = o.add_msg(c, tid, o.BOSS, 'control', '已回報完成本人操作：' + labels + '\n請先驗證完成條件，再依原授權接續；回報本身不是驗證成功。')
    payload = json.loads(original['payload'])
    instruction = ('負責人已回報完成人工操作：' + labels + '\n' +
                   '\n'.join(x['done_when'] for x in actions) +
                   '\n先使用本輪工具核對完成條件與既有副作用，再接續原工作；不能重複已完成的修改。'
                   ' 若仍無工具或證據，回報 blocked，不能把本人回報當成驗證成功。\n' + payload['body'])
    jid = automation.enqueue(c, tid, original['kind'], key + ':continue', instruction, mid,
                             original['worker'], original['plan_id'], original['delivery_id'],
                             original['parent_id'], original['attempt'], payload['authority'])
    if payload.get('require_plan'):
        next_payload = json.loads(c.execute('SELECT payload FROM office_jobs WHERE id=?', (jid,)).fetchone()[0])
        next_payload['require_plan'] = True
        c.execute('UPDATE office_jobs SET payload=? WHERE id=?', (json.dumps(next_payload), jid))
    c.execute('INSERT INTO office_human_responses VALUES(?,?,?,?)', (target_id, tid, o.now(), jid))
    c.execute('UPDATE office_controls SET paused=0,mode=? WHERE task_id=?',
              ('discuss' if original['kind'] == 'discuss' else 'execute', tid))
    o.set_status(c, tid, 'discuss' if original['kind'] == 'discuss' else 'review' if original['kind'] == 'review' else 'working')
