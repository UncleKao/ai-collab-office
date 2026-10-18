"""只提供使用者明確列入 read_roots 的參考資料。"""
from pathlib import Path
from office_config import CONFIG
from office_worker_tools import SECRET, forbidden, safe_root

def local_roots(worker):
    return [str(Path(p)) for p in CONFIG['workers'].get(worker,{}).get('read_roots',[]) if Path(p).exists() and safe_root(p)]
def missing_local_roots(worker):
    return [p+'（來源不存在或不在允許範圍）' for p in CONFIG['workers'].get(worker,{}).get('read_roots',[]) if not Path(p).exists() or not safe_root(p)]
def stage_assistant(folder):
    roots=[];descriptions=[];omitted=missing_local_roots('assistant')
    for index,rel in enumerate(local_roots('assistant')):
        source=Path(rel);target=Path(folder)/('context-'+str(index));count=size=0
        for path in ([source] if source.is_file() else sorted(source.rglob('*'))):
            if path.is_dir():continue
            if path.is_symlink() or forbidden(path) or not path.is_file() or not path.resolve().is_relative_to(source.resolve() if source.is_dir() else source.parent.resolve()):continue
            if path.stat().st_size>2_000_000:continue
            data=path.read_bytes()
            if SECRET.search(data.decode('utf-8',errors='replace')):continue
            if count>=100 or size+len(data)>4_000_000:omitted.append(str(path)+'（來源限額）');continue
            part=path.relative_to(source) if source.is_dir() else Path(source.name)
            dest=target/part;dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True);dest.write_bytes(data);dest.chmod(0o600)
            count+=1;size+=len(data)
        if count:roots.append(str(target));descriptions.append(f'{source.name}：{count} 檔、{size} bytes')
    return roots,descriptions,omitted
