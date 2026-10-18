"""公開版的單一設定入口；不搜尋主機上的私人設定或聊天紀錄。"""
import copy
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
DEFAULTS = {
    'title': 'AI 協作辦公室', 'owner_name': '負責人', 'timezone': 'Asia/Taipei',
    'automation': False, 'model_discovery': False,
    'data_dir': './data', 'secret_dir': './data/secrets', 'context_dir': './context',
    'public_url': 'http://127.0.0.1:9870', 'capacity_file': '',
    'teams': {'maintenance': '開發協作區', 'life': '助理協作區'},
    'life_lead': 'assistant', 'execution_hosts': ['local'], 'protected_paths': [],
    'workers': {
        'claude': {'name': 'Claude', 'provider': 'claude', 'team': 'maintenance', 'teams': ['maintenance', 'life'], 'enabled': True, 'cli': 'claude', 'model': '', 'models': [], 'read_roots': [], 'host': ''},
        'codex': {'name': 'Codex', 'provider': 'codex', 'team': 'maintenance', 'teams': ['maintenance', 'life'], 'enabled': True, 'cli': 'codex', 'model': '', 'models': [], 'read_roots': [], 'host': ''},
        'assistant': {'name': '助理', 'provider': 'claude', 'team': 'life', 'teams': ['life'], 'enabled': True, 'cli': 'claude', 'model': '', 'models': [], 'read_roots': [], 'host': ''},
        'grok': {'name': 'Grok', 'provider': 'grok', 'team': 'maintenance', 'teams': ['maintenance', 'life'], 'enabled': False, 'cli': 'grok', 'model': '', 'models': [], 'read_roots': [], 'host': ''},
        'gemini': {'name': 'Gemini', 'provider': 'gemini', 'team': 'life', 'teams': ['life'], 'enabled': False, 'cli': 'gemini', 'model': '', 'models': [], 'read_roots': [], 'host': ''},
    },
}

def load(path=None):
    explicit = path or os.environ.get('OFFICE_CONFIG')
    config_path = Path(explicit).expanduser().resolve() if explicit else BASE/'office-config.json'
    data = copy.deepcopy(DEFAULTS)
    if explicit and not config_path.is_file():
        raise ValueError('OFFICE_CONFIG 指定的設定檔不存在')
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or set(raw)-set(DEFAULTS):
            raise ValueError('設定包含不支援的欄位')
        for key, value in raw.items():
            if key == 'workers':
                if not isinstance(value, dict) or set(value)-set(DEFAULTS['workers']):
                    raise ValueError('請使用範例中的工作者識別碼，顯示名稱可自行修改')
                for worker, row in value.items():
                    if not isinstance(row,dict) or set(row)-set(DEFAULTS['workers'][worker])-{'home','hostname','remote_dir'}:
                        raise ValueError('工作者設定欄位不符')
                    data['workers'][worker].update(row)
            else: data[key] = value
    for field in ('automation','model_discovery'):
        if type(data[field]) is not bool: raise ValueError(field+' 必須是布林值')
    for field in ('title','owner_name','timezone','data_dir','secret_dir','context_dir','public_url','capacity_file'):
        if not isinstance(data[field],str) or (not data[field] and field!='capacity_file'):
            raise ValueError(field+' 格式不符')
    ZoneInfo(data['timezone'])
    from urllib.parse import urlsplit
    u = urlsplit(data['public_url'])
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('public_url 必須是沒有帳密或路徑的 HTTP(S) origin')
    if not isinstance(data['teams'],dict) or set(data['teams'])!={'maintenance','life'} or any(not isinstance(x,str) or not x.strip() for x in data['teams'].values()):
        raise ValueError('需提供兩個工作區的顯示名稱')
    hosts=data['execution_hosts']
    if not isinstance(hosts,list) or not hosts or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',x) for x in hosts):
        raise ValueError('execution_hosts 需為 local 或明確的 SSH 別名')
    if not isinstance(data['protected_paths'],list) or any(not isinstance(x,str) or not Path(x).is_absolute() or '..' in Path(x).parts for x in data['protected_paths']):
        raise ValueError('protected_paths 必須是絕對路徑清單')
    base=config_path.parent
    def absolute(value): return str((base/Path(value).expanduser()).resolve())
    for field in ('data_dir','secret_dir','context_dir'):
        env='OFFICE_'+field.upper()
        data[field]=absolute(os.environ.get(env,data[field]))
    if data['capacity_file']: data['capacity_file']=absolute(data['capacity_file'])
    for worker, row in data['workers'].items():
        if type(row['enabled']) is not bool or row['team'] not in data['teams'] or not isinstance(row['name'],str) or not row['name'].strip() or len(row['name'])>80:
            raise ValueError('工作者名稱、工作區或啟用標記不符')
        if row['provider']!=DEFAULTS['workers'][worker]['provider']:
            raise ValueError('此測試版的工作者識別碼對應固定 CLI adapter')
        if worker=='gemini' and row['enabled']: raise ValueError('此測試版尚未提供 Gemini adapter，請保持停用')
        if not isinstance(row['teams'],list) or not row['teams'] or any(x not in data['teams'] for x in row['teams']):
            raise ValueError('工作者可參與的工作區不符')
        for field in ('cli','model','host'):
            if not isinstance(row[field],str): raise ValueError('工作者 '+field+' 格式不符')
        if row['model'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:+\[\]-]{0,119}',row['model']):
            raise ValueError('模型識別格式不符')
        if not isinstance(row['models'],list): raise ValueError('models 必須是清單')
        if not isinstance(row['read_roots'],list) or any(not isinstance(x,str) for x in row['read_roots']): raise ValueError('read_roots 必須是路徑清單')
        row['read_roots']=[absolute(x) for x in row['read_roots']]
        if row['host']:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',row['host']): raise ValueError('SSH host 必須是明確別名')
            if not row.get('home') or not Path(row['home']).is_absolute() or not isinstance(row.get('hostname'),str) or not row['hostname']:
                raise ValueError('遠端座位需提供 home 與 hostname')
            if row.get('remote_dir') and not Path(row['remote_dir']).is_absolute(): raise ValueError('remote_dir 必須是絕對路徑')
    if data['life_lead'] not in data['workers'] or not data['workers'][data['life_lead']]['enabled'] or 'life' not in data['workers'][data['life_lead']]['teams']:
        raise ValueError('life_lead 必須是已啟用的助理區工作者')
    return data

CONFIG=load()
DATA_DIR=Path(CONFIG['data_dir'])
SECRET_DIR=Path(CONFIG['secret_dir'])
CONTEXT_DIR=Path(CONFIG['context_dir'])
