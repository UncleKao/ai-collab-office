#!/usr/bin/env python3
"""公開套件檢查：只輸出檔名、行號與類別，不回顯命中的機密內容。"""
import ipaddress
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
    '私鑰內容': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    '供應商認證': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})\b'),
    'Bot認證': re.compile(rb'\b[0-9]{6,12}:AA[A-Za-z0-9_-]{25,}\b'),
    'JWT認證': re.compile(rb'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b'),
    '私人網域': re.compile(rb'[a-zA-Z0-9_-]+\.tail[a-zA-Z0-9]+\.ts\.net'),
    '個人家目錄': re.compile(rb'/home/[A-Za-z0-9_.-]+/'),
}
DENIED_SUFFIXES={'.tok','.key','.pem','.p12','.pfx','.sqlite','.sqlite3','.db','.jsonl','.log','.zip','.gz','.tar'}
DENIED_PARTS={'.secrets','.ssh','.claude','.codex','.grok','data','context','secrets','node_modules','.venv'}

def paths(root=ROOT):
    if (root/'.git').exists():
        result=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True,check=True)
        return [root/value.decode() for value in result.stdout.split(b'\0') if value]
    return [p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts and '__pycache__' not in p.relative_to(root).parts]

def check(candidates,root=ROOT):
    findings=[]
    for path in candidates:
        rel=path.relative_to(root)
        if path.is_symlink():findings.append((str(rel),0,'符號連結'));continue
        if any(part in DENIED_PARTS for part in rel.parts) or path.suffix in DENIED_SUFFIXES or path.name=='office-config.json' or path.name=='.env':
            findings.append((str(rel),0,'執行期或機密檔案'));continue
        data=path.read_bytes()
        if b'\x00' in data:findings.append((str(rel),0,'未核准二進位檔'));continue
        for line_no,line in enumerate(data.splitlines(),1):
            for label,pattern in PATTERNS.items():
                if pattern.search(line):findings.append((str(rel),line_no,label))
            for match in re.finditer(rb'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',line):
                try:address=ipaddress.ip_address(match.group().decode())
                except ValueError:continue
                if address.is_loopback or address.is_unspecified or str(address)=='100.64.0.0' or address in ipaddress.ip_network('192.0.2.0/24') or address in ipaddress.ip_network('198.51.100.0/24') or address in ipaddress.ip_network('203.0.113.0/24'):continue
                findings.append((str(rel),line_no,'非範例網路位址'))
    return findings

def main():
    candidates=paths()
    findings=check(candidates)
    for name,line,label in findings:print(f'{name}:{line}：{label}')
    print(f'已檢查 {len(candidates)} 個交付檔案，命中 {len(findings)} 項。')
    if findings:raise SystemExit(1)
if __name__=='__main__':main()
