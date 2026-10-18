"""AI 協作辦公室：office_summary_worker。"""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import os
from office_worker_tools import atomic, stamp, schema


def validate(source,summary):
    if not isinstance(summary,dict):raise ValueError('總結格式不符')
    messages={m['id']:m for m in source['messages']}
    def refs(value):
        if not isinstance(value,list) or not value or len(value)>12 or any(type(x) is not int or x not in messages for x in value):raise ValueError('每段需引用本輪原訊息')
        return list(dict.fromkeys(value))
    overview=summary.get('overview')
    if not isinstance(overview,str) or not 10<=len(overview.strip())<=800:raise ValueError('總結開頭需10至800字')
    points=summary.get('points')
    if not isinstance(points,list) or not 1<=len(points)<=8:raise ValueError('總結需1至8個重點')
    clean=[]
    for p in points:
        if not isinstance(p,dict) or p.get('category') not in ('consensus','difference','next','decision'):raise ValueError('重點分類不符')
        text=p.get('text');ids=refs(p.get('refs'));speakers=p.get('speakers')
        if not isinstance(text,str) or not 1<=len(text.strip())<=600:raise ValueError('重點太長或空白')
        authors={messages[x]['author'] for x in ids}
        if not isinstance(speakers,list) or not speakers or any(x not in authors for x in speakers):raise ValueError('署名需有對應原文')
        if p['category'] in ('consensus','difference'):
            discussants={messages[x]['author'] for x in ids if messages[x].get('kind') not in ('control','system','decide','claim','new') and messages[x]['author']!='system'}
            if any(x not in discussants for x in speakers):raise ValueError('共識與分歧須引用本人公開發言，操作紀錄不能代替意見')
        if p['category']=='consensus' and len(set(speakers)-{'system'})<2:raise ValueError('單一發言不能列為共識')
        clean.append({'category':p['category'],'text':text.strip(),'refs':ids,'speakers':list(dict.fromkeys(speakers))})
    if len(overview)+sum(len(p['text']) for p in clean)>2400:raise ValueError('總結請縮短至2400字內')
    return {'overview':overview.strip(),'refs':refs(summary.get('refs')),'points':clean}


TEXT={'type':'string'}
IDS={'type':'array','items':{'type':'integer'}}
TOOLS=[
    {'name':'current_time','description':'確認目前台北時間','inputSchema':schema()},
    {'name':'read_context','description':'讀本輪需求、工作狀態及訊息索引；索引不等於已讀原文','inputSchema':schema()},
    {'name':'read_messages','description':'依index讀一則固定公開訊息，長文用offset續讀到next_offset為null','inputSchema':schema({'index':{'type':'integer'},'offset':{'type':'integer'}},['index'])},
    {'name':'submit_summary','description':'讀完本輪原文後提交署名總結，不改任何工作狀態','inputSchema':schema({'overview':TEXT,'refs':IDS,'points':{'type':'array','items':schema({'category':{'enum':['consensus','difference','next','decision']},'text':TEXT,'refs':IDS,'speakers':{'type':'array','items':TEXT}},['category','text','refs','speakers'])}},['overview','refs','points'])}]


def serve(path):
    path=Path(path);raw=path.read_bytes();manifest=json.loads(raw);source=manifest['context'];covered={};seen=set()
    if manifest['kind']!='summary':raise ValueError('只接受摘要工作單')
    for line in sys.stdin:
        req=json.loads(line)
        if 'id' not in req:continue
        name=None;success=False
        try:
            method=req.get('method')
            if method=='initialize':
                value={'protocolVersion':req.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'office-summary','version':'1'}}
            elif method=='tools/list':value={'tools':TOOLS}
            elif method=='ping':value={}
            elif method=='tools/call':
                name=req['params']['name'];args=req['params'].get('arguments',{})
                if name=='current_time':data={'time':subprocess.check_output(['date','--iso-8601=seconds'],env={**os.environ,'TZ':__import__('office_config').CONFIG['timezone']},text=True).strip()}
                elif name=='read_context':data={**{k:v for k,v in source.items() if k!='messages'},'messages':[{'index':i,**{k:m[k] for k in ('id','author','kind','created_at')},'characters':len(m['body'])} for i,m in enumerate(source['messages'])]}
                elif name=='read_messages':
                    i=args['index'];offset=args.get('offset',0)
                    if type(i) is not int or not 0<=i<len(source['messages']) or type(offset) is not int or offset<0:raise ValueError('訊息位置不符')
                    m=source['messages'][i];body=m['body'];end=min(len(body),offset+6000)
                    if offset>len(body):raise ValueError('超過訊息長度')
                    covered.setdefault(i,set()).update(range(offset,end))
                    data={**m,'body':body[offset:end],'next_offset':end if end<len(body) else None}
                elif name=='submit_summary':
                    if not {'current_time','read_context'}<=seen or any(len(covered.get(i,set()))!=len(m['body']) for i,m in enumerate(source['messages'])):raise ValueError('先確認時間、上下文並完整讀取本輪每則訊息')
                    clean=validate(source,args)
                    destination=path.parent/'result.json'
                    if destination.exists() and json.loads(destination.read_text())['summary']!=clean:raise ValueError('本輪已交不同總結，不能覆寫')
                    atomic(destination,{'summary':clean,'manifest_sha256':hashlib.sha256(raw).hexdigest(),'submitted_at':stamp()})
                    data={'accepted':True}
                else:raise ValueError('摘要沒有此工具')
                seen.add(name);success=True
                value={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}]}
            else:raise ValueError('未知方法')
        except Exception as e:value={'isError':True,'content':[{'type':'text','text':str(e)}]}
        if name:
            with (path.parent/'tool-events.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'success':success,'at':stamp()})+'\n')
        print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':value},ensure_ascii=False),flush=True)


if __name__=='__main__':serve(sys.argv[1])
