"""AI 協作辦公室：office_notifications。"""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from office_config import CONFIG as SETTINGS, DATA_DIR
CONFIG = DATA_DIR/'notification.json'
PUBLIC_URL = SETTINGS['public_url'].rstrip('/')
NAMES = {'codex': 'Codex', 'claude': 'Claude', 'assistant': '助理', 'grok': 'Grok'}
LABELS = {'decision': '待你決定', 'human': '待你操作', 'acceptance': '可以驗收', 'blocked': '工作受阻', 'connected': '通知已啟用'}


def now():
    return datetime.now(ZoneInfo(__import__('office_config').CONFIG['timezone'])).isoformat()


def load_config(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('通知憑證owner或mode不符')
    value = json.loads(path.read_text())
    if set(value) != {'token', 'chat_id', 'bot_username'}:
        raise ValueError('通知憑證欄位不符')
    if not isinstance(value['token'], str) or not re.fullmatch(r'\d{5,}:[A-Za-z0-9_-]{25,}', value['token']):
        raise ValueError('Bot憑證格式不符')
    if type(value['chat_id']) is not int or value['chat_id'] <= 0:
        raise ValueError('通知限固定私人收件者')
    if not isinstance(value['bot_username'], str) or not re.fullmatch(r'[A-Za-z0-9_]{5,32}', value['bot_username']):
        raise ValueError('Bot名稱格式不符')
    return value


def event(key, tid, kind, reason):
    # 只發程式定義的摘要；工作單、來源、日誌及AI自由文字留在有登入保護的網頁。
    return {'key': key, 'task_id': tid, 'kind': kind,
            'text': f'{tid:03d}｜{LABELS[kind]}\n{reason}\n請開啟工作單查看原因與下一步。',
            'url': PUBLIC_URL + f'/t/{tid}'+{'human':'#human-actions','acceptance':'#results','blocked':'#missing-items','decision':'#next-step'}.get(kind,'')}


def task_events(task, auto):
    if not task.get('authorized') or task.get('status') in ('proposal', 'closed', 'dropped'):
        return []
    tid = int(task['id'])
    jobs = auto.get('jobs', [])
    attention = set(auto.get('attention_job_ids', []))
    current = [j for j in jobs if j['id'] in attention and not j.get('superseded') and not j.get('human_obsolete') and not j.get('retry_job_id')]
    actions = [j for j in current if j['state'] == 'blocked' and j.get('user_actions') and not j.get('human_response') and not j.get('human_obsolete')]
    result = []
    for job in actions:
        worker = NAMES.get(job['worker'], '主責夥伴')
        count = len(job['user_actions'])
        result.append(event(f"human:{tid}:{job['id']}", tid, 'human', f'{worker}有 {count} 項需要你本人處理的操作；包含登入、補資料、確認或人工簽署時，請依操作卡完成。'))
    in_flight = any(j['state'] in ('queued', 'running') for j in jobs)
    delivery = auto.get('delivery')
    accepted = bool(delivery and delivery.get('acceptance') and delivery['acceptance'].get('decision') == 'accepted')
    if task['status'] == 'approved' and delivery and not accepted and not current and not in_flight:
        result.append(event(f"acceptance:{tid}:{delivery['delivery_id']}", tid, 'acceptance', '本版成果已通過夥伴複核；請查看成果、證據與限制，再驗收通過或要求修正。'))
    plans = auto.get('plans', [])
    if auto.get('start_ready') and plans and plans[0].get('status') == 'draft':
        plan = plans[0]
        result.append(event(f"decision:{tid}:{plan['id']}", tid, 'decision', '最新動工計畫已整理好；請核對範圍、分工與驗收方式，再決定是否開始。'))
    if not actions and not in_flight:
        blocked = [j for j in current if j['state'] in ('failed', 'blocked') and not j.get('human_response')]
        if blocked:
            round_id = max(j.get('trigger_message') or 0 for j in blocked)
            workers = '、'.join(dict.fromkeys(NAMES.get(j['worker'], '主責夥伴') for j in blocked))
            result.append(event(f'blocked:{tid}:{round_id}', tid, 'blocked', f'{workers}的 {len(blocked)} 項工作尚有卡點，目前沒有接續工作在跑；由主責核對原因與補件，不代表需要你自行修復。'))
    repairs=auto.get('repairs',[])
    if repairs and repairs[0].get('state')=='needs_more' and not in_flight:
        repair=repairs[0]
        result.append(event(f'repair:{tid}:{repair["id"]}',tid,'blocked','這次核對仍有必要資料待負責夥伴取得；請查看原因與處理進度，有額外資料時才需補交。'))
    return result


def collect(office):
    result = []
    import office_automation
    with office.tx() as c:
        for row in c.execute("SELECT * FROM tasks WHERE status NOT IN ('proposal','closed','dropped') ORDER BY id").fetchall():
            task = dict(row)
            task['authorized'] = office.authorized_by(row)[0]
            result.extend(task_events(task, office_automation.snapshot(c, row['id'])))
    return result


class Telegram:
    def __init__(self, config_path=CONFIG, opener=None):
        self.path = Path(config_path)
        self.opener = opener or urllib.request.urlopen

    def send(self, notice):
        try:
            config = load_config(self.path)
        except Exception:
            return {'state': 'blocked', 'code': 'credential_invalid'}
        payload = {'chat_id': config['chat_id'], 'text': notice['text'],
                   'link_preview_options': {'is_disabled': True},
                   'reply_markup': {'inline_keyboard': [[{'text': '開啟AI 協作辦公室' if notice['task_id'] == 0 else f"查看 {notice['task_id']:03d} 工作單", 'url': notice['url']}]]}}
        request = urllib.request.Request('https://api.telegram.org/bot' + config['token'] + '/sendMessage',
                                         data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json'})
        try:
            try:
                with self.opener(request, timeout=12) as response:
                    reply = json.load(response)
            except urllib.error.HTTPError as error:
                reply = json.loads(error.read())
        except Exception:
            # 逾時可能已送達；不能盲目重送造成重複。狀態留給owner核對。
            return {'state': 'uncertain', 'code': 'delivery_unknown'}
        if not isinstance(reply, dict) or type(reply.get('ok')) is not bool:
            return {'state': 'uncertain', 'code': 'response_invalid'}
        if reply['ok']:
            result = reply.get('result')
            if (not isinstance(result, dict) or type(result.get('message_id')) is not int
                or result['message_id'] <= 0 or not isinstance(result.get('chat'), dict) or not isinstance(result.get('from'), dict)
                or result['chat'].get('id') != config['chat_id']
                or (result.get('chat') or {}).get('type') != 'private'
                or (result.get('from') or {}).get('id') != int(config['token'].split(':', 1)[0])):
                return {'state': 'uncertain', 'code': 'receipt_invalid'}
            return {'state': 'sent', 'code': None, 'message_id': result['message_id']}
        code = reply.get('error_code')
        if code == 429:
            seconds = (reply.get('parameters') or {}).get('retry_after', 60)
            seconds = min(86400, max(15, seconds)) if type(seconds) is int else 60
            return {'state': 'retry', 'code': 'telegram_rate_limit', 'retry_after': seconds}
        if type(code) is int and 500 <= code <= 599:
            return {'state': 'retry', 'code': 'telegram_unavailable', 'retry_after': 60}
        return {'state': 'blocked', 'code': {400: 'recipient_invalid', 401: 'credential_rejected', 403: 'recipient_unavailable'}.get(code, 'telegram_rejected')}


class Notices:
    def __init__(self, office, config_path=CONFIG, sender=None, snapshot=None, clock=None):
        self.office = office
        self.path = Path(office.DATA_DIR) / 'office-notices.db'
        self.config_path = Path(config_path)
        self.sender = sender or Telegram(self.config_path)
        self.snapshot = snapshot or (lambda: collect(office))
        self.clock = clock or time.time
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.enabled = False
        self.error = None
        self.last_check = None
        self.thread = None

    @contextmanager
    def db(self):
        with self.lock:
            c = sqlite3.connect(self.path, timeout=5)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

    def initialize(self):
        if not self.config_path.exists():
            self.error = 'not_configured'
            return False
        try:
            load_config(self.config_path)
        except Exception:
            self.error = 'credential_invalid'
            return False
        if self.path.exists():
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                self.error = 'ledger_permissions_invalid'
                return False
        else:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        with self.db() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS notices(
                event_key TEXT PRIMARY KEY,task_id INTEGER NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,url TEXT NOT NULL,
                state TEXT NOT NULL,active INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0,message_id INTEGER,error_code TEXT,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            ''')
            c.execute("UPDATE notices SET state='uncertain',error_code='restart_delivery_unknown',updated_at=? WHERE state='sending'", (now(),))
        self.enabled = True
        return True

    def sync(self, notices):
        at = now()
        keys = {n['key'] for n in notices}
        if len(keys) != len(notices):
            raise ValueError('通知識別碼重複')
        with self.db() as c:
            first = c.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone() is None
            c.execute("UPDATE notices SET active=0 WHERE kind!='connected'")
            for item in notices:
                c.execute('''INSERT INTO notices(event_key,task_id,kind,text,url,state,active,next_attempt,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,1,?,?,?) ON CONFLICT(event_key) DO UPDATE SET active=1,updated_at=excluded.updated_at''',
                  (item['key'],item['task_id'],item['kind'],item['text'],item['url'],'baseline' if first else 'pending',self.clock()+60 if item['kind']=='blocked' else 0,at,at))
            c.execute("UPDATE notices SET state='cancelled',updated_at=? WHERE active=0 AND state IN ('pending','retry')", (at,))
            if first:
                c.execute("INSERT INTO meta VALUES('seeded',?)", (at,))
                hello = 'AI 協作辦公室通知已啟用。\n之後需要你決定、本人操作、驗收，或工作出現卡點時，會從這裡提醒並附工作單連結。\n首次啟用已記住舊待辦，避免歷史通知洗版；同一件事不反覆提醒。\n請按下方按鈕開啟辦公室。'
                c.execute('''INSERT INTO notices(event_key,task_id,kind,text,url,state,active,created_at,updated_at)
                  VALUES('connected:v1',0,'connected',?,?,'pending',1,?,?)''',(hello,PUBLIC_URL,at,at))
        self.last_check = at
        self.error = None

    def tick(self):
        if not self.enabled:
            return
        self.sync(self.snapshot())
        with self.db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM notices WHERE active=1 AND state IN ('pending','retry') AND next_attempt<=? ORDER BY created_at,event_key LIMIT 2",(self.clock(),))]
        for row in rows:
            if self.stop.is_set():
                break
            # 在送出之前重新讀取待辦，使用者剛完成的操作不再發送。
            if row['kind'] != 'connected':
                self.sync(self.snapshot())
            with self.db() as c:
                claimed = c.execute("UPDATE notices SET state='sending',attempts=attempts+1,updated_at=? WHERE event_key=? AND active=1 AND state IN ('pending','retry')",(now(),row['event_key'])).rowcount
            if not claimed:
                continue
            try:
                receipt = self.sender.send(row)
            except Exception:
                receipt = {'state':'uncertain','code':'sender_delivery_unknown'}
            if receipt.get('state') not in ('sent','retry','uncertain','blocked'):
                receipt = {'state':'uncertain','code':'sender_receipt_invalid'}
            delay = receipt.get('retry_after',60)
            delay = min(86400,max(15,delay)) if type(delay) is int else 60
            with self.db() as c:
                c.execute('''UPDATE notices SET state=?,message_id=?,error_code=?,next_attempt=?,updated_at=? WHERE event_key=?''',
                  (receipt['state'],receipt.get('message_id'),receipt.get('code'),self.clock()+delay if receipt['state']=='retry' else 0,now(),row['event_key']))

    def status(self):
        result = {'enabled':self.enabled,'bot_username':None,'last_check':self.last_check,'error_code':self.error,'states':{},'last_sent':None,'last_failure':None}
        if self.enabled:
            try:
                result['bot_username'] = load_config(self.config_path)['bot_username']
            except Exception:
                result['error_code'] = 'credential_invalid'
            with self.db() as c:
                result['states'] = {r['state']:r['n'] for r in c.execute('SELECT state,count(*) AS n FROM notices WHERE active=1 GROUP BY state')}
                row = c.execute("SELECT task_id,kind,message_id,updated_at FROM notices WHERE state='sent' ORDER BY updated_at DESC LIMIT 1").fetchone()
                result['last_sent'] = dict(row) if row else None
                row = c.execute("SELECT task_id,kind,state,error_code,attempts,updated_at FROM notices WHERE state IN ('blocked','uncertain','retry') AND active=1 ORDER BY updated_at DESC LIMIT 1").fetchone()
                result['last_failure'] = dict(row) if row else None
        return result

    def start(self):
        if not self.initialize():
            return
        self.thread = threading.Thread(target=self.loop,daemon=True,name='office-notices')
        self.thread.start()

    def loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                self.error = 'notice_check_failed'
                sys.stderr.write('辦公室通知檢查未完成；請主責核對通知狀態\n')
            self.stop.wait(15)
