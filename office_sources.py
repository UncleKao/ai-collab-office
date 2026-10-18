"""AI 協作辦公室：office_sources。"""
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid


class SourcesBlocked(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _source_directory(path, create=False):
    """逐層以目錄描述元開啟，避免父層符號連結繞過白名單。"""
    path = Path(path).absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = os.open('/', flags)
    try:
        for part in path.parts[1:]:
            if part in ('.', '..'):
                raise ValueError('來源目錄格式不符')
            try:
                child = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _source_bytes(directory, name, limit=1_000_000):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('來源必須是大小合規的一般檔案')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('來源讀取中變更或超過大小限制')
    return data


def _source_manifest(raw, task, library=False):
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or type(manifest.get('task_id')) is not int or manifest['task_id'] != task['id'] or manifest.get('brief_sha256') != sha(task['brief'].strip().encode()):
        raise ValueError('來源清單與目前提案不符')
    files = manifest.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 30:
        raise ValueError('來源清單需有 1 至 30 個檔案')
    names = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError('來源檔案清單格式不符')
        name = entry.get('name')
        if not isinstance(name, str) or not name or len(name) > 240 or Path(name).name != name or name.startswith('.') or name == 'manifest.json' or '\\' in name or any(ord(x) < 32 for x in name) or name in names:
            raise ValueError('來源檔名不符或重複')
        names.add(name)
        digest = entry.get('sha256')
        if not isinstance(digest, str) or len(digest) != 64 or any(x not in '0123456789abcdef' for x in digest) or type(entry.get('required', True)) is not bool:
            raise ValueError('來源指紋或必要欄位格式不符')
    if library:
        authorization = manifest.get('authorization')
        resume = manifest.get('auto_resume_job_id')
        references = manifest.get('references', [])
        if manifest.get('owner') != 'codex' or not isinstance(authorization, str) or not 1 <= len(authorization.strip()) <= 4000:
            raise ValueError('來源庫缺少 owner 核准紀錄')
        if resume is not None and (type(resume) is not int or resume <= 0):
            raise ValueError('來源庫接續工作識別不符')
        if not isinstance(references, list) or len(references) > 20 or not all(isinstance(x, dict) and type(x.get('task_id')) is int and x['task_id'] > 0 for x in references):
            raise ValueError('來源庫參考工作格式不符')
    return manifest


def _source_members(directory, files):
    allowed = {'manifest.json', *(entry['name'] for entry in files)}
    if any(name not in allowed for name in os.listdir(directory)):
        raise ValueError('來源目錄含未列入核准清單的檔案')


def _write_source_missing(directory, name, data):
    """先完整寫入暫存檔，再以不覆寫既有檔案的方式加入資料包。"""
    temporary = '.source-' + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        except FileExistsError:
            if _source_bytes(directory, name) != data:
                raise ValueError('既有來源在恢復期間變更，未覆寫')
            return False
        return True
    finally:
        os.unlink(temporary, dir_fd=directory)


def _validated_library(data_dir, task):
    """同一份清單與逐檔指紋綁定的記憶體快照；回傳後不再重讀來源。"""
    task = dict(task)
    if type(task.get('id')) is not int or task['id'] <= 0:
        raise ValueError('工作識別不符')
    library = Path(data_dir) / 'source-library' / str(task['id'])
    try:
        library_fd = _source_directory(library)
    except FileNotFoundError:
        return None
    try:
        raw = _source_bytes(library_fd, 'manifest.json', 100_000)
        manifest = _source_manifest(raw, task, library=True)
        _source_members(library_fd, manifest['files'])
        contents = {}
        total = 0
        for entry in manifest['files']:
            data = _source_bytes(library_fd, entry['name'])
            total += len(data)
            if total > 2_000_000 or sha(data) != entry['sha256']:
                raise ValueError('來源庫內容與核准指紋不符或超過大小限制')
            data.decode('utf-8')
            contents[entry['name']] = data
        if _source_bytes(library_fd, 'manifest.json', 100_000) != raw:
            raise ValueError('來源庫清單在讀取期間變更')
        return raw, manifest, contents
    finally:
        os.close(library_fd)


def recover_sources(data_dir, task):
    """只由 owner 核准的本機來源庫補缺件；完整原件與既有差異均不覆寫。"""
    result = {'state': 'absent', 'revision': None, 'repaired': False, 'reason': '',
              'owner': None, 'resume_job_id': None, 'references': []}
    package_fd = None
    try:
        task = dict(task)
        snapshot = _validated_library(data_dir, task)
        if snapshot is None:
            return result
        raw, manifest, contents = snapshot
        result.update(revision=sha(raw), owner='codex', resume_job_id=manifest.get('auto_resume_job_id'), references=manifest.get('references', []))
        package = Path(data_dir) / 'sources' / str(task['id'])
        missing = []
        missing_manifest = True
        try:
            package_fd = _source_directory(package)
        except FileNotFoundError:
            pass
        if package_fd is not None:
            _source_members(package_fd, manifest['files'])
            try:
                current_raw = _source_bytes(package_fd, 'manifest.json', 100_000)
            except FileNotFoundError:
                current_raw = None
            if current_raw is not None:
                current = _source_manifest(current_raw, task)
                identity = lambda entries: sorted((x['name'], x['sha256'], x.get('required', True)) for x in entries)
                if identity(current['files']) != identity(manifest['files']):
                    raise ValueError('既有來源清單與核准來源庫不同，未覆寫')
                missing_manifest = False
        for name, data in contents.items():
            try:
                existing = _source_bytes(package_fd, name) if package_fd is not None else None
            except FileNotFoundError:
                existing = None
            if existing is None:
                missing.append(name)
            elif existing != data:
                raise ValueError('既有來源內容已變更，未覆寫')
        if package_fd is None:
            package_fd = _source_directory(package, create=True)
        for name in missing:
            result['repaired'] |= _write_source_missing(package_fd, name, contents[name])
        if missing_manifest:
            result['repaired'] |= _write_source_missing(package_fd, 'manifest.json', raw)
        result.update(state='ready', reason='核准來源已齊備')
    except (OSError, ValueError, KeyError, TypeError):
        # 不把原始例外、來源內容或不可信欄位帶進 API／日誌。
        result.update(state='blocked', reason='核准來源缺件、格式或指紋不符；Codex需核對原件，未覆寫既有差異', resume_job_id=None)
    finally:
        if package_fd is not None:
            os.close(package_fd)
    return result


def prepare_sources(data_dir, task, folder, parent_manifest=None, expected_revision=None):
    """複核沿用交付當輪的來源；新查核讀取 owner 登記且對應原提案的資料包。"""
    prior = (parent_manifest or {}).get('context', {}).get('sources', [])
    if expected_revision is not None:
        if prior:
            raise SourcesBlocked('原交付來源不能改接另一份來源核准版本')
        target_fd = None
        try:
            snapshot = _validated_library(data_dir, task)
            if snapshot is None or sha(snapshot[0]) != expected_revision:
                raise SourcesBlocked('來源核准版本已變更，停止舊輪自動續查')
            _, manifest, contents = snapshot
            target = Path(folder) / 'source-evidence'
            target_fd = _source_directory(target, create=True)
            if os.listdir(target_fd):
                raise SourcesBlocked('本輪來源快照已存在，停止重複準備')
            result = []
            for entry in manifest['files']:
                data = contents[entry['name']]
                if not _write_source_missing(target_fd, entry['name'], data):
                    raise SourcesBlocked('本輪來源快照已存在，停止重複準備')
                result.append({'path': str(target / entry['name']), 'sha256': sha(data),
                               'total_lines': len(data.decode('utf-8').splitlines()),
                               'required': entry.get('required', True),
                               'source': entry.get('source', entry['name']), 'captured_at': entry.get('captured_at')})
            return result
        except SourcesBlocked:
            raise
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SourcesBlocked('核准來源快照無法使用，停止舊輪自動續查') from e
        finally:
            if target_fd is not None:
                os.close(target_fd)
    package = Path(data_dir) / 'sources' / str(task['id'])
    if not prior:
        recovery = recover_sources(data_dir, task)
        if recovery['state'] == 'blocked':
            raise SourcesBlocked(recovery['reason'])
    if prior:
        entries = prior
    elif package.exists():
        try:
            if package.is_symlink() or (package/'manifest.json').is_symlink():
                raise ValueError('來源清單不接受符號連結')
            manifest = json.loads((package / 'manifest.json').read_text())
            if manifest['task_id'] != task['id'] or manifest['brief_sha256'] != sha(task['brief'].strip().encode()):
                raise ValueError('來源包與目前提案不符')
            entries = []
            for entry in manifest['files']:
                name = entry['name']
                if not name or Path(name).name != name or name.startswith('.'):
                    raise ValueError('來源名稱不符')
                entries.append({**entry, 'path': str(package / name)})
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SourcesBlocked('核准來源清單無法使用：' + str(e)) from e
    else:
        return []
    if not isinstance(entries, list) or not 1 <= len(entries) <= 30:
        raise SourcesBlocked('核准來源清單需有 1 至 30 個檔案')
    target = folder / 'source-evidence'
    target.mkdir(mode=0o700, exist_ok=True)
    result = []
    total = 0
    try:
        for entry in entries:
            source = Path(entry['path'])
            if any(p.is_symlink() for p in [source, *source.parents]):
                raise ValueError('來源不接受符號連結')
            if not source.is_file() or source.stat().st_size > 1_000_000:
                raise ValueError('來源缺件或過大：' + source.name)
            data = source.read_bytes()
            total += len(data)
            if total > 2_000_000 or sha(data) != entry['sha256']:
                raise ValueError('來源內容與核准指紋不符：' + source.name)
            text = data.decode('utf-8')
            destination = target / source.name
            if destination.exists():
                raise ValueError('本輪來源快照已存在或名稱重複')
            destination.write_bytes(data)
            os.chmod(destination, 0o600)
            result.append({'path': str(destination), 'sha256': sha(data),
                           'total_lines': len(text.splitlines()), 'required': entry.get('required', True),
                           'source': entry.get('source', source.name), 'captured_at': entry.get('captured_at')})
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise SourcesBlocked('待補資料：' + str(e)) from e
    return result


def validate_outcome(result):
    outcome = result.get('outcome', 'completed')
    if outcome not in ('completed', 'blocked'):
        raise ValueError('outcome 只能為 completed 或 blocked')
    blockers = result.get('blockers', [])
    if not isinstance(blockers, list) or len(blockers) > 20 or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 2000 for x in blockers):
        raise ValueError('blockers 格式不符')
    if outcome == 'blocked' and (not blockers or result.get('verdict', 'none') != 'none'):
        raise ValueError('待補資料需列出 blockers，verdict 使用 none')
    if outcome == 'completed' and blockers:
        raise ValueError('仍有 blockers 時請回報 blocked')
    return outcome


def validate_source_reads(job, events, result):
    if validate_outcome(result) == 'blocked' or job['kind'] == 'discuss':
        return
    # 退回內容錯誤也要讀指定原件；缺件必須使用 blocked，不能偽裝已完成查核。
    for source in job.get('context', {}).get('sources', []):
        if not source.get('required', True):
            continue
        ranges = []
        for event in events:
            read = event.get('file_read', {})
            if event.get('success') and event.get('tool') == 'read_file' and read.get('path') == source['path'] and read.get('sha256') == source['sha256']:
                ranges.append((read['start_line'], read['end_line']))
        end = 0
        for start, stop in sorted(ranges):
            if start > end + 1:
                break
            end = max(end, stop)
        if not ranges or end < source['total_lines']:
            raise ValueError('尚未完整讀取必要原件：' + source['path'] + '；請分段 read_file，缺件則提交 outcome=blocked')
