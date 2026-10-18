#!/usr/bin/env python3
"""初始化與診斷；不把登入碼印到終端。"""
import argparse
import json
from pathlib import Path
import shutil
import sys

def main():
    parser=argparse.ArgumentParser(description='AI 協作辦公室初始化與診斷')
    parser.add_argument('action',choices=('init','doctor','configure'))
    args=parser.parse_args()
    base=Path(__file__).resolve().parent
    if args.action=='configure':
        import os
        import uuid
        from office_config import load
        raw=sys.stdin.read(100_001)
        if len(raw)>100_000:raise SystemExit('設定檔過大')
        value=json.loads(raw)
        target=Path(os.environ.get('OFFICE_CONFIG',str(base/'office-config.json'))).expanduser().resolve()
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        temp=target.with_name('.office-config-'+uuid.uuid4().hex)
        try:
            fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
            load(temp)
            os.replace(temp,target)
        finally:temp.unlink(missing_ok=True)
        print('設定已驗證並寫入；重新啟動後生效。')
        return
    if args.action=='init':
        import os
        config=Path(os.environ.get('OFFICE_CONFIG',str(base/'office-config.json'))).expanduser()
        if not config.exists():
            config.parent.mkdir(parents=True,exist_ok=True)
            with config.open('x') as stream:
                stream.write((base/'office-config.example.json').read_text())
            config.chmod(0o600)
        from office_config import DATA_DIR,SECRET_DIR
        DATA_DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
        SECRET_DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
        from office_server import load_tokens
        identities=load_tokens()
        print(json.dumps({'結果':'初始化完成','設定檔':str(config.resolve()),'資料目錄':str(DATA_DIR),'負責人登入碼檔':str(SECRET_DIR/'owner.tok'),'身分數':len(identities),'提醒':'使用編輯器開啟登入碼檔；請勿貼進指令、日誌或問題回報。'},ensure_ascii=False,indent=2))
        return
    from office_config import CONFIG,DATA_DIR,SECRET_DIR
    errors=[];workers=[]
    for key,row in CONFIG['workers'].items():
        found=shutil.which(row['cli']) if '/' not in row['cli'] else str(Path(row['cli']).expanduser())
        exists=bool(found and Path(found).is_file())
        workers.append({'識別碼':key,'名稱':row['name'],'啟用':row['enabled'],'遠端':bool(row['host']),'本機CLI存在':exists,'已填模型':bool(row['model'])})
        if CONFIG['automation'] and row['enabled'] and (not row['model'] or (not row['host'] and not exists)):
            errors.append(key+' 尚未填妥模型或本機 CLI')
    print(json.dumps({'模式':'自動派工' if CONFIG['automation'] else '手動測試（不呼叫模型）','Python':sys.version.split()[0],
                      '資料目錄':str(DATA_DIR),'登入碼目錄':str(SECRET_DIR),'工作者':workers,'待處理':errors,
                      '限制':'只查設定與執行檔是否存在；不驗證供應商登入、模型權益或遠端連線。'},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
