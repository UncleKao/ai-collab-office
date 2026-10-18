"""AI 協作辦公室：office_plan。"""

def normalize_plan(value,worker,assigned=None):
    import office_execution
    import office_people as people
    if not isinstance(value,dict):return None
    summary=value.get('summary','').strip()
    if not 10<=len(summary)<=3000:raise ValueError('計畫摘要長度不符')
    scope=value.get('scope');acceptance=value.get('acceptance');steps=value.get('steps')
    if not all(isinstance(x,list) and 1<=len(x)<=20 for x in (scope,acceptance,steps)):raise ValueError('計畫缺少範圍、步驟或驗收')
    if not all(isinstance(x,str) and 1<=len(x)<=2000 for x in scope+acceptance):raise ValueError('計畫文字格式不符')
    owner=value.get('worker',(assigned or {}).get('worker') or worker)
    if assigned and assigned.get('worker') and owner!=assigned['worker']:raise ValueError('計畫執行人不符合負責人指定分工')
    if owner not in people.EXECUTION_WORKERS:raise ValueError(people.GEMINI_REASON if owner=='gemini' else '計畫負責人不符')
    notes={}
    for field in ('disagreements','assumptions','pending_items','absences'):
        values=value.get(field,[])
        if not isinstance(values,list) or len(values)>20 or any(not isinstance(x,str) or not 1<=len(x.strip())<=2000 for x in values):
            raise ValueError('計畫'+field+'格式不符')
        notes[field]=values
    clean=[]
    for s in steps:
        if not isinstance(s,dict) or not isinstance(s.get('title'),str):raise ValueError('計畫步驟格式不符')
        if s.get('kind') not in ('check','implement'):raise ValueError('計畫只能包含查核或工作區實作')
        clean.append({'title':s['title'][:2000],'worker':owner,'kind':s['kind']})
    execution=office_execution.normalize(value.get('execution'))
    return {'next_actions':normalize_next_actions(value.get('next_actions')),'summary':summary,'scope':scope,'acceptance':acceptance,'steps':clean,'worker':owner,**notes,**({'execution':execution} if execution else {})}



def normalize_next_actions(value):
    """接續事項只有顯示語義，不能改變權限、啟動工作或替人核准。"""
    if value is None:return []
    if not isinstance(value,list) or len(value)>20:raise ValueError('next_actions格式不符')
    clean=[]
    for row in value:
        if not isinstance(row,dict) or set(row)!={'kind','text'} or row['kind'] not in ('approval','planning','implementation','schedule'):
            raise ValueError('next_actions類型不符')
        if not isinstance(row['text'],str) or not 1<=len(row['text'].strip())<=2000:raise ValueError('next_actions文字不符')
        clean.append({'kind':row['kind'],'text':row['text'].strip()})
    return clean
