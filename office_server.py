#!/usr/bin/env python3
"""AI 協作辦公室：office_server。"""
import argparse, fcntl, hashlib, html, ipaddress, json, os, secrets, socket, sqlite3, sys, threading, re
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path
from office_runtime import snapshot as execution_snapshot
import office_assignment
import office_models
import office_summary
import office_automation
import office_people as people
import office_delivery as handover
from office_capacity import capacity

VERSION = '0.1.0-beta.1'
SSO = None
SSO_CSRF_KEY = None
AUTOMATION = None
NOTICES = None
WEB_DIR = Path(__file__).resolve().parent / 'web'
FRONTEND_FILES = ('index.html', 'app.js', 'style.css', 'models.js')
FRONTEND_LOCK = threading.Lock()
_frontend_cache = None
from office_config import CONFIG, DATA_DIR as CONFIG_DATA_DIR, SECRET_DIR as CONFIG_SECRET_DIR
TZ = ZoneInfo(CONFIG['timezone'])
SECRET_DIR = str(CONFIG_SECRET_DIR)
DATA_DIR = str(CONFIG_DATA_DIR)
DB_PATH = os.path.join(DATA_DIR, 'office.db')
AGENTS = list(people.MEMBERS)          # 成員名單；Gemini仍由派工政策禁止啟動
BOSS = 'owner'
STATUSES = ['proposal', 'inbox', 'discuss', 'working', 'review', 'fix', 'approved', 'active', 'closed', 'dropped']
STATUS_ZH = {'proposal': '提案', 'inbox': '收件', 'discuss': '討論中', 'working': '實作中', 'review': '複核中',
             'fix': '修正中', 'approved': '複核全過·等拍板', 'active': '正式啟用', 'closed': '結案', 'dropped': '作廢'}
KIND_ZH = {'say': '發言', 'claim': '認領', 'deliver': '交付', 'review': '複核', 'decide': '拍板', 'system': '系統', 'new': '建立'}
NAME_ZH = {BOSS: CONFIG['owner_name'], 'system': '系統', **{w:m['name'] for w,m in people.MEMBERS.items()}}
TAILNET = ipaddress.ip_network('100.64.0.0/10')
LOCK = threading.Lock()
COOKIE = 'office_tok'
SITE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
            "font-src 'self'; frame-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
# 成果是 AI 產出、不可信：只給靜態畫面。沙箱不給任何權限（不跑 script、不同源、不彈窗、不導向），
PREVIEW_CSP = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; media-src data:; "
               "form-action 'none'; base-uri 'none'; frame-src 'none'; frame-ancestors 'self'")
# 預覽只准在任務頁內出現：HTML 只能被框載入、SVG 只能被圖片載入；直接整頁打開（可自行導向外站）一律拒絕。
PREVIEW_DEST = {'.html': 'iframe', '.htm': 'iframe', '.svg': 'image'}
PREVIEW_TYPES = {'.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8', '.svg': 'image/svg+xml'}


def now():
    return datetime.now(TZ).isoformat(timespec='seconds')


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


class OfficeError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg); self.code = code; self.msg = msg


def frontend_snapshot():
    """只快取讀取前後一致的靜態檔快照；熱更新不依賴重啟服務。"""
    global _frontend_cache
    paths = tuple(WEB_DIR / name for name in FRONTEND_FILES)

    def signature():
        result = []
        for path in paths:
            st = path.stat()
            result.append((str(path.resolve()), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
        return tuple(result)

    with FRONTEND_LOCK:
        try:
            for _ in range(3):
                before = signature()
                if _frontend_cache and _frontend_cache[0] == before:
                    return _frontend_cache[1], _frontend_cache[2]
                contents = tuple(path.read_bytes() for path in paths)
                if before != signature():
                    continue
                digest = hashlib.sha256()
                for name, content in zip(FRONTEND_FILES, contents):
                    digest.update(name.encode('utf-8') + b'\0')
                    digest.update(hashlib.sha256(content).digest())
                build = digest.hexdigest()
                _frontend_cache = (before, build, contents[0])
                return build, contents[0]
        except OSError:
            raise OfficeError(503, '辦公室畫面正在更新，請稍後再試') from None
    raise OfficeError(503, '辦公室畫面正在更新，請稍後再試')


def frontend_build():
    return frontend_snapshot()[0]


def frontend_page():
    build, content = frontend_snapshot()
    marker = b'\n  <meta name="office-build" content="' + build.encode('ascii') + b'">'
    page, count = re.subn(br'(<head\b[^>]*>)', lambda match: match.group(1) + marker, content, count=1, flags=re.IGNORECASE)
    if not count:
        raise OfficeError(503, '辦公室畫面格式尚未就緒，請稍後再試')
    return page


# ---------- token ----------
def load_tokens():
    """回傳 {sha256(token): name}。缺的 token 檔就產生（只寫檔、不印值）。"""
    os.makedirs(SECRET_DIR, mode=0o700, exist_ok=True)
    os.chmod(SECRET_DIR, 0o700)
    table = {}
    for name in [BOSS] + AGENTS:
        p = os.path.join(SECRET_DIR, f'{name}.tok')
        if not os.path.exists(p):
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(32) + '\n')
        os.chmod(p, 0o600)
        with open(p) as f:
            table[sha(f.read().strip())] = name
    return table


# ---------- db ----------
@contextmanager
def tx():
    """一個請求一個交易：LOCK 序列化本行程、BEGIN IMMEDIATE 序列化跨行程、結束一定 close。"""
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        with LOCK:
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
                c.execute('COMMIT')
            except Exception:
                c.execute('ROLLBACK')
                raise
    finally:
        c.close()


def init_db():
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    try:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, brief TEXT NOT NULL, status TEXT NOT NULL,
            created_by TEXT NOT NULL, owner TEXT, reviewers TEXT, delivery_id INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, author TEXT NOT NULL, kind TEXT NOT NULL,
            body TEXT NOT NULL, ref TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews(
            id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, delivery_id INTEGER NOT NULL,
            reviewer TEXT NOT NULL, verdict TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(delivery_id, reviewer));
        CREATE INDEX IF NOT EXISTS idx_msg_task ON messages(task_id);
        ''')
        cols = {r[1] for r in c.execute('PRAGMA table_info(tasks)')}
        for col in ('approved_by TEXT', 'approved_at TEXT', 'brief_sha TEXT', 'delivery_by TEXT', "team TEXT NOT NULL DEFAULT 'maintenance'"):
            if col.split()[0] not in cols:
                c.execute(f'ALTER TABLE tasks ADD COLUMN {col}')
        c.execute('UPDATE tasks SET delivery_by=(SELECT author FROM messages WHERE id=tasks.delivery_id) WHERE delivery_id IS NOT NULL AND delivery_by IS NULL')
        c.execute("UPDATE tasks SET brief_sha=? WHERE brief_sha IS NULL AND 0", ('',))
        for r in c.execute('SELECT id, brief FROM tasks WHERE brief_sha IS NULL').fetchall():
            c.execute('UPDATE tasks SET brief_sha=? WHERE id=?', (sha(r[1]), r[0]))
        c.commit()
        office_automation.initialize(c)
        c.commit()
    finally:
        c.close()
    os.chmod(DB_PATH, 0o600)


def parse_reviewers(s):
    if not s:
        return None
    names = [x.strip() for x in str(s).split(',') if x.strip()]
    bad = [n for n in names if n not in AGENTS]
    if bad:
        raise OfficeError(400, f'複核者只能是 {", ".join(AGENTS)}；不認識：{", ".join(bad)}')
    if any(n not in people.AUTO_WORKERS for n in names):raise OfficeError(403,'複核者尚未啟用派工')
    return ','.join(dict.fromkeys(names)) or None


def effective_reviewers(task):
    author = task['delivery_by'] if 'delivery_by' in task.keys() and task['delivery_by'] else task['owner']
    names = task['reviewers'].split(',') if task['reviewers'] else (list(people.LIFE_MEMBERS) if people.task_team(task)=='life' else list(people.MAINTENANCE_MEMBERS))
    if people.task_team(task)=='life' and people.LIFE_LEAD != author:names=[people.LIFE_LEAD]+names
    return list(dict.fromkeys(n for n in names if n != author and n in people.AUTO_WORKERS))


def authorized_by(t):
    """回傳 (是否授權, 依據文字)。只有負責人建立、或負責人收件的任務才算授權。"""
    if t['created_by'] == BOSS:
        return True, f'負責人建立 {t["created_at"]}'
    if t['approved_by'] == BOSS:
        return True, f'負責人 {t["approved_at"]} 收件（內容 sha256 前 12 碼 {(t["brief_sha"] or "")[:12]}）'
    return False, f'{NAME_ZH.get(t["created_by"], t["created_by"])} 提案，負責人尚未收件'


def task_dict(c, tid, with_messages=True):
    t = c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
    if not t:
        raise OfficeError(404, f'沒有任務 #{tid}')
    d = dict(t)
    d['status_zh'] = STATUS_ZH.get(d['status'], d['status'])
    d['effective_reviewers'] = effective_reviewers(t)
    d['authorized'], d['authorized_by'] = authorized_by(t)
    revs = c.execute('SELECT * FROM reviews WHERE task_id=? AND delivery_id=? ORDER BY id',
                     (tid, d['delivery_id'] or -1)).fetchall()
    d['reviews'] = [dict(r) for r in revs]
    d['assignment'] = office_assignment.snapshot(c, t)
    d['automation'] = office_automation.snapshot(c, tid)
    d['summary'] = office_summary.snapshot(c, t)
    d['models'] = office_models.snapshot(c, t)
    if with_messages:
        d['messages'] = [dict(m) for m in c.execute('SELECT * FROM messages WHERE task_id=? ORDER BY id', (tid,))]
    return d


def add_msg(c, tid, author, kind, body, ref=None):
    cur = c.execute('INSERT INTO messages(task_id,author,kind,body,ref,created_at) VALUES(?,?,?,?,?,?)',
                    (tid, author, kind, body, ref, now()))
    return cur.lastrowid


def set_status(c, tid, status, **cols):
    sets = ['status=?', 'updated_at=?']; vals = [status, now()]
    for k, v in cols.items():
        sets.append(f'{k}=?'); vals.append(v)
    vals.append(tid)
    c.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)


# ---------- actions ----------
def create_task(actor, title, brief, reviewers=None, team=None):
    team=team or people.team_of(actor) or 'maintenance'
    if team not in people.TEAMS:raise OfficeError(400,'不認識的工作區')
    if actor!='owner' and not people.in_team(actor,team):raise OfficeError(403,'請在自己的工作區提出任務')
    if actor=='gemini':raise OfficeError(403,people.GEMINI_REASON)
    title = (title or '').strip(); brief = brief or ''
    if not title or not brief.strip():
        raise OfficeError(400, '標題與內容都要有')
    if len(title) > 200:
        raise OfficeError(400, '標題太長（200 字內）')
    rv = parse_reviewers(reviewers)
    status = 'inbox' if actor == BOSS else 'proposal'
    with tx() as c:
        cur = c.execute('INSERT INTO tasks(title,brief,status,created_by,reviewers,brief_sha,created_at,updated_at,team,owner) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (title, brief, status, actor, rv, sha(brief), now(), now(),team,people.LIFE_LEAD if team=='life' else None))
        tid = cur.lastrowid
        mid = add_msg(c, tid, actor, 'new', brief)
        if AUTOMATION:
            AUTOMATION.on_human_message(c, c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone(), actor, mid, brief)
        return task_dict(c, tid)


def recompute_review_status(c, t):
    """依本輪交付的複核重算狀態；回傳 (新狀態, 系統訊息或 None)。

    fix 不是「把 reject 改成 pass 就能批准」：補登錄可以，但批准必須來自新的 deliver。
    """
    revs = effective_reviewers(t)
    rows = c.execute('SELECT reviewer,verdict FROM reviews WHERE delivery_id=?', (t['delivery_id'],)).fetchall()
    got = {r['reviewer']: r['verdict'] for r in rows if r['reviewer'] in revs}
    if any(v == 'reject' for v in got.values()):
        return 'fix', f'有人打回，退給 {NAME_ZH.get(t["delivery_by"] or t["owner"], t["delivery_by"] or t["owner"])} 修正（其他複核者仍可補登錄）'
    if t['status'] == 'fix':
        if revs and all(got.get(r) == 'pass' for r in revs):
            return 'fix', '複核意見已更新，但仍須負責人重新交付才能進拍板'
        return 'fix', None
    if revs and all(got.get(r) == 'pass' for r in revs):
        return 'approved', '複核全部通過，等負責人拍板'
    return 'review', None


def act(actor, tid, action, body='', ref=None, verdict=None):
    body = (body or '').strip()
    if ref is not None:
        ref = str(ref).strip() or None
    with tx() as c:
        t = c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
        if not t:
            raise OfficeError(404, f'沒有任務 #{tid}')
        if not people.can_view(actor,t,effective_reviewers(t)):raise OfficeError(403,'你不在這件事的工作區或指定複核名單')
        if actor=='gemini':raise OfficeError(403,people.GEMINI_REASON)
        if people.cross_team(actor,t) and action not in ('say','review'):raise OfficeError(403,'跨區只允許指定複核與意見，不能接管原負責人的工作')
        st = t['status']
        if action in ('claim','deliver','review') and not authorized_by(t)[0]:raise OfficeError(409,'請先由負責人收件')
        is_agent = actor in AGENTS

        if action == 'say':
            if not body:
                raise OfficeError(400, '內容空白')
            mid = add_msg(c, tid, actor, 'say', body, ref)
            if AUTOMATION:
                AUTOMATION.on_human_message(c, t, actor, mid, body)
            if st == 'inbox' and is_agent:
                set_status(c, tid, 'discuss')
            else:
                c.execute('UPDATE tasks SET updated_at=? WHERE id=?', (now(), tid))

        elif action == 'claim':
            assigned=office_assignment.snapshot(c,t)
            if actor not in people.EXECUTION_WORKERS or (assigned['worker'] and assigned['worker']!=actor):
                raise OfficeError(403, '本輪執行人已指定，或此夥伴目前未開放實作')
            if not is_agent:
                raise OfficeError(403, '只有 AI 能認領')
            if st not in ('inbox', 'discuss'):
                raise OfficeError(409, f'狀態是「{STATUS_ZH[st]}」，不能認領')
            if people.task_team(t)!='life' and t['owner'] and t['owner'] != actor:
                raise OfficeError(409, f'已由 {NAME_ZH.get(t["owner"], t["owner"])} 認領；分工請用 say 講清楚')
            add_msg(c, tid, actor, 'claim', body or '我來做')
            set_status(c, tid, 'working', owner=people.LIFE_LEAD if people.task_team(t)=='life' else actor)

        elif action == 'deliver':
            assigned=office_assignment.snapshot(c,t)
            if actor not in people.EXECUTION_WORKERS or (assigned['worker'] and assigned['worker']!=actor):
                raise OfficeError(403, '交付者不符合本輪指定執行人')
            if not is_agent:
                raise OfficeError(403, '只有 AI 能交付')
            if st not in ('inbox', 'discuss', 'working', 'fix'):
                raise OfficeError(409, f'狀態是「{STATUS_ZH[st]}」，不能交付')
            if people.task_team(t)!='life' and t['owner'] and t['owner'] != actor:
                raise OfficeError(409, f'負責人是 {NAME_ZH.get(t["owner"], t["owner"])}，不是你')
            if not body:
                raise OfficeError(400, '交付要寫「做了什麼、證據在哪」')
            probe = dict(t); probe['delivery_by'] = actor
            probe['owner'] = people.LIFE_LEAD if people.task_team(t)=='life' else actor
            revs = effective_reviewers(probe)
            if not revs:
                raise OfficeError(409, '扣掉你自己之後沒有複核者了；請負責人改複核名單或換人交付')
            mid = add_msg(c, tid, actor, 'deliver', body, ref)
            set_status(c, tid, 'review', owner=people.LIFE_LEAD if people.task_team(t)=='life' else actor, delivery_id=mid, delivery_by=actor)
            add_msg(c, tid, 'system', 'system', '等待複核：' + '、'.join(NAME_ZH.get(r, r) for r in revs))

        elif action == 'review':
            if not is_agent:
                raise OfficeError(403, '複核是 AI 之間的事；負責人用「拍板」')
            if st not in ('review', 'fix') or not t['delivery_id']:
                raise OfficeError(409, f'狀態是「{STATUS_ZH[st]}」，現在沒有交付可複核')
            if actor == (t['delivery_by'] or t['owner']):
                raise OfficeError(403, '交付者不能複核自己的交付（自己查自己會放過自己）')
            revs = effective_reviewers(t)
            if actor not in revs:
                raise OfficeError(403, f'你不在複核名單：{", ".join(revs)}')
            if verdict not in ('pass', 'reject'):
                raise OfficeError(400, 'verdict 要是 pass 或 reject')
            if not body:
                raise OfficeError(400, '複核要寫理由（pass 也要寫查了什麼）')
            c.execute('INSERT OR REPLACE INTO reviews(task_id,delivery_id,reviewer,verdict,body,created_at) VALUES(?,?,?,?,?,?)',
                      (tid, t['delivery_id'], actor, verdict, body, now()))
            add_msg(c, tid, actor, 'review', f'[{"通過" if verdict == "pass" else "打回"}] {body}', ref)
            new_st, note = recompute_review_status(c, t)
            if new_st != st:
                set_status(c, tid, new_st)
                if note:
                    add_msg(c, tid, 'system', 'system', note)
            else:
                if note:
                    add_msg(c, tid, 'system', 'system', note)
                c.execute('UPDATE tasks SET updated_at=? WHERE id=?', (now(), tid))

        elif action == 'decide':
            if actor != BOSS:
                raise OfficeError(403, '只有負責人能拍板')
            d = verdict
            if d == 'accept':
                if st != 'proposal':
                    raise OfficeError(409, '只有提案能收件')
                set_status(c, tid, 'inbox', approved_by=BOSS, approved_at=now(), brief_sha=sha(t['brief']))
            elif d == 'active':
                if st != 'approved':
                    raise OfficeError(409, f'狀態是「{STATUS_ZH[st]}」；要複核全過才能正式啟用（想硬過就先 reopen 再走一輪）')
                set_status(c, tid, 'active')
            elif d in ('closed', 'dropped'):
                set_status(c, tid, d)
                c.execute("UPDATE office_jobs SET state='cancelled',stage='任務已關閉，未執行',finished_at=? WHERE task_id=? AND state='queued'", (now(), tid))
            elif d == 'reopen':
                if st not in ('approved', 'active', 'closed', 'dropped', 'review'):
                    raise OfficeError(409, f'狀態是「{STATUS_ZH[st]}」，不用 reopen')
                set_status(c, tid, 'fix' if t['owner'] else 'inbox')
            else:
                raise OfficeError(400, 'decision 要是 accept / active / closed / dropped / reopen')
            mid = add_msg(c, tid, actor, 'decide', f'[{d}] {body}'.strip())
            if AUTOMATION and d in ('accept','reopen'):
                current = c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
                AUTOMATION.on_human_message(c, current, actor, mid, body or '請接續討論這件事，先提出具體範圍、分工與驗收。')
        else:
            raise OfficeError(400, f'不認識的動作 {action}')
        return task_dict(c, tid)


def list_tasks(status=None,actor=BOSS):
    with tx() as c:
        rows = c.execute('SELECT * FROM tasks ORDER BY updated_at DESC').fetchall()
        out = []
        for r in rows:
            if not people.can_view(actor,r,effective_reviewers(r)):continue
            if status and r['status'] != status:
                continue
            d = dict(r); d['status_zh'] = STATUS_ZH[r['status']]
            d['authorized'], d['authorized_by'] = authorized_by(r)
            d['effective_reviewers'] = effective_reviewers(r)
            d['assignment'] = office_assignment.snapshot(c, r)
            if d.get('delivery_id'):
                d['reviews'] = [dict(x) for x in c.execute(
                    'SELECT reviewer,verdict FROM reviews WHERE delivery_id=?', (d['delivery_id'],))]
            else:
                d['reviews'] = []
            states=[x[0] for x in c.execute('SELECT state FROM office_jobs WHERE task_id=?',(r['id'],))]
            d['human_waiting']=[]
            attention_ids=set(office_automation.attention_jobs(c,r['id']))
            for blocked in c.execute("SELECT j.id,j.result,j.trigger_message,coalesce(x.discussion_message,0) AS discussion_message,h.job_id AS responded FROM office_jobs j LEFT JOIN office_controls x ON x.task_id=j.task_id LEFT JOIN office_human_responses h ON h.job_id=j.id WHERE j.task_id=? AND j.state='blocked'",(r['id'],)):
                if blocked['id'] in attention_ids and not blocked['responded'] and blocked['discussion_message']<=(blocked['trigger_message'] or 0):
                    actions=json.loads(blocked['result'] or '{}').get('user_actions',[])
                    if actions:d['human_waiting'].append({'id':blocked['id'],'user_actions':actions})
            if states:
                current='running' if 'running' in states else 'queued' if 'queued' in states else 'failed' if office_automation.attention_jobs(c,r['id']) else 'idle'
                if current=='failed':
                    attention=set(office_automation.attention_jobs(c,r['id']))
                    if any(j['id'] in attention and json.loads(j['result'] or '{}').get('blockers') for j in c.execute("SELECT id,result FROM office_jobs WHERE task_id=? AND state='blocked'",(r['id'],))):current='blocked'
                d['work_status']={'state':current,'count':states.count(current) if current in ('running','queued') else 1}
            out.append(people.public_task(d,actor))
        return out


def inbox_for(agent):
    """agent 待處理清單。"""
    out = []
    if agent=='gemini':return out
    with tx() as c:
        for t in c.execute('SELECT * FROM tasks ORDER BY updated_at DESC').fetchall():
            if not people.can_view(agent,t,effective_reviewers(t)):continue
            if people.cross_team(agent,t) and t['status'] not in ('review','fix'):continue
            st = t['status']
            mine = c.execute('SELECT MAX(id) FROM messages WHERE task_id=? AND author=?', (t['id'], agent)).fetchone()[0]
            why = None
            if agent == BOSS:
                if st == 'approved': why = '複核全過，等妳拍板'
                elif st == 'proposal': why = 'AI 提案，要不要收件'
            else:
                if st in ('inbox', 'discuss') and mine is None:
                    why = '新任務，還沒發言／認領'
                elif st in ('review', 'fix') and (t['delivery_by'] or t['owner']) != agent and agent in effective_reviewers(t) and t['delivery_id']:
                    r = c.execute('SELECT 1 FROM reviews WHERE delivery_id=? AND reviewer=?', (t['delivery_id'], agent)).fetchone()
                    if not r:
                        why = '等你複核' if st == 'review' else '已有人打回，你的複核仍可補登錄'
                if why is None and st == 'fix' and (t['delivery_by'] or t['owner']) == agent:
                    why = '被打回，要修正後重新交付'
                elif why is None and st == 'working' and t['owner'] == agent:
                    why = '你認領中，記得交付'
            if why is None and st not in ('closed', 'dropped'):
                m = c.execute('SELECT id FROM messages WHERE task_id=? AND id>? AND body LIKE ? AND author!=?',
                              (t['id'], mine or 0, f'%@{agent}%', agent)).fetchone()
                if m: why = '有人點名你'
            if why:
                d = dict(t); d['why'] = why; d['status_zh'] = STATUS_ZH[st]
                d['authorized'], d['authorized_by'] = authorized_by(t)
                out.append(people.public_task(d,agent))
    return out


# ---------- http ----------
def esc(s):
    return html.escape('' if s is None else str(s))


def zh(n):
    return esc(NAME_ZH.get(n, n) if n else '—')


def ago(ts):
    try:
        dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
        sec = int((datetime.now(TZ) - dt).total_seconds())
    except (TypeError, ValueError):
        return esc(ts)
    if sec < 45:
        return '剛剛'
    if sec < 3600:
        return f'{max(1, sec // 60)} 分鐘前'
    if sec < 86400:
        return f'{sec // 3600} 小時前'
    if sec < 86400 * 7:
        return f'{sec // 86400} 天前'
    return esc(ts[5:16])


def review_chips_html(t):
    if not t.get('delivery_id'):
        return ''
    got = {r['reviewer']: r for r in t.get('reviews') or []}
    chips = []
    for r in t.get('effective_reviewers') or []:
        if r in got:
            v = got[r]['verdict']
            lab, cls = ('通過', 'pass') if v == 'pass' else ('打回', 'reject')
        else:
            lab, cls = '未複核', 'wait'
        chips.append(f'<span class="chip {cls}">{zh(r)} {esc(lab)}</span>')
    return '<div class="chips">' + ''.join(chips) + '</div>' if chips else ''


CSS = '''
:root{--bg:#f3efe6;--ink:#1c1917;--muted:#6b635b;--card:#fffcf7;--line:#e4ddd2;--accent:#0f766e;--ok:#3f6b3a;--warn:#a33b2b}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);background:var(--bg);font-family:system-ui,"Noto Sans CJK TC","Noto Sans TC",sans-serif;line-height:1.55}
a{color:var(--accent)}a:hover{color:#115e59}
.wrap{max-width:980px;margin:0 auto;padding:0 1.1rem 2.4rem}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;padding:1rem 0 .85rem;border-bottom:1px solid var(--line);margin-bottom:1.15rem}
.brand{font-size:1.12rem;font-weight:700;text-decoration:none;color:inherit}
.who{color:var(--muted);font-size:.9rem;white-space:nowrap}
h2{font-size:1.22rem;margin:.15rem 0 .55rem;line-height:1.35}
.st{display:inline-block;padding:.12rem .55rem;border-radius:999px;background:#e8e4dc;font-size:.78em;font-weight:650}
.st-review,.st-fix{background:#fde68a}.st-approved{background:#bbf7d0}.st-active{background:#bae6fd}
.st-inbox,.st-discuss,.st-working{background:#fef08a}.st-proposal{background:#e7e5e4}.st-closed,.st-dropped{background:#e7e5e4;color:#57534e}
.meta{color:var(--muted);font-size:.86rem}
.warn{color:var(--warn)}.ok{color:var(--ok)}
.todo{background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:.75rem 1rem;margin:0 0 1rem}
.todo ul{margin:.35rem 0 0;padding-left:1.1rem}
.nav{display:flex;flex-wrap:wrap;gap:.35rem .85rem;margin:0 0 1rem;font-size:.9rem}
.nav a.on{font-weight:700;color:var(--ink);text-decoration:none}
.sec{margin:1.15rem 0 .45rem;font-size:.95rem}
.sticky{position:sticky;top:0;z-index:3;background:var(--bg);padding:.4rem 0 .1rem}
.cards{display:grid;gap:.65rem}
.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.8rem 1rem;text-decoration:none;color:inherit}
.card:hover{border-color:#c9c1b4}
.card .t{font-weight:650;margin:.2rem 0 .15rem}
.row{display:flex;justify-content:space-between;align-items:center;gap:.5rem;flex-wrap:wrap}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.85rem 1rem;margin:.7rem 0}
.chips{display:flex;flex-wrap:wrap;gap:.35rem .6rem;margin:.4rem 0 .2rem}
.chip{background:#e8e4dc;border-radius:999px;padding:.12rem .6rem;font-size:.82rem}
.chip.pass{background:#dcfce7}.chip.reject{background:#fee2e2}.chip.wait{background:#fef9c3}
.msg{border-left:3px solid #d6d3d1;padding:.45rem .85rem;margin:.55rem 0;background:var(--card);border-radius:0 10px 10px 0}
.msg.k-deliver{border-color:#0f766e}.msg.k-review{border-color:#c2410c}
.msg.k-decide{border-color:#3f6b3a}.msg.k-system{border-color:#a8a29e;color:var(--muted);font-size:.92em}
pre{white-space:pre-wrap;word-break:break-word;margin:.35rem 0;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.92em}
form{margin:.75rem 0;padding:.85rem 1rem;background:var(--card);border:1px solid var(--line);border-radius:12px}
label{display:block;font-weight:650;margin-bottom:.35rem}
input[type=text],input[type=password],textarea,select{width:100%;box-sizing:border-box;font:inherit;padding:.45rem .55rem;border:1px solid #d6d3d1;border-radius:8px;background:#fff;margin:.15rem 0 .45rem}
.actions{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
button{font:inherit;padding:.4rem 1rem;border:0;border-radius:8px;background:#e7e5e4;cursor:pointer}
button.primary{background:var(--accent);color:#fff}
.foot{color:var(--muted);font-size:.8rem;margin-top:1.6rem;padding-top:.7rem;border-top:1px solid var(--line)}
'''


def page(title, body, me=None):
    who = f'你是：{zh(me)} · <a href="/logout">登出</a>' if me else '訪客（只能看）· <a href="/login">登入</a>'
    return (f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style><div class="wrap">'
            f'<header class="top"><a class="brand" href="/">AI 協作辦公室</a><div class="who">{who}</div></header>'
            f'{body}<p class="foot">v{VERSION} · 只綁 tailnet · 規則由程式強制</p></div>')


class Handler(BaseHTTPRequestHandler):
    tokens = {}
    server_version = f'office/{VERSION}'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s %s\n' % (now(), self.client_address[0], fmt % args))

    # -- auth --
    def cookie_token(self):
        for part in self.headers.get('Cookie', '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == COOKIE and v:
                return v
        return None

    def who(self, web=False):
        """API：一律 Bearer。網頁：cookie 裡的 token；沒有就是訪客（None）。不再拿來源位址當身分。"""
        if web and SSO:
            if SSO.trusted(self):
                import hmac
                binding = SSO.owner_uid + ':' + self.headers.get('Cookie', '')
                self._csrf = hmac.new(SSO_CSRF_KEY, binding.encode(), 'sha256').hexdigest()
                return BOSS
            return None
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            name = self.tokens.get(sha(auth[7:].strip()))
            if not name:
                raise OfficeError(401, 'token 不對')
            return name
        if web:
            tok = self.cookie_token()
            if tok:
                name = self.tokens.get(sha(tok))
                if name:
                    self._csrf = sha('csrf:' + tok)[:32]
                    return name
            return None
        raise OfficeError(401, '需要 Bearer token')

    def need_login(self):
        me = self.who(web=True)
        if not me:
            raise OfficeError(401, '要先登入（右上角）才能在網頁上操作')
        return me

    def check_csrf(self, p):
        expected = getattr(self, '_csrf', None)
        if not expected or p.get('csrf') != expected:
            raise OfficeError(403, '表單驗證失敗（CSRF），請重新整理再送一次')

    # -- io --
    def send(self, code, body, ctype='text/html; charset=utf-8', extra=None):
        data = body.encode() if isinstance(body, str) else body
        extra = dict(extra or {})
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        # 成果預覽自帶更嚴格的沙箱政策；其他回應一律用站台政策（只允許嵌入本站的預覽頁）。
        self.send_header('Content-Security-Policy', extra.pop('Content-Security-Policy', SITE_CSP))
        self.send_header('Referrer-Policy', 'no-referrer')
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, code, obj):
        self.send(code, json.dumps(obj, ensure_ascii=False, indent=1), 'application/json; charset=utf-8')

    def read_body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 2_000_000:
            raise OfficeError(413, '內容太大')
        raw = self.rfile.read(n) if n else b''
        ct = self.headers.get('Content-Type', '')
        if ct.startswith('application/json'):
            try:
                d = json.loads(raw.decode() or '{}')
            except json.JSONDecodeError as e:
                raise OfficeError(400, f'JSON 壞了：{e}')
            if not isinstance(d, dict):
                raise OfficeError(400, 'JSON 要是物件')
            return d
        return {k: v[0] for k, v in parse_qs(raw.decode(), keep_blank_values=True).items()}

    def sso_gate(self):
        if not SSO:
            return True
        path = urlparse(self.path).path
        if path.startswith('/api/'):
            self.who()
            return True
        if SSO.trusted(self):
            if self.command not in ('GET', 'HEAD') and not SSO.same_origin(self):
                raise OfficeError(403, '網頁來源驗證失敗')
            return True
        return SSO.reject(self)

    # -- routes --
    def do_GET(self):
        try:
            if not self.sso_gate():
                return
            u = urlparse(self.path); q = parse_qs(u.query)
            assets = {'/models.js': ('models.js', 'text/javascript; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8'),
                      '/mark.svg': ('mark.svg', 'image/svg+xml')}
            for who in ('claude', 'codex', 'grok', 'assistant', 'gemini'):
                for size in (96, 192):
                    filename = f'avatars/{who}-{size}.webp'
                    assets['/' + filename] = (filename, 'image/webp')
            if u.path in assets:
                filename, content_type = assets[u.path]
                return self.send(200, (WEB_DIR / filename).read_bytes(), content_type)
            if u.path in ('/', '/login', '/new') or re.fullmatch(r'/t/[1-9][0-9]*', u.path):
                return self.send(200, frontend_page())
            if u.path.startswith('/web/') and u.path not in ('/web/session','/web/overview'):
                self.need_login()
            if u.path == '/web/executions':
                return self.send_json(200, execution_snapshot(Path(DATA_DIR) / 'executions'))
            if u.path == '/web/capacity':
                return self.send_json(200, capacity())
            if u.path in ('/web/session', '/web/overview'):
                me = self.who(web=True)
                session = {'name': me, 'csrf': getattr(self, '_csrf', '') if me else ''}
                if u.path == '/web/session':
                    return self.send_json(200, session)
                return self.send_json(200, {'tasks': list_tasks(actor=me), 'members':people.roster(), 'teams':people.TEAMS, 'session': session,
                                           'fetched_at': datetime.now(TZ).isoformat(), 'read_only': not bool(me), 'frontend_build': frontend_build(), 'settings': {'title':CONFIG['title'],'owner_name':CONFIG['owner_name'],'timezone':CONFIG['timezone'],'automation':CONFIG['automation'],'life_lead':people.LIFE_LEAD}})
            web_task = re.fullmatch(r'/web/tasks/([1-9][0-9]*)', u.path)
            artifact = re.fullmatch(r'/web/tasks/([1-9][0-9]*)/deliveries/([1-9][0-9]*)/(report|(files|preview)/([0-9]+))',u.path)
            if artifact:
                actor=self.need_login();tid=int(artifact[1])
                with tx() as c:
                    task=task_dict(c,tid)
                    if not people.can_view(actor,task,effective_reviewers(task)):raise OfficeError(403,'此成果未分享給你')
                    delivery=handover.snapshot(c,tid)
                    if not delivery or delivery['delivery_id']!=int(artifact[2]):raise OfficeError(409,'交付已更新，請重新檢視目前版本')
                if artifact[3]=='report':
                    data=delivery['report'].encode('utf-8');filename=f'office-{tid}-delivery-{artifact[2]}.txt'
                else:
                    index=int(artifact[5]);items=delivery['artifacts']
                    if not delivery['job_id'] or index>=len(items):raise OfficeError(404,'這版沒有此成果檔案')
                    preview_type=PREVIEW_TYPES.get(Path(items[index]['name']).suffix.lower())
                    if artifact[4]=='preview' and not preview_type:raise OfficeError(415,'這類檔案不提供網頁預覽，請下載或展開文字')
                    if artifact[4]=='preview' and self.headers.get('Sec-Fetch-Dest')!=PREVIEW_DEST[Path(items[index]['name']).suffix.lower()]:
                        raise OfficeError(403,'成果預覽只在任務頁內顯示，不能直接開啟；請用下載')
                    try:data=handover.read_artifact(DATA_DIR,delivery['job_id'],index,items[index])
                    except (ValueError,OSError):raise OfficeError(409,'交付檔案與固定版本不符，請先核對')
                    filename=Path(items[index]['name']).name
                    if artifact[4]=='preview':
                        return self.send(200,data,preview_type,{'Content-Security-Policy':PREVIEW_CSP,'Cross-Origin-Resource-Policy':'same-origin','X-DNS-Prefetch-Control':'off'})
                return self.send(200,data,'text/plain; charset=utf-8',{'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename,safe='')})
            if web_task:
                with tx() as c:
                    payload = task_dict(c, int(web_task[1]));actor=self.who(web=True)
                    if not people.can_view(actor,payload,effective_reviewers(payload)):raise OfficeError(403,'此任務未分享給你')
                    payload=people.public_task(payload,actor)
                return self.send_json(200, payload)
            if u.path in ('/api/notifications', '/web/notifications'):
                actor = self.who(web=u.path.startswith('/web/'))
                if actor not in (BOSS, 'codex'):
                    raise OfficeError(403, '通知狀態僅限負責人與Codex')
                return self.send_json(200, NOTICES.status() if NOTICES else {'enabled': False, 'error_code': 'not_started'})
            if u.path in ('/health', '/api/health'):
                return self.send_json(200, {'ok': True, 'version': VERSION, 'time': now()})
            if u.path == '/api/whoami':
                return self.send_json(200, {'name': self.who()})
            if u.path == '/api/tasks':
                return self.send_json(200, list_tasks(q.get('status', [None])[0],self.who()))
            m = re.fullmatch(r'/api/tasks/(\d+)', u.path)
            if m:
                actor=self.who()
                with tx() as c:
                    payload = task_dict(c, int(m.group(1)))
                    if not people.can_view(actor,payload,effective_reviewers(payload)):raise OfficeError(403,'此任務未分享給你')
                    payload=people.public_task(payload,actor)
                return self.send_json(200, payload)
            if u.path == '/api/inbox':
                return self.send_json(200, inbox_for(self.who()))
            if u.path == '/login':
                return self.send(200, page('登入', self.html_login(), self.who(web=True)))
            if u.path == '/logout':
                return self.send(303, '', extra={'Location': '/', 'Set-Cookie': f'{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
            if u.path == '/':
                st = q.get('status', [None])[0]
                if st and st not in STATUSES:
                    st = None
                return self.send(200, self.html_index(self.who(web=True), st))
            m = re.fullmatch(r'/t/(\d+)', u.path)
            if m:
                return self.send(200, self.html_task(self.who(web=True), int(m.group(1))))
            raise OfficeError(404, '沒這頁')
        except OfficeError as e:
            self.fail(e)

    def do_POST(self):
        try:
            u = urlparse(self.path)
            if u.path=='/internal/approved-step':
                import office_execution
                if self.headers.get('Origin'):raise OfficeError(403,'核准步驟只供本輪工作者使用')
                p=self.read_body()
                try:reply=office_execution.execute(sys.modules[__name__],p.get('job_id'),p.get('step_id'),p.get('token'),p.get('workspace'))
                except ValueError as error:raise OfficeError(409,'此步驟未執行：'+str(error)) from None
                except (KeyError,FileNotFoundError):raise OfficeError(409,'此步驟未執行：請核對計畫、本輪身分與前一步結果') from None
                return self.send_json(200,reply)
            if not self.sso_gate():return
            if u.path.startswith('/web/'):
                p = self.read_body()
                if u.path == '/web/login':
                    if SSO:
                        raise OfficeError(400, '此入口使用 Authentik 登入')
                    tok = (p.get('token') or '').strip()
                    name = self.tokens.get(sha(tok)) if tok else None
                    if not name:
                        raise OfficeError(401, '登入碼不正確，請確認後再試')
                    cookie = f'{COOKIE}={tok}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Strict'
                    return self.send(200, json.dumps({'ok': True}), 'application/json; charset=utf-8', {'Set-Cookie': cookie})
                actor = self.need_login()
                self.check_csrf(p)
                if u.path == '/web/logout':
                    if SSO:
                        return self.send_json(200, {'ok': True, 'redirect': SSO.origin + '/outpost.goauthentik.io/sign_out'})
                    return self.send(200, json.dumps({'ok': True}), 'application/json; charset=utf-8',
                                     {'Set-Cookie': f'{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
                if u.path == '/web/models/refresh':
                    if actor != BOSS:raise OfficeError(403,'只有負責人能要求更新模型清單')
                    office_models.refresh_catalog(force=True)
                    return self.send_json(200, {'ok': True, 'refreshing': True})
                if u.path == '/web/tasks':
                    return self.send_json(201, create_task(actor, p.get('title', ''), p.get('brief', ''), p.get('reviewers') or None,p.get('team')))
                control = re.fullmatch(r'/web/tasks/([1-9][0-9]*)/control', u.path)
                if control:
                    if p.get('action')=='models':
                        with tx() as c:
                            task=c.execute('SELECT * FROM tasks WHERE id=?',(int(control[1]),)).fetchone()
                            if not task:raise OfficeError(404,'工作單不存在')
                            office_models.save(sys.modules[__name__],c,task,p.get('model_settings'),actor)
                            result=task_dict(c,task['id'])
                        return self.send_json(200,result)
                    if p.get('action')=='summarize':
                        if actor!=BOSS:raise OfficeError(403,'只有負責人可指定主責總結')
                        with tx() as c:
                            task=c.execute('SELECT * FROM tasks WHERE id=?',(int(control[1]),)).fetchone()
                            if not task:raise OfficeError(404,'工作單不存在')
                            office_summary.request(sys.modules[__name__],c,task,p.get('summary_owner'),retry=True)
                            result=task_dict(c,task['id'])
                        return self.send_json(200,result)
                    if not AUTOMATION:
                        raise OfficeError(503, '接單服務尚未啟動')
                    return self.send_json(200, AUTOMATION.control(actor, int(control[1]), p.get('action'), p.get('body', ''), p.get('plan_id'), p.get('request_id'),p.get('target_id'),p.get('checked'),p.get('assignment'),p.get('accept_proposal',False),p.get('files')))
                web_action = re.fullmatch(r'/web/tasks/([1-9][0-9]*)/(say|decide)', u.path)
                if web_action:
                    return self.send_json(200, act(actor, int(web_action[1]), web_action[2], p.get('body', ''), None, p.get('decision')))
                raise OfficeError(404, '沒有這個網頁操作')
            if u.path.startswith('/api/'):
                actor = self.who()
                p = self.read_body()
                if u.path == '/api/tasks':
                    return self.send_json(201, create_task(actor, p.get('title', ''), p.get('brief', ''), p.get('reviewers'),p.get('team')))
                m = re.fullmatch(r'/api/tasks/(\d+)/(say|claim|deliver|review|decide)', u.path)
                if m:
                    return self.send_json(200, act(actor, int(m.group(1)), m.group(2), p.get('body', ''), p.get('ref'), p.get('verdict') or p.get('decision')))
                raise OfficeError(404, '沒這個 API')
            p = self.read_body()
            if u.path == '/login':
                tok = (p.get('token') or '').strip()
                name = self.tokens.get(sha(tok)) if tok else None
                if not name:
                    raise OfficeError(401, 'token 不對')
                cookie = f'{COOKIE}={tok}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Strict'
                return self.send(303, '', extra={'Location': '/', 'Set-Cookie': cookie})
            actor = self.need_login()
            self.check_csrf(p)
            if u.path == '/new':
                t = create_task(actor, p.get('title', ''), p.get('brief', ''), p.get('reviewers') or None)
                return self.send(303, '', extra={'Location': f'/t/{t["id"]}'})
            m = re.fullmatch(r'/t/(\d+)/(say|decide)', u.path)
            if m:
                tid = int(m.group(1))
                act(actor, tid, m.group(2), p.get('body', ''), None, p.get('decision'))
                return self.send(303, '', extra={'Location': f'/t/{tid}'})
            raise OfficeError(404, '沒這頁')
        except OfficeError as e:
            self.fail(e)

    def fail(self, e):
        if self.path.startswith(('/api/', '/web/','/internal/')):
            self.send_json(e.code, {'error': e.msg, 'code': e.code})
        else:
            me = None
            try:
                me = self.who(web=True)
            except OfficeError:
                pass
            self.send(e.code, page('錯誤', f'<p class="warn">{esc(e.msg)}</p><p><a href="/">回首頁</a></p>', me))

    # -- html --
    def csrf_field(self):
        return f'<input type="hidden" name="csrf" value="{esc(getattr(self, "_csrf", ""))}">'

    def html_login(self):
        return ('<form method="post" action="/login"><label>登入</label>'
                '<p class="meta">貼上自己的 token。登入碼由本機資料目錄的 <code>secrets/owner.tok</code> 取得；請用編輯器開啟，不要貼進指令或日誌。存成 HttpOnly cookie，30 天。</p>'
                '<input type="password" name="token" autocomplete="off" required>'
                '<div class="actions"><button class="primary" type="submit">登入</button></div></form>')

    def html_index(self, me, status=None):
        rows = list_tasks(status)
        order = ['approved', 'review', 'fix', 'working', 'discuss', 'inbox', 'proposal', 'active', 'closed', 'dropped']
        labels = {'approved': '等拍板', 'review': '複核中', 'fix': '修正中', 'working': '實作中',
                  'discuss': '討論中', 'inbox': '收件', 'proposal': '提案', 'active': '已啟用',
                  'closed': '結案', 'dropped': '作廢'}
        todo = ''
        if me:
            items = inbox_for(me)
            if items:
                lis = ''.join(
                    f'<li><a href="/t/{x["id"]}">#{x["id"]} {esc(x["title"])}</a> <span class="meta">— {esc(x["why"])}</span></li>'
                    for x in items)
                todo = f'<section class="todo"><b>待你處理</b><ul>{lis}</ul></section>'
        all_on = ' class="on"' if not status else ''
        nav_bits = [f'<a href="/"{all_on}>全部</a>']
        for s in order:
            on = ' class="on"' if status == s else ''
            nav_bits.append(f'<a href="/?status={s}"{on}>{esc(labels[s])}</a>')
        nav = '<nav class="nav">' + ' '.join(nav_bits) + '</nav>'

        def card(r):
            return (f'<a class="card" href="/t/{r["id"]}"><div class="row"><span class="meta">#{r["id"]}</span>'
                    f'<span class="st st-{esc(r["status"])}">{esc(r["status_zh"])}</span></div>'
                    f'<div class="t">{esc(r["title"])}</div>'
                    f'{review_chips_html(r)}'
                    f'<div class="meta">負責：{zh(r["owner"])} · {ago(r["updated_at"])}'
                    + ('' if r['authorized'] else ' · 未授權提案') + '</div></a>')

        if not rows:
            body_cards = '<p class="meta">這個篩選底下沒有任務。</p>' if status else '<p class="meta">還沒有任務</p>'
        elif status:
            body_cards = '<div class="cards">' + ''.join(card(r) for r in rows) + '</div>'
        else:
            chunks = []
            by = {}
            for r in rows:
                by.setdefault(r['status'], []).append(r)
            for s in order:
                grp = by.get(s)
                if not grp:
                    continue
                chunks.append(f'<h2 class="sec">{esc(labels[s])}</h2><div class="cards">' + ''.join(card(r) for r in grp) + '</div>')
            body_cards = ''.join(chunks)
        form = ''
        if me:
            hint = '建立者記成負責人＝授權來源' if me == BOSS else 'AI 建的是提案，要負責人收件才算授權'
            form = (f'<form method="post" action="/new">{self.csrf_field()}<label>丟一件事進來</label>'
                    '<input type="text" name="title" placeholder="標題（一句話）" required>'
                    '<textarea name="brief" rows="5" placeholder="要做什麼、什麼叫做好（驗收條件）" required></textarea>'
                    '<input type="text" name="reviewers" placeholder="複核者（可空＝除交付者外全部；例：codex,grok）">'
                    f'<div class="actions"><button class="primary" type="submit">丟進去</button> <span class="meta">{hint}</span></div></form>')
        return page('AI 協作辦公室', todo + nav + form + body_cards, me)

    def html_task(self, me, tid):
        with tx() as c:
            t = task_dict(c, tid)
        msgs = ''.join(
            f'<div class="msg k-{esc(m["kind"])}"><div class="meta">{zh(m["author"])} · {esc(KIND_ZH.get(m["kind"], m["kind"]))} · {esc(m["created_at"])}（{ago(m["created_at"])}）'
            + (f' · 附：<code>{esc(m["ref"])}</code>' if m.get('ref') else '') + f'</div><pre>{esc(m["body"])}</pre></div>'
            for m in t['messages'] if m['kind'] != 'new')
        revs = review_chips_html(t)
        forms = ''
        if me:
            forms = (f'<div class="sticky"><form method="post" action="/t/{tid}/say">{self.csrf_field()}<label>留言</label>'
                     '<textarea name="body" rows="3" required></textarea>'
                     '<div class="actions"><button class="primary" type="submit">送出</button></div></form>')
            if me == BOSS:
                opts = ''.join(f'<option value="{k}">{v}</option>' for k, v in
                               [('active', '正式啟用（要複核全過）'), ('accept', '提案收件'), ('reopen', '重開／打回再修'), ('closed', '結案'), ('dropped', '作廢')])
                forms += (f'<form method="post" action="/t/{tid}/decide">{self.csrf_field()}<label>拍板</label>'
                          f'<select name="decision">{opts}</select>'
                          f'<input type="text" name="body" placeholder="一句話（可空）">'
                          f'<div class="actions"><button class="primary" type="submit">拍板</button></div></form>')
            forms += '</div>'
        auth_cls = 'ok' if t['authorized'] else 'warn'
        head = (f'<div class="row"><h2>#{tid} {esc(t["title"])}</h2><span class="st st-{esc(t["status"])}">{esc(t["status_zh"])}</span></div>'
                f'<p class="meta">建立：{zh(t["created_by"])} {esc(t["created_at"])} · 負責：{zh(t["owner"])}'
                f' · 複核者：{"、".join(zh(r) for r in t["effective_reviewers"])} · <span class="{auth_cls}">授權：{esc(t["authorized_by"])}</span></p>'
                f'{revs}<div class="panel"><pre>{esc(t["brief"])}</pre></div>')
        trail = f'<h2>時間軸</h2>{msgs}' if msgs else '<p class="meta">還沒有留言。</p>'
        return page(f'#{tid} {t["title"]}', head + forms + trail, me)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    freebind = False

    def server_bind(self):
        if self.freebind:
            # tailnet 位址可能開機後幾秒才掛上；IP_FREEBIND 讓綁定不必等它出現（跟監控板同招）
            self.socket.setsockopt(socket.IPPROTO_IP, getattr(socket, 'IP_FREEBIND', 15), 1)
        super().server_bind()


def main():
    global AUTOMATION, NOTICES
    os.umask(0o077)
    ap = argparse.ArgumentParser(description='AI 協作辦公室中樞')
    ap.add_argument('--sso-config', type=Path, default=os.environ.get('OFFICE_SSO_CONFIG'))
    ap.add_argument('--notification-config', type=Path, default=os.environ.get('OFFICE_NOTIFICATION_CONFIG', str(CONFIG_DATA_DIR/'notification.json')))
    ap.add_argument('--bind', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=9870)
    ap.add_argument('--allow-network', action='store_true', help='非 127.0.0.1 要明確給這個旗標，且只准 tailnet 位址')
    a = ap.parse_args()
    if a.bind != '127.0.0.1':
        if not a.allow_network:
            ap.error('非本機入口要明確指定 --allow-network')
        address=ipaddress.ip_address(a.bind)
        if address.is_global and address not in TAILNET:
            ap.error('此測試版只允許本機、私有或 tailnet 位址；公開存取請經自己的 HTTPS 代理')
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    lock_fh = open(os.path.join(DATA_DIR, '.lock'), 'w')
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit('已有另一個中樞行程在用這個資料目錄，不重複起')
    if CONFIG['model_discovery']: office_models.start_catalog_refresh()
    init_db()
    Handler.tokens = load_tokens()
    global SSO, SSO_CSRF_KEY
    from owner_proxy import OwnerProxy
    SSO = OwnerProxy.from_file(a.sso_config) if a.sso_config else None
    if SSO:
        SSO_CSRF_KEY = (Path(SECRET_DIR) / (BOSS + '.tok')).read_bytes().strip()
    Server.freebind = False
    srv = Server((a.bind, a.port), Handler)
    global EXECUTION_URL
    EXECUTION_URL = 'http://' + ('127.0.0.1' if a.bind=='0.0.0.0' else a.bind) + ':' + str(srv.server_port) + '/internal/approved-step'
    AUTOMATION = office_automation.Automation(sys.modules[__name__])
    if CONFIG['automation']: AUTOMATION.start()
    import office_notifications
    NOTICES = office_notifications.Notices(sys.modules[__name__], config_path=a.notification_config)
    NOTICES.start()
    sys.stderr.write(f'{now()} office 中樞 v{VERSION} 啟動 http://{a.bind}:{a.port}  身分數={len(Handler.tokens)}  db={DB_PATH}\n')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        AUTOMATION.stop.set()
        if NOTICES: NOTICES.stop.set()
        srv.server_close()


if __name__ == '__main__':
    main()
