"""AI 協作辦公室：office_runtime。"""
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_DIR = __import__('office_config').DATA_DIR / 'executions'
STATES = {'queued', 'running', 'returned', 'completed', 'failed', 'blocked'}
WORKERS = {'claude', 'codex', 'grok', 'assistant'}
TTL = 45


def stamp():
    return datetime.now(ZoneInfo(__import__('office_config').CONFIG['timezone'])).isoformat(timespec='seconds')


def process_identity(pid):
    try:
        fields = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, ValueError, IndexError):
        return None


def write_record(record, directory=DEFAULT_DIR):
    directory = Path(directory)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', record['id']):
        raise ValueError('無效執行識別碼')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / (record['id'] + '.json')
    temporary = directory / ('.' + uuid.uuid4().hex)
    try:
        with open(temporary, 'x') as f:
            os.chmod(temporary, 0o600)
            json.dump(record, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot(directory=DEFAULT_DIR):
    """只回傳顯示欄位；程序消失、PID重用或心跳過期不顯示執行中。"""
    result = {'runs': [], 'incomplete': False, 'fetched_at': stamp()}
    try:
        files = sorted(Path(directory).glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        result['incomplete'] = len(files) > 200
        for path in files[:200]:
            try:
                if path.is_symlink() or path.stat().st_size > 16384:
                    raise ValueError('無效紀錄大小或類型')
                a = json.loads(path.read_text())
                if (a['worker'] not in WORKERS or a['state'] not in STATES
                        or type(a['task_id']) is not int or a['task_id'] < 1
                        or not isinstance(a['label'], str) or not 1 <= len(a['label']) <= 120):
                    raise ValueError('無效欄位')
                age = time.time() - datetime.fromisoformat(a['updated_at']).timestamp()
                state = a['state']
                if state in ('running', 'queued'):
                    alive = process_identity(a.get('pid', 0))
                    if age < -10 or age > TTL or not alive or alive != a.get('process_start'):
                        state = 'unknown'
                public = {k: a.get(k) for k in ('id', 'task_id', 'worker', 'label', 'started_at',
                           'updated_at', 'finished_at', 'reported_by')}
                public['state'] = state
                result['runs'].append(public)
            except (OSError, ValueError, KeyError, TypeError):
                result['incomplete'] = True
    except OSError:
        result['incomplete'] = True
    return result


class Run:
    """呼叫端活著才續報；結束時由呼叫端指明待核對、完成或失敗。"""
    def __init__(self, task_id, worker, label, run_id=None, directory=DEFAULT_DIR, reported_by=None):
        self.directory = directory
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.record = {'id': run_id or str(uuid.uuid4()), 'task_id': task_id,
                       'worker': worker, 'label': label, 'state': 'running',
                       'started_at': stamp(), 'updated_at': stamp(), 'finished_at': None,
                       'pid': os.getpid(), 'process_start': process_identity(os.getpid()),
                       'reported_by': reported_by or worker}
        write_record(self.record, self.directory)
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def _heartbeat(self):
        while not self.stop.wait(10):
            with self.lock:
                self.record['updated_at'] = stamp()
                try:
                    write_record(self.record, self.directory)
                except OSError:
                    # 保留舊心跳，讀取端會顯示待確認。
                    pass

    def finish(self, state):
        if state not in ('returned', 'completed', 'failed', 'blocked'):
            raise ValueError('結束狀態無效')
        self.stop.set()
        with self.lock:
            self.record.update(state=state, updated_at=stamp(), finished_at=stamp())
            write_record(self.record, self.directory)
