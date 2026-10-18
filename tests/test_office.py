"""公開版的空白安裝、HTTP 流程、身分與檔案邊界驗證。"""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import office_config
import office_execution
import office_native
import office_remote
from office_worker_tools import WorkerTools,available_tools

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='office-http-')
        cls.folder=Path(cls.temp.name)
        config=copy.deepcopy(office_config.DEFAULTS)
        config.update(title='測試協作空間',owner_name='測試負責人',timezone='UTC',data_dir='./state',secret_dir='./state/secrets')
        config['workers']['codex']['name']='複核夥伴'
        config['workers']['codex']['teams']=['maintenance']
        cls.config=cls.folder/'config.json';cls.config.write_text(json.dumps(config))
        cls.env={**os.environ,'OFFICE_CONFIG':str(cls.config)}
        for name in ('OFFICE_DATA_DIR','OFFICE_SECRET_DIR','OFFICE_CONTEXT_DIR'):
            cls.env.pop(name,None)
        with socket.socket() as s:s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.url=f'http://127.0.0.1:{cls.port}'
        cls.log=(cls.folder/'server.log').open('wb')
        cls.process=subprocess.Popen([sys.executable,str(ROOT/'office_server.py'),'--port',str(cls.port)],env=cls.env,stdout=cls.log,stderr=cls.log)
        for _ in range(100):
            if cls.process.poll() is not None:
                cls.log.flush();raise RuntimeError('測試中樞提前退出：'+(cls.folder/'server.log').read_text()[-1200:])
            try:
                with urllib.request.urlopen(cls.url+'/health',timeout=.3) as response:
                    if json.load(response)['ok']:break
            except (OSError,urllib.error.URLError):time.sleep(.05)
        else:raise RuntimeError('測試中樞未啟動')
        cls.tokens={p.stem:p.read_text().strip() for p in (cls.folder/'state/secrets').glob('*.tok')}

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:cls.process.kill();cls.process.wait()
        cls.log.close();cls.temp.cleanup()

    def request(self,path,actor=None,payload=None,cookie=None):
        headers={}
        if actor:headers['Authorization']='Bearer '+self.tokens[actor]
        if cookie:headers['Cookie']=cookie
        data=None
        if payload is not None:data=json.dumps(payload).encode();headers['Content-Type']='application/json'
        req=urllib.request.Request(self.url+path,data=data,headers=headers)
        try:response=urllib.request.urlopen(req,timeout=4)
        except urllib.error.HTTPError as e:response=e
        with response:
            raw=response.read()
            value=json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw.decode()
            return response.code,value,dict(response.headers)

    def new(self,actor='owner',**fields):
        code,t,_=self.request('/api/tasks',actor,{'title':'測試任務','brief':'只含測試資料','reviewers':'codex',**fields})
        self.assertEqual(code,201);return t
    def action(self,t,actor,action,**fields):
        return self.request(f'/api/tasks/{t["id"]}/{action}',actor,{'body':'測試證據',**fields})

    def test_00_empty_database_and_default_mode(self):
        code,data,_=self.request('/api/tasks','owner')
        self.assertEqual(code,200);self.assertEqual(data,[])
        code,data,_=self.request('/web/overview')
        self.assertEqual(data['tasks'],[]);self.assertFalse(data['settings']['automation'])
        self.assertEqual(data['settings']['title'],'測試協作空間')
        self.assertEqual(data['settings']['owner_name'],'測試負責人')
        self.assertEqual(data['settings']['timezone'],'UTC')
        self.assertEqual(next(m['name'] for m in data['members'] if m['worker']=='codex'),'複核夥伴')

    def test_token_permissions_and_health(self):
        for p in (self.folder/'state/secrets').glob('*.tok'):self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE((self.folder/'state/secrets').stat().st_mode),0o700)
        self.assertTrue(self.request('/health')[1]['ok'])

    def test_unauthenticated_reads_are_private(self):
        task=self.new()
        self.assertEqual(self.request('/web/overview')[1]['tasks'],[])
        for path in ('/api/tasks',f'/web/tasks/{task["id"]}','/web/executions','/web/capacity'):
            self.assertIn(self.request(path)[0],(401,403))

    def test_login_csrf_and_custom_identity(self):
        code,_,headers=self.request('/web/login',payload={'token':self.tokens['owner']})
        self.assertEqual(code,200);self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        cookie=headers['Set-Cookie'].split(';',1)[0]
        code,session,_=self.request('/web/session',cookie=cookie)
        self.assertEqual(session['name'],'owner')
        self.assertEqual(self.request('/web/tasks',payload={'title':'測試','brief':'測試','csrf':'wrong'},cookie=cookie)[0],403)
        self.assertEqual(self.request('/web/tasks',payload={'title':'測試','brief':'測試','csrf':session['csrf']},cookie=cookie)[0],201)

    def test_invalid_login(self):
        self.assertEqual(self.request('/web/login',payload={'token':'invalid-test-value'})[0],401)

    def test_complete_manual_lifecycle(self):
        task=self.new();self.assertTrue(task['authorized'])
        self.assertEqual(self.action(task,'claude','claim')[1]['status'],'working')
        self.assertEqual(self.action(task,'claude','deliver')[1]['status'],'review')
        self.assertEqual(self.action(task,'claude','review',verdict='pass')[0],403)
        self.assertEqual(self.action(task,'codex','review',verdict='pass')[1]['status'],'approved')
        self.assertEqual(self.action(task,'owner','decide',decision='active')[1]['status'],'active')

    def test_proposal_requires_owner_acceptance(self):
        task=self.new('claude')
        self.assertFalse(task['authorized']);self.assertEqual(task['status'],'proposal')
        self.assertEqual(self.action(task,'claude','claim')[0],409)
        self.assertEqual(self.action(task,'owner','decide',decision='accept')[1]['status'],'inbox')
        self.assertEqual(self.action(task,'claude','claim')[0],200)

    def test_only_owner_can_decide_and_cannot_skip_review(self):
        task=self.new()
        self.assertEqual(self.action(task,'claude','decide',decision='active')[0],403)
        self.assertEqual(self.action(task,'owner','decide',decision='active')[0],409)

    def test_reject_requires_fresh_delivery(self):
        task=self.new()
        self.action(task,'claude','deliver')
        self.assertEqual(self.action(task,'codex','review',verdict='reject')[1]['status'],'fix')
        self.assertEqual(self.action(task,'codex','review',verdict='pass')[1]['status'],'fix')
        self.assertEqual(self.action(task,'owner','decide',decision='active')[0],409)
        self.action(task,'claude','deliver')
        self.assertEqual(self.action(task,'codex','review',verdict='pass')[1]['status'],'approved')

    def test_cross_team_review_does_not_reveal_brief(self):
        task=self.new(team='life',brief='測試用限制分享內容')
        code,data,_=self.request(f'/api/tasks/{task["id"]}','codex')
        self.assertEqual(code,200);self.assertNotEqual(data['brief'],'測試用限制分享內容')
        self.assertNotIn('測試用限制分享內容',json.dumps(data,ensure_ascii=False))
        self.assertEqual(self.action(task,'codex','claim')[0],403)

    def test_disabled_worker_is_rejected(self):
        self.assertEqual(self.request('/api/tasks','grok',{'title':'測試','brief':'測試'})[0],403)
        self.assertEqual(self.request('/api/tasks','owner',{'title':'測試','brief':'測試','reviewers':'grok'})[0],403)

    def test_manual_mode_never_queues_model_jobs(self):
        task=self.new();self.action(task,'owner','say')
        with sqlite3.connect(self.folder/'state/office.db') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM office_jobs').fetchone()[0],0)

    def test_manual_mode_rejects_model_dispatch_controls(self):
        task=self.new()
        _,_,headers=self.request('/web/login',payload={'token':self.tokens['owner']})
        cookie=headers['Set-Cookie'].split(';',1)[0]
        csrf=self.request('/web/session',cookie=cookie)[1]['csrf']
        for action in ('discuss','start','summarize'):
            status,_,_=self.request(f'/web/tasks/{task["id"]}/control',payload={'csrf':csrf,'action':action,'request_id':'test-manual-control'},cookie=cookie)
            self.assertEqual(status,409)

    def test_cli_uses_same_configuration(self):
        env={**self.env,'OFFICE_URL':self.url}
        r=subprocess.run([sys.executable,str(ROOT/'office.py'),'--agent','owner','whoami'],env=env,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertNotIn(self.tokens['owner'],r.stdout+r.stderr)

    def test_static_assets(self):
        for path in ('/','/app.js','/models.js','/style.css','/mark.svg'):
            code,data,headers=self.request(path)
            self.assertEqual(code,200);self.assertTrue(data)
            self.assertIn('Content-Security-Policy',headers)

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='office-unit-');self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def manifest(self,kind='implement'):
        work=self.root/'workspace';work.mkdir(exist_ok=True)
        job=self.root/'job';job.mkdir(exist_ok=True)
        m={'id':1,'task_id':1,'worker':'claude','kind':kind,'workspace':str(work),'context':{},'read_roots':[],'jobs_root':str(self.root),'baseline':False,'desktop_probe':False}
        p=job/'manifest.json';p.write_text(json.dumps(m));return p,m

    def test_paths_are_relative_to_config_file(self):
        f=self.root/'config.json';f.write_text(json.dumps({'data_dir':'./state','secret_dir':'./auth','context_dir':'./refs'}))
        config=office_config.load(f)
        self.assertEqual(config['data_dir'],str(self.root/'state'));self.assertEqual(config['secret_dir'],str(self.root/'auth'))

    def test_invalid_configuration_fails_closed(self):
        for value in ({'automation':'yes'},{'workers':{'unexpected':{}}},{'workers':{'gemini':{'enabled':True}}},{'execution_hosts':['-invalid']},{'timezone':'invalid-zone'}):
            f=self.root/'config.json';f.write_text(json.dumps(value))
            with self.assertRaises((ValueError,KeyError)):office_config.load(f)

    def test_missing_explicit_config_fails(self):
        with self.assertRaises(ValueError):office_config.load(self.root/'missing.json')

    def test_default_reference_roots_and_private_recall_are_empty(self):
        import office_home_context,office_private_recall,office_source_collection
        self.assertEqual(office_home_context.local_roots('claude'),[])
        self.assertEqual(office_private_recall.lookup('claude','測試','測試',jobs_root=self.root),[])
        self.assertIsNone(office_source_collection.collect(self.root,{},self.root))

    def test_file_escape_and_secret_paths_are_denied(self):
        path,m=self.manifest();tools=WorkerTools(path)
        outside=self.root/'outside.txt';outside.write_text('測試')
        (Path(m['workspace'])/'escape').symlink_to(outside)
        for name in ('../outside.txt','escape','.ssh/known_hosts','.env'):
            with self.assertRaises(ValueError):tools.resolve(name)
        with self.assertRaises(ValueError):tools.resolve(str(outside),write=True)

    def test_file_write_uses_current_hash(self):
        path,m=self.manifest();tools=WorkerTools(path)
        tools.execute('write_file',{'path':'hello.txt','content':'第一版','expected_sha256':None})
        with self.assertRaises(ValueError):tools.execute('write_file',{'path':'hello.txt','content':'覆蓋','expected_sha256':None})
        expected=hashlib.sha256('第一版'.encode()).hexdigest()
        tools.execute('write_file',{'path':'hello.txt','content':'第二版','expected_sha256':expected})
        self.assertEqual((Path(m['workspace'])/'hello.txt').read_text(),'第二版')

    def test_discussion_cannot_write_or_use_environment_probes(self):
        path,m=self.manifest('discuss')
        tools=available_tools(m)
        self.assertIn('read_context',tools);self.assertNotIn('write_file',tools)
        self.assertTrue(set(tools).isdisjoint({'inspect_baseline','inspect_desktop','home_inventory','unit_status','unit_log_tail'}))

    def test_native_command_and_resume_keep_one_configuration_layer(self):
        path,m=self.manifest('discuss')
        m['model']='test-model';m['effort']='medium';path.write_text(json.dumps(m))
        with patch('office_native.cli_path',return_value='/usr/bin/example-cli'):
            fresh,_=office_native.command('codex',path.parent)
            resumed,_=office_native.command('codex',path.parent,'00000000-0000-0000-0000-000000000001')
        self.assertIn('--sandbox',fresh);self.assertIn('read-only',fresh)
        self.assertEqual(resumed.count('resume'),1)
        self.assertTrue(all(i>resumed.index('resume') for i,x in enumerate(resumed) if x=='-c'))
        self.assertIn('mcp_servers.office.required=true',resumed)

    def test_native_execution_is_disabled_in_manual_mode(self):
        with self.assertRaisesRegex(ValueError,'手動測試'):office_native.run('claude',self.root)

    def test_remote_unpack_rejects_traversal_and_symlinks(self):
        import base64
        data=base64.b64encode(b'test').decode()
        for name in ('../outside','/absolute','.ssh/config'):
            with self.assertRaises(ValueError):office_remote.unpack({name:data},self.root/'work')
        work=self.root/'work';target=self.root/'other';target.mkdir();(work/'link').symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):office_remote.unpack({'link/file':data},work)

    def test_execution_rejects_unconfigured_hosts_and_secret_paths(self):
        with self.assertRaises(ValueError):office_execution.normalize({'scope':{'unconfigured':['${workspace}']},'commands':[],'rollback':['回復']})
        for path in ('/etc/shadow','/proc/self/environ','/tmp/.ssh/key'):
            with self.assertRaises(ValueError):office_execution.safe_path(path)

    def test_valid_fixed_readonly_plan(self):
        plan=office_execution.normalize({'scope':{'local':['${workspace}']},'commands':[{'id':'check','title':'確認檔案','host':'local','argv':['stat','${workspace}/README.md'],'check':True}],'rollback':['這輪沒有修改，不需回復']})
        self.assertEqual(plan['commands'][0]['id'],'check')
        self.assertFalse(plan['baseline_consent_required'])

    def test_task_numbers_never_add_implicit_reference_or_host_access(self):
        import office_server as office
        from office_automation import Automation
        with patch.multiple(office,DATA_DIR=str(self.root/'data'),DB_PATH=str(self.root/'data/office.db'),AUTOMATION=None):
            office.init_db();auto=Automation(office)
            for number in range(1,10):
                task=office.create_task('owner','一般測試','只討論這份需求',reviewers='codex')
                if number not in (5,6,7,9):continue
                with office.tx() as c:
                    job_id=auto.enqueue(c,task['id'],'discuss','test-'+str(number),worker='claude')
                _,folder,_=auto.prepare(job_id)
                manifest=json.loads((folder/'manifest.json').read_text())
                self.assertFalse(manifest['baseline']);self.assertFalse(manifest['desktop_probe'])
                self.assertEqual(manifest['read_roots'],[])
                self.assertNotIn('prior_private_sessions',manifest['context'])
                self.assertNotIn('home_inventory',available_tools(manifest))

    def test_public_scanner_flags_generated_credentials_without_printing_values(self):
        sys.path.insert(0,str(ROOT/'tools'))
        from check_public_bundle import check
        p=self.root/'sample.txt';p.write_text(''.join(('gh','p_'))+'x'*40)
        findings=check([p],root=self.root)
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0][2],'供應商認證')

if __name__=='__main__':unittest.main()
