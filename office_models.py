"""AI 協作辦公室：office_models。"""
import json
import os
import threading
import time
import tempfile
from datetime import datetime
import office_model_discovery as discovery
from pathlib import Path

import office_people as people

WORKERS = ('codex', 'claude', 'grok', 'assistant')
CATALOG_PATH = Path(__file__).resolve().parent / 'model-catalog.json'


def _load_catalog(path=None, data=None):
    if data is None:data = json.loads(path.read_text(encoding='utf-8')) if path else discovery.catalog()
    if not isinstance(data, dict) or not isinstance(data.get('workers'), dict):
        raise ValueError('模型目錄格式不符')
    if not isinstance(data.get('verified_at'), str) or not data['verified_at']:
        raise ValueError('模型目錄缺少核對時間')
    workers = {}
    for name in WORKERS:
        row = data['workers'].get(name)
        if not isinstance(row, dict):
            raise ValueError('模型目錄缺少夥伴 ' + name)
        stamp = datetime.fromisoformat(row.get('verified_at', data['verified_at']))
        if stamp.tzinfo is None:raise ValueError('模型核對時間缺少時區')
        default = row.get('default_model')
        options = row.get('options')
        if not isinstance(default, str) or not default or not isinstance(options, list) or not options:
            raise ValueError('模型目錄的 ' + name + ' 選項不完整')
        clean = []
        seen = set()
        for item in options:
            if not isinstance(item, dict) or type(item.get('id')) is not str or type(item.get('label')) is not str:
                raise ValueError('模型目錄的 ' + name + ' 選項格式不符')
            if not item['id'] or not item['label'] or item['id'] in seen:
                raise ValueError('模型目錄的 ' + name + ' 選項重複或空白')
            seen.add(item['id'])
            discovery.valid_model(item['id'])
            if len(item['label']) > 160:
                raise ValueError('模型名稱過長')
            efforts = item.get('supported_efforts', [])
            if not isinstance(efforts, list) or any(type(e) is not str or e not in discovery.EFFORTS for e in efforts):
                raise ValueError('原生思考強度格式不符')
            if len(efforts) != len(set(efforts)):
                raise ValueError('原生思考強度重複')
            clean.append({'id': item['id'], 'label': item['label'], 'supported_efforts': list(efforts)})
        if default not in seen:
            raise ValueError('模型目錄的 ' + name + ' 預設不在選項內')
        workers[name] = {'default_model': default, 'options': clean,
                         'verified_at': row.get('verified_at', data['verified_at']),
                         'source': row.get('source', data.get('source')),
                         'host': row.get('host'), 'refresh_error': row.get('refresh_error')}
    source = data.get('source')
    if source is not None and type(source) is not str:
        raise ValueError('模型目錄來源說明格式不符')
    return {'verified_at': data['verified_at'], 'source': source, 'workers': workers}


CACHE_PATH = __import__('office_config').DATA_DIR / 'model-catalog-live.json'
REFRESH_SECONDS = 300
_catalog_lock = threading.RLock()
_live_catalog = None
_auto_refresh = False
_refreshing = False
_last_attempt = 0.0
_last_signature = None


class CatalogUnavailable(ValueError):
    pass


def _signature():
    paths = []
    for worker in ('codex', 'claude', 'grok'):
        try:paths.append(Path(discovery.cli_path(worker)))
        except FileNotFoundError:paths.append(Path('/不存在的原生CLI/' + worker))
    paths.append(Path.home() / '.codex/config.toml')
    return tuple((str(p.resolve()), p.stat().st_mtime_ns) for p in paths if p.exists())


def _initial_catalog():
    # 個別 provider 失敗不會把其他 provider 的有效清單覆蓋掉。
    if CACHE_PATH.exists():
        try:
            return _load_catalog(CACHE_PATH)
        except (ValueError, OSError):
            pass
    return _load_catalog()


def _refresh():
    global _live_catalog, _refreshing
    try:
        with _catalog_lock:
            current = json.loads(json.dumps(_live_catalog or _initial_catalog()))
        for worker in WORKERS:
            try:
                proposed = json.loads(json.dumps(current))
                proposed['workers'][worker] = discovery.probe(worker)
                current['workers'][worker] = _load_catalog(data=proposed)['workers'][worker]
            except Exception as error:
                current['workers'][worker]['refresh_error'] = type(error).__name__
        current['verified_at'] = min(row['verified_at'] for row in current['workers'].values())
        current['source'] = '使用者設定（尚未驗證供應商支援）'
        with _catalog_lock:
            _live_catalog = current
        # 本輪已驗證的清單仍可使用；快取寫入失敗不能使有效查詢消失。
        temporary = None
        try:
            CACHE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=CACHE_PATH.parent,
                                             prefix='.model-catalog-', delete=False) as output:
                temporary = Path(output.name)
                json.dump(current, output, ensure_ascii=False, indent=2)
            os.replace(temporary, CACHE_PATH)
        except OSError:
            pass
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
    finally:
        with _catalog_lock:
            _refreshing = False


def refresh_catalog(force=False, background=True):
    global _refreshing, _last_attempt, _last_signature, _live_catalog
    with _catalog_lock:
        if _live_catalog is None:
            _live_catalog = _initial_catalog()
        signature = _signature()
        if _refreshing or (not force and signature == _last_signature
                           and time.monotonic() - _last_attempt < REFRESH_SECONDS):
            return False
        _refreshing = True
        _last_attempt = time.monotonic()
        _last_signature = signature
    if background:
        threading.Thread(target=_refresh, name='office-model-catalog', daemon=True).start()
    else:
        _refresh()
    return True


def start_catalog_refresh():
    global _auto_refresh
    _auto_refresh = True
    refresh_catalog()


def catalog():
    if not _auto_refresh:
        return _load_catalog()
    refresh_catalog()
    with _catalog_lock:
        result = json.loads(json.dumps(_live_catalog))
        result['refreshing'] = _refreshing
    for row in result['workers'].values():
        age = time.time() - datetime.fromisoformat(row['verified_at']).timestamp()
        row['stale'] = bool(row.get('refresh_error')) or age > 86400
    return result


# 本輪核對快照，只代表目錄當時列出的預設；不能宣稱 API 永遠可用。
DEFAULTS = {name: catalog()['workers'][name]['default_model'] for name in WORKERS}


def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS office_model_settings(
        task_id INTEGER PRIMARY KEY, version INTEGER NOT NULL,
        models TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS office_effort_settings(
        task_id INTEGER PRIMARY KEY, efforts TEXT NOT NULL)''')


def _stored(c, task):
    row = c.execute('SELECT version,models,updated_at FROM office_model_settings WHERE task_id=?', (task['id'],)).fetchone()
    if not row:
        return 0, {name: None for name in WORKERS}, None
    models = json.loads(row['models'] if isinstance(row, dict) else row[1])
    version = row['version'] if isinstance(row, dict) else row[0]
    updated = row['updated_at'] if isinstance(row, dict) else row[2]
    if type(version) is not int or version < 0 or not isinstance(models, dict) or set(models) != set(WORKERS):
        raise ValueError('已存模型選擇格式不符')
    clean = {}
    for name in WORKERS:
        value = models[name]
        if value is not None and type(value) is not str:
            raise ValueError('已存模型選擇格式不符')
        clean[name] = value
    return version, clean, updated


def _stored_efforts(c, task):
    row = c.execute('SELECT efforts FROM office_effort_settings WHERE task_id=?', (task['id'],)).fetchone()
    if not row:return {worker: None for worker in WORKERS}
    values = json.loads(row['efforts'] if isinstance(row, dict) else row[0])
    if not isinstance(values, dict) or set(values) != set(WORKERS):
        raise ValueError('已存思考強度格式不符')
    for value in values.values():
        if value is not None and (type(value) is not str or value not in discovery.EFFORTS):
            raise ValueError('已存思考強度格式不符')
    return values


def effort_options(cat, worker, model):
    return next((item['supported_efforts'] for item in cat['workers'][worker]['options']
                 if item['id'] == model), [])


def snapshot(c, task):
    cat = catalog()
    version, selected, _updated = _stored(c, task)
    efforts = _stored_efforts(c, task)
    workers = []
    for name in WORKERS:
        info = cat['workers'][name]
        workers.append({
            'worker': name,
            'selected': selected[name], 'selected_effort': efforts[name],
            'default_model': info['default_model'],
            'options': [dict(item) for item in info['options']],
            'verified_at': info.get('verified_at'), 'source': info.get('source'),
            'host': info.get('host'), 'stale': info.get('stale', False),
            'refresh_error': info.get('refresh_error'),
        })
    return {'version': version, 'verified_at': cat['verified_at'], 'workers': workers,
            'refreshing': cat.get('refreshing', False)}


def _validate_payload(o, payload, cat, preserved=None):
    if not isinstance(payload, dict) or set(payload) not in ({'version', 'models'}, {'version', 'models', 'efforts'}):
        raise o.OfficeError(400, '模型設定需要版本與四位夥伴的選擇')
    if type(payload['version']) is not int or payload['version'] < 0:
        raise o.OfficeError(400, '模型版本格式不符')
    models = payload['models']
    if not isinstance(models, dict):
        raise o.OfficeError(400, '模型選擇必須是物件')
    if 'gemini' in models:
        raise o.OfficeError(403, people.GEMINI_REASON)
    extra = set(models) - set(WORKERS)
    missing = set(WORKERS) - set(models)
    if extra or missing:
        raise o.OfficeError(400, '模型選擇必須正好包含Codex、Claude、Grok 與助理，且不得加入其他人')
    clean = {}
    for name in WORKERS:
        value = models[name]
        ids = {item['id'] for item in cat['workers'][name]['options']}
        if value is None:
            clean[name] = None
            continue
        if type(value) is not str or (value not in ids and value != (preserved or {}).get(name)):
            raise o.OfficeError(400, '不接受未列出的模型或注入的型號')
        clean[name] = value
    return payload['version'], clean


def save(o, c, task, payload, actor):
    if actor != o.BOSS:
        raise o.OfficeError(403, '只有負責人能指定模型')
    if not o.authorized_by(task)[0]:
        raise o.OfficeError(409, '請先由負責人明確收件，再儲存模型選擇')
    if task['status'] in ('closed', 'dropped', 'proposal'):
        raise o.OfficeError(409, '這張單尚未收件或已封存，不能改模型')
    cat = catalog()
    current_version, current_models, _updated = _stored(c, task)
    version, models = _validate_payload(o, payload, cat, current_models)
    current_efforts = _stored_efforts(c, task)
    efforts = payload.get('efforts', current_efforts)
    if not isinstance(efforts, dict) or set(efforts) != set(WORKERS):
        raise o.OfficeError(400, '思考強度必須正好包含四位夥伴')
    for name, value in efforts.items():
        if value is None:continue
        model = models[name] or cat['workers'][name]['default_model']
        preserved = models[name] == current_models[name] and value == current_efforts[name]
        if type(value) is not str or value not in discovery.EFFORTS or (value not in effort_options(cat, name, model) and not preserved):
            raise o.OfficeError(400, '所選模型不支援這個思考強度，請改選或跟隨預設')
    if version != current_version:
        raise o.OfficeError(409, '模型選擇已更新，請重新檢視後再儲存')
    if models == current_models and efforts == current_efforts:
        return
    now = o.now()
    c.execute(
        'INSERT INTO office_model_settings(task_id,version,models,updated_at) VALUES(?,?,?,?) '
        'ON CONFLICT(task_id) DO UPDATE SET version=excluded.version,models=excluded.models,updated_at=excluded.updated_at',
        (task['id'], current_version + 1, json.dumps(models, ensure_ascii=False, sort_keys=True), now),
    )
    if efforts != current_efforts:
        c.execute('INSERT INTO office_effort_settings(task_id,efforts) VALUES(?,?) '
                  'ON CONFLICT(task_id) DO UPDATE SET efforts=excluded.efforts',
                  (task['id'], json.dumps(efforts, sort_keys=True)))


def selection(c, task, worker):
    if worker not in WORKERS:
        raise ValueError('不認識的夥伴，無法解析模型')
    version, selected, _updated = _stored(c, task)
    choice = selected[worker]
    if choice is None:
        info = catalog()['workers'][worker]
        if info.get('stale') or info.get('refresh_error'):
            raise CatalogUnavailable('這位夥伴的模型清單尚未完成有效更新，保留原工作')
        model = info['default_model']
    else:
        model = choice
    effort = _stored_efforts(c, task)[worker]
    if effort is not None:
        cat = catalog()
        if model in {item['id'] for item in cat['workers'][worker]['options']} and effort not in effort_options(cat, worker, model):
            raise CatalogUnavailable('目前模型不支援已選思考強度，請調整設定，保留原工作')
    return {'choice': choice, 'model': model, 'effort': effort, 'version': version}
