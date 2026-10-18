"""AI 協作辦公室：office_assignment。"""
import json
import office_people as people


def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS office_assignments(
        task_id INTEGER PRIMARY KEY, worker TEXT, discussion_workers TEXT NOT NULL,
        reviewers TEXT NOT NULL, integrator TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL,
        updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)''')
    if 'integrator' not in {row[1] for row in c.execute('PRAGMA table_info(office_assignments)')}:
        c.execute("ALTER TABLE office_assignments ADD COLUMN integrator TEXT NOT NULL DEFAULT ''")


def default_integrator(task):
    return people.LIFE_LEAD if people.task_team(task) == 'life' else next(iter(people.MAINTENANCE_MEMBERS),'')


def editable(c, task):
    requires_acceptance = task['created_by']!='owner' and task['approved_by']!='owner'
    if requires_acceptance and task['status'] not in ('proposal', 'inbox'):
        return False, '請先回到待收件或待分工，再由負責人收件並指定分工'
    if task['status'] not in ('inbox', 'discuss', 'working', 'fix') and not (requires_acceptance and task['status']=='proposal'):
        return False, '請先回到討論或明確重開任務，再調整分工'
    if c.execute("SELECT 1 FROM office_jobs WHERE task_id=? AND state IN ('queued','running')", (task['id'],)).fetchone():
        return False, '請等目前排隊或執行的工作完成，再調整分工'
    if task['delivery_id'] and task['status'] != 'discuss':
        reopened = c.execute("SELECT 1 FROM messages WHERE task_id=? AND author='owner' AND kind='decide' AND body LIKE '[reopen]%' AND id>?", (task['id'], task['delivery_id'])).fetchone()
        if task['status'] != 'fix' or not reopened:
            return False, '已有交付成果，請先回到討論或明確重開任務，再調整分工'
    return True, '尚未收件；儲存時須由負責人明確收件並指定分工，才會取得本輪授權' if requires_acceptance else ''


def snapshot(c, task):
    row = c.execute('SELECT * FROM office_assignments WHERE task_id=?', (task['id'],)).fetchone()
    if row:
        result = {k: row[k] for k in ('worker', 'integrator', 'version', 'updated_at', 'updated_by')}
        result['integrator'] = result['integrator'] or default_integrator(task)
        result.update(discussion_workers=json.loads(row['discussion_workers']), reviewers=json.loads(row['reviewers']))
    else:
        discussions = list(people.LIFE_MEMBERS if people.task_team(task) == 'life' else people.MAINTENANCE_MEMBERS)
        reviewers = task['reviewers'].split(',') if task['reviewers'] else discussions
        result = {'worker': None, 'integrator': default_integrator(task), 'discussion_workers': discussions, 'reviewers': reviewers,
                  'version': 0, 'updated_at': None, 'updated_by': None}
    for field in ('discussion_workers','reviewers'):
        result[field]=[w for w in result[field] if w in people.AUTO_WORKERS]
    if result['worker'] not in people.AUTO_WORKERS:result['worker']=None
    result['can_edit'], result['edit_reason'] = editable(c, task)
    result['requires_acceptance'] = task['created_by']!='owner' and task['approved_by']!='owner'
    return result


def save(o, c, task, value, actor):
    if actor!=o.BOSS:
        raise o.OfficeError(403, '只有負責人能指定分工')
    if not o.authorized_by(task)[0]:
        raise o.OfficeError(409, '請先由負責人明確收件，再儲存分工')
    if not isinstance(value, dict) or set(value) not in ({'worker', 'discussion_workers', 'reviewers', 'version'}, {'worker', 'discussion_workers', 'reviewers', 'integrator', 'version'}):
        raise o.OfficeError(400, '分工資料需要執行人、討論夥伴、整合者、複核夥伴與版本')
    current = snapshot(c, task)
    if type(value['version']) is not int or value['version'] < 0:
        raise o.OfficeError(400, '分工版本格式不符')
    if value['version'] != current['version']:
        raise o.OfficeError(409, '分工已更新，請重新檢視後再儲存')
    if not current['can_edit']:
        raise o.OfficeError(409, current['edit_reason'])
    worker = value['worker']
    if worker is not None and (not isinstance(worker, str) or worker not in people.EXECUTION_WORKERS or not people.in_team(worker, people.task_team(task))):
        raise o.OfficeError(403, people.GEMINI_REASON if worker == 'gemini' else '此夥伴未開放本區實作指派')
    integrator = value.get('integrator', current['integrator'])
    if not isinstance(integrator, str) or integrator not in people.EXECUTION_WORKERS or not people.in_team(integrator, people.task_team(task)):
        raise o.OfficeError(403, people.GEMINI_REASON if integrator == 'gemini' else '整合者須是本工作區可執行人選')
    groups = {}
    for field in ('discussion_workers', 'reviewers'):
        names = value[field]
        if not isinstance(names, list) or not names or len(names) > len(people.AUTO_WORKERS) or any(not isinstance(n, str) for n in names):
            raise o.OfficeError(400, '請至少指定一位討論夥伴與一位獨立複核夥伴')
        if len(set(names)) != len(names):
            raise o.OfficeError(400, '分工名單不能重複')
        if any(n not in people.AUTO_WORKERS for n in names):
            raise o.OfficeError(403, people.GEMINI_REASON if 'gemini' in names else '不認識的分工夥伴')
        if field == 'discussion_workers' and any(not people.in_team(n, people.task_team(task)) for n in names):
            raise o.OfficeError(403, '討論夥伴不得超出本工作區')
        groups[field] = list(names)
    if worker in groups['reviewers']:
        raise o.OfficeError(400, '執行人不能複核自己的成果，請另選複核夥伴')
    if people.task_team(task) == 'life' and worker and worker != 'assistant' and 'assistant' not in groups['reviewers']:
        groups['reviewers'].insert(0, 'assistant')
    # 自動安排也必須至少有一種可獨立複核的本區執行人選。
    eligible = [w for w in people.EXECUTION_WORKERS if people.in_team(w, people.task_team(task)) and any(r != w for r in groups['reviewers'])]
    if not eligible:
        raise o.OfficeError(400, '目前名單沒有可獨立複核的執行人選')
    from office_automation import process_identity
    for job in c.execute("SELECT native_pid,process_start FROM office_jobs WHERE task_id=? AND state='blocked' AND native_pid IS NOT NULL", (task['id'],)):
        if process_identity(job['native_pid'])==job['process_start'] and job['process_start']:
            raise o.OfficeError(409, '上次原生程序仍在，請先核對其結果，再調整分工')
    now = o.now()
    c.execute('''INSERT INTO office_assignments(task_id,worker,discussion_workers,reviewers,integrator,version,updated_at,updated_by)
              VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET worker=excluded.worker,discussion_workers=excluded.discussion_workers,
              reviewers=excluded.reviewers,integrator=excluded.integrator,version=excluded.version,updated_at=excluded.updated_at,updated_by=excluded.updated_by''',
              (task['id'], worker, json.dumps(groups['discussion_workers']), json.dumps(groups['reviewers']), integrator, current['version'] + 1, now, actor))
    # 舊交付與其複核紀錄保留；新分工不重算或延用舊交付。
    c.execute('UPDATE tasks SET owner=?,reviewers=?,delivery_id=NULL,delivery_by=NULL,updated_at=?,status=? WHERE id=?',
              ('assistant' if people.task_team(task) == 'life' else worker, ','.join(groups['reviewers']), now, 'inbox' if task['status']=='inbox' else 'discuss', task['id']))
    c.execute("UPDATE office_plans SET status='superseded' WHERE task_id=? AND status IN ('draft','approved')", (task['id'],))
    names = o.NAME_ZH
    text = ('已儲存分工；執行：' + (names.get(worker, worker) if worker else '自動安排') +
            '；討論：' + '、'.join(names.get(w, w) for w in groups['discussion_workers']) +
            '；整合：' + names.get(integrator, integrator) +
            '；複核：' + '、'.join(names.get(w, w) for w in groups['reviewers']) +
            '。尚未派出工作；先前計畫已失效，請依新分工整理計畫。')
    mid = o.add_msg(c, task['id'], actor, 'control', text)
    c.execute("INSERT INTO office_controls(task_id,paused,mode,discussion_message) VALUES(?,0,'discuss',?) ON CONFLICT(task_id) DO UPDATE SET mode='discuss',discussion_message=excluded.discussion_message", (task['id'], mid))
