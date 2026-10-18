"""依使用者設定決定名稱、工作區與派工資格。"""
from office_config import CONFIG
TEAMS=CONFIG['teams']
MEMBERS={w:{'name':p['name'],'team':p['team']} for w,p in CONFIG['workers'].items()}
AUTO_WORKERS=tuple(w for w,p in CONFIG['workers'].items() if p['enabled'])
EXECUTION_WORKERS=AUTO_WORKERS
LIFE_MEMBERS=tuple(w for w in AUTO_WORKERS if 'life' in CONFIG['workers'][w]['teams'])
MAINTENANCE_MEMBERS=tuple(w for w in AUTO_WORKERS if 'maintenance' in CONFIG['workers'][w]['teams'])
LIFE_LEAD=CONFIG['life_lead']
GEMINI_REASON='此測試版尚未提供 Gemini CLI adapter'
def team_of(worker):return MEMBERS.get(worker,{}).get('team')
def task_team(task):return task['team'] if 'team' in task.keys() else 'maintenance'
def in_team(worker,team):return worker in AUTO_WORKERS and team in CONFIG['workers'][worker]['teams']
def cross_team(actor,task):return actor in MEMBERS and not in_team(actor,task_team(task))
def roster():
    return [{'worker':w,**m,'teams':CONFIG['workers'][w]['teams'],'dispatch_enabled':w in AUTO_WORKERS,'dispatch_note':'可派工' if w in AUTO_WORKERS else GEMINI_REASON if w=='gemini' else '管理者尚未啟用'} for w,m in MEMBERS.items()]
def allowed_worker(worker,task,kind,reviewers):
    return worker in AUTO_WORKERS and (worker in reviewers if kind=='review' else in_team(worker,task_team(task)))
def can_view(actor,task,reviewers):
    if actor=='owner':return True
    if actor is None:return False
    authorized=task.get('authorized',False) if isinstance(task,dict) and 'authorized' in task else task['created_by']=='owner' or task['approved_by']=='owner'
    return in_team(actor,task_team(task)) or (actor in reviewers and bool(authorized))
def public_task(task,actor):
    if not cross_team(actor,task):return task
    task=dict(task);task['brief']='跨區僅分享本次計畫與交付；原始對話不隨複核傳出。'
    if 'messages' in task:task['messages']=[m for m in task['messages'] if m['kind'] in ('deliver','review')]
    return task
