"""AI 協作辦公室：office_capacity。"""
from datetime import datetime
from pathlib import Path
import json
import math

from office_config import CONFIG, DATA_DIR
CACHE=Path(CONFIG['capacity_file']) if CONFIG['capacity_file'] else DATA_DIR/'capacity.json'
NAMES={w:p['name'] for w,p in CONFIG['workers'].items()}
FIVE_HOUR_BASIS='5 小時額度'
WEEKLY_BASIS='每週額度'


def validated_windows(windows,now):
    """各視窗獨立驗證；參考額度缺件不會抹掉有效的主基準。"""
    if not isinstance(windows,list):raise ValueError('額度視窗格式異常')
    labels={}
    for w in windows:
        if not isinstance(w,dict) or not isinstance(w.get('label'),str) or not w['label']:continue
        labels.setdefault(w['label'],[]).append(w)
    result=[]
    for label,entries in labels.items():
        item={'label':label,'remaining':None,'resets_at':None,'status':'unknown'}
        try:
            if len(entries)!=1:raise ValueError('視窗名稱重複，待重新確認')
            w=entries[0];used=w['used']
            if w.get('status','ok')!='ok':raise ValueError('此視窗來源尚未就緒')
            if type(used) not in (int,float) or not math.isfinite(used) or not 0<=used<=100:
                raise ValueError('比例格式無效')
            try:reset=datetime.fromisoformat(w['resets_at'])
            except (ValueError,TypeError):raise ValueError('重置時間格式無效') from None
            if reset<=now:raise ValueError('等待重置後的新樣本')
            item.update(remaining=100-used,resets_at=reset.isoformat(),status='ok')
        except (ValueError,TypeError,KeyError,OverflowError) as e:
            item['reason']=str(e) if isinstance(e,ValueError) else '來源欄位不完整'
        result.append(item)
    return result


def reset_reserve(entry,now,left):
    result={'status':'unknown','available_count':None,'next_expiry':None,'suggestion':'重置券資料尚未確認'}
    try:
        if entry.get('status')!='ok' or not -30<=(now-datetime.fromisoformat(entry['at'])).total_seconds()<=900:return result
        raw=entry['reset_credits'];count=raw['available_count'];credits=raw['credits']
        if raw['status']!='ok' or type(count) is not int or not 0<=count<=1000 or not isinstance(credits,list) or len(credits)!=count:return result
        dates=[]
        for item in credits:
            if item['reset_type']!='codexRateLimits':return result
            expiry=datetime.fromisoformat(item['expires_at'])
            if expiry>now:dates.append(expiry)
        dates.sort();usable=len(dates)
        result.update(status='ok',available_count=usable,next_expiry=dates[0].isoformat() if dates else None,
                      suggestion='沒有可用重置券' if not usable else '可作後備；使用前由負責人兌換，成功後重新讀取額度')
        if usable and left is not None and left<30:
            result['suggestion']='額度偏低；大型工作開始前可由負責人使用重置券，更新額度後再分派'
        if usable and (dates[0]-now).total_seconds()<=3*86400:
            result['suggestion']+='；最近一張三天內到期'
    except (KeyError,ValueError,TypeError,OverflowError):pass
    return result


def capacity(path=CACHE, now=None):
    now=now or datetime.now().astimezone()
    try: raw=json.loads(Path(path).read_text())
    except (OSError,ValueError):raw={}
    if not isinstance(raw,dict):raw={}
    agents=[]
    for worker,key in [(w,w) for w,p in CONFIG['workers'].items() if p['enabled']]:
        entry=raw.get(key,{})
        if not isinstance(entry,dict):entry={}
        row={'worker':worker,'label':NAMES[worker],'state':'unknown','remaining_percent':None,
             'windows':[],'reason':'尚未取得有效額度','at':entry.get('at')}
        if CONFIG['workers'][worker]['provider']=='claude':row['basis_label']=FIVE_HOUR_BASIS
        elif key=='codex':row['basis_label']=None
        try:
            if entry.get('status')!='ok':raise ValueError('來源查詢失敗或尚未就緒')
            age=(now-datetime.fromisoformat(entry['at'])).total_seconds()
            if not -30<=age<=900:raise ValueError('來源超過15分鐘或時間異常')
            windows=entry.get('windows',[])
            if not windows:raise ValueError('未取得額度視窗')
            if key in ('claude','codex'):
                row['windows']=validated_windows(windows,now)
                if key=='codex':
                    labels={w['label'] for w in row['windows']}
                    # 依實際提供的視窗切換；5 小時資料損壞時不得退用週額度。
                    row['basis_label']=FIVE_HOUR_BASIS if FIVE_HOUR_BASIS in labels else WEEKLY_BASIS if WEEKLY_BASIS in labels else None
                basis=next((w for w in row['windows'] if w['label']==row['basis_label']),None)
                left=basis['remaining'] if basis else None
                if left is None:row['reason']=(row['basis_label'] or '5 小時或每週額度')+'尚未確認：'+(basis.get('reason','來源欄位不完整') if basis else '未取得此視窗')
            else:
                labels=set()
                for w in windows:
                    used=w['used'];label=w['label']
                    if type(used) not in (int,float) or not math.isfinite(used) or not 0<=used<=100:
                        raise ValueError('比例格式無效')
                    if not isinstance(label,str) or not label or label in labels:raise ValueError('視窗名稱異常')
                    labels.add(label)
                    reset=datetime.fromisoformat(w['resets_at'])
                    if reset<=now:raise ValueError('等待重置後的新樣本')
                    row['windows'].append({'label':label,'remaining':100-used,'resets_at':reset.isoformat()})
                left=min(w['remaining'] for w in row['windows'])
            if left is not None:
                row.update(remaining_percent=left,state='implementation' if left>=30 else 'small_review' if left>=15 else 'reserve',
                           reason='可接實作候選' if left>=30 else '建議只接小型查核' if left>=15 else '建議保留對話與收尾額度')
        except (ValueError,TypeError,KeyError) as e:
            row.update(state='unknown',remaining_percent=None,windows=[],reason=str(e) if isinstance(e,ValueError) else '來源欄位不完整')
        if worker=='codex':row['reset_credits']=reset_reserve(entry,now,row['remaining_percent'])
        row['team']=CONFIG['workers'][worker]['team']
        row['teams']=CONFIG['workers'][worker]['teams']
        row['pool']=worker
        agents.append(row)
    agents.append({'worker':'gemini','label':'Gemini','team':'life','pool':'gemini-api','state':'disabled','remaining_percent':None,'windows':[],'at':None,'reason':'API 計費；負責人尚未明確允許，不派工'})
    return {'mode':'advisory','fetched_at':now.isoformat(),'agents':agents,'thresholds':{'implementation':30,'small_review':15},
            'note':'只讀伺服器現有資料，先提供建議；未取得的視窗不代表無限制；重置券不計入剩餘百分比，不自動兌換。'}
