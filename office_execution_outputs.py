"""AI 協作辦公室：office_execution_outputs。"""
import hashlib
import json
import os
from pathlib import Path
import re
from office_sources import _source_directory, _source_bytes


def project(data_dir, step, receipt):
    """只交付固定 git／sha256sum／stat 格式，欄位與批准參數逐項對照。"""
    from office_execution import argv_program, safe_path
    if (not step['check'] or receipt.get('step_id') != step['id']
        or receipt.get('host') != step['host'] or receipt.get('check') is not True
        or receipt.get('passed') is not True or receipt.get('state') != 'finished'
        or receipt.get('exit_code') != 0 or type(receipt.get('job_id')) is not int):
        return None
    args = step['argv']; program, rest = argv_program(args)
    if args[0] == 'sudo' or '${workspace}' in ''.join(args):return None
    kind = None; targets = []
    if program == 'sha256sum' and rest[:1] == ['--']:
        kind = 'sha256'; targets = rest[1:]
    elif program == 'stat' and rest[:2] == ['--format=%n|%s|%Y|%a', '--']:
        kind = 'stat'; targets = rest[2:]
    elif (program == 'git' and rest[:2] == ['--no-optional-locks', '-C']
          and len(rest) > 3 and rest[3] == 'rev-parse'):
        kind = 'git_objects'; targets = rest[4:]
        if targets[:1] == ['--verify']:targets = targets[1:]
        if not targets or targets[0] != 'HEAD' or any(not v.startswith('HEAD:') for v in targets[1:]):return None
        safe_path(rest[2])
    elif (program == 'git' and rest[:2] == ['--no-optional-locks', '-C']
          and rest[3:9] == ['diff', '--quiet', '--no-ext-diff', '--no-textconv', 'HEAD', '--']):
        kind = 'git_quiet'; safe_path(rest[2])
    if kind is None:return None
    if kind in ('sha256', 'stat'):
        if not targets:return None
        for path in targets:safe_path(path)
    fd = _source_directory(Path(data_dir)/'execution-private'/str(receipt['job_id']))
    try:
        out = _source_bytes(fd, step['id']+'.stdout', 200000)
        err = _source_bytes(fd, step['id']+'.stderr', 200000)
    finally:os.close(fd)
    # 非空 stderr 留給 owner 查證；不把任意訊息當成安全文字回傳。
    if err:raise ValueError('查核 stderr 非空，owner 需核對原件')
    lines = out.decode('utf-8').splitlines(); rows = []
    if kind == 'git_quiet':
        if out:raise ValueError('quiet 查核輸出不符')
    else:
        if len(lines) != len(targets):raise ValueError('查核輸出筆數不符')
        for target, line in zip(targets, lines):
            if kind == 'git_objects':
                if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', line):raise ValueError('Git 物件格式不符')
                rows.append({'object':target, 'oid':line})
            elif kind == 'sha256':
                match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
                if not match or match[2] != target:raise ValueError('雜湊路徑或格式不符')
                rows.append({'path':target, 'sha256':match[1]})
            else:
                fields = line.split('|')
                if (len(fields) != 4 or fields[0] != target or not fields[1].isdigit()
                    or not re.fullmatch(r'-?\d+', fields[2]) or not re.fullmatch(r'[0-7]{1,4}', fields[3])):
                    raise ValueError('stat 路徑或數值不符')
                rows.append({'path':target, 'bytes':int(fields[1]), 'mtime_epoch':int(fields[2]), 'mode':fields[3]})
    return {'kind':kind, 'rows':rows, 'stdout_bytes':len(out), 'stderr_bytes':len(err),
            'stdout_sha256':hashlib.sha256(out).hexdigest(), 'stderr_sha256':hashlib.sha256(err).hexdigest(),
            'limitation':'只交付核准查核的限定欄位；成功收據不等於版本或功能驗收通過。'}


def collect(o, task, origin):
    """沿同件補件鏈定位原執行，不重跑；DB 批准計畫決定允許讀取的步驟。"""
    with o.tx() as c:
        seen = set(); job = None; plan = None
        while type(origin) is int and origin not in seen and len(seen) < 20:
            seen.add(origin)
            job = c.execute('SELECT * FROM office_jobs WHERE id=? AND task_id=?', (origin, task['id'])).fetchone()
            if not job:return []
            if job['plan_id']:
                plan = c.execute('SELECT * FROM office_plans WHERE id=? AND task_id=?', (job['plan_id'], task['id'])).fetchone()
                break
            origin = json.loads(job['payload']).get('repair_origin')
        if not plan or plan['status'] != 'approved':return []
        if hashlib.sha256(plan['payload'].encode()).hexdigest() != plan['plan_sha']:raise ValueError('核准計畫指紋不符')
        from office_execution import normalize
        execution = normalize(json.loads(plan['payload']).get('execution'))
        if not execution:return []
        job = dict(job); plan = dict(plan)
    entries = []; unavailable = []
    fd = _source_directory(Path(o.DATA_DIR)/'jobs'/str(job['id'])/'execution-evidence')
    try:
        for step in execution['commands']:
            try:
                receipt = json.loads(_source_bytes(fd, step['id']+'.json', 200000))
                if (receipt.get('job_id') != job['id'] or receipt.get('plan_id') != plan['id']
                    or receipt.get('plan_sha256') != plan['plan_sha']):raise ValueError('查核收據與核准計畫不符')
                output = project(o.DATA_DIR, step, receipt)
                if output is None:unavailable.append({'step_id':step['id'], 'reason':'此指令不在限定輸出投影內'});continue
                entries.append({'receipt':receipt, 'approved_argv':step['argv'], 'output':output})
            except (OSError, ValueError, UnicodeError, KeyError, TypeError):
                unavailable.append({'step_id':step['id'], 'reason':'原件未取得或格式未通過，owner 需核對；未重跑'})
    finally:os.close(fd)
    from office_execution import stamp
    value = {'captured_at':stamp(), 'task_id':task['id'], 'execution_job':job['id'], 'plan_id':plan['id'],
             'plan_sha256':plan['plan_sha'], 'entries':entries, 'unavailable':unavailable,
             'limitations':['這是原執行保護檔的後續限定投影，沒有重新執行命令。', '原收據、交件及批准計畫未覆寫；功能與其他階段驗收另核對。']}
    return [{'name':'approved_execution_outputs.json', 'content':json.dumps(value, ensure_ascii=False, indent=2)}]
