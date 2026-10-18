"""模型目錄來自使用者填寫的設定；讀取設定不代表供應商已驗證。"""
from datetime import datetime
from pathlib import Path
import re
import shutil
from office_config import CONFIG

MODEL=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:+\[\]-]{0,119}')
EFFORTS=('none','minimal','low','medium','high','xhigh','max','ultra')
def valid_model(value):
    if not isinstance(value,str) or not MODEL.fullmatch(value):raise ValueError('模型識別格式不符')
    return value
def cli_path(worker):
    row=CONFIG['workers'].get(worker)
    if not row or not row['enabled']:raise ValueError('此工作者尚未啟用')
    value=row['cli']
    path=str(Path(value).expanduser()) if '/' in value else shutil.which(value)
    if not path or not Path(path).is_file():raise FileNotFoundError('原生 CLI 不存在，請安裝並填寫 cli')
    return path
def probe(worker):
    row=CONFIG['workers'][worker]
    model=valid_model(row['model'] or 'configure-model')
    options=[]
    for item in row['models']:
        if isinstance(item,str):item={'id':item,'label':item,'supported_efforts':[]}
        if not isinstance(item,dict):raise ValueError('模型選項格式不符')
        identifier=valid_model(item.get('id'))
        efforts=item.get('supported_efforts',[])
        if not isinstance(efforts,list) or any(x not in EFFORTS for x in efforts):raise ValueError('思考強度選項不符')
        options.append({'id':identifier,'label':str(item.get('label',identifier)),'supported_efforts':efforts})
    if not any(x['id']==model for x in options):options.insert(0,{'id':model,'label':row['model'] or '請先填寫模型','supported_efforts':[]})
    return {'default_model':model,'options':options,'verified_at':datetime.now().astimezone().isoformat(),
            'source':'使用者設定（尚未驗證供應商支援）','host':row.get('hostname') or 'local','refresh_error':None}
def catalog():
    return {'verified_at':datetime.now().astimezone().isoformat(),'source':'使用者設定；時間是設定讀取時間',
            'workers':{w:probe(w) for w in ('codex','claude','grok','assistant')}}
