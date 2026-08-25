#!/usr/bin/env python3
from __future__ import annotations
import argparse,re,subprocess
from pathlib import Path
EXCLUDE_START='# >>> MCP_LIGHT_MEMORY LOCAL-ONLY >>>'; EXCLUDE_END='# <<< MCP_LIGHT_MEMORY LOCAL-ONLY <<<'
PATTERNS=[
 ('private-key',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
 ('github-token',re.compile(r'\bgh[pousr]_[A-Za-z0-9_]{20,}\b')),
 ('openai-key',re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b')),
 ('aws-access-key',re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
 ('bearer-token',re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}\b')),
 ('credential-url',re.compile(r'(?i)\bhttps?://[^/\s:@]+:[^/\s@]+@')),
 ('password-assignment',re.compile(r'(?i)\b(?:password|passwd|pwd)\s*[:=]\s*[\"\']?[^ \t\r\n\"\']{8,}')),
 ('secret-assignment',re.compile(r'(?i)\b(?:api[_-]?key|secret|token)\s*[:=]\s*[\"\']?[^ \t\r\n\"\']{12,}'))]
def git(t,*a,check=True):
 p=subprocess.run(['git','-C',str(t),*a],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if check and p.returncode: raise RuntimeError(p.stderr.strip())
 return p.returncode,p.stdout.strip(),p.stderr.strip()
def repo(p):
 p=p.expanduser().resolve(); c,o,_=git(p,'rev-parse','--show-toplevel',check=False)
 if c: raise SystemExit(f'ERROR: not a Git repository: {p}')
 return Path(o).resolve()
def gp(t,r):
 _,o,_=git(t,'rev-parse','--git-path',r); p=Path(o); return (p if p.is_absolute() else t/p).resolve()
def managed(x): return x.startswith('INTERNAL_RAG/') or x.startswith('.agents/skills/internal-rag/') or x.startswith('.opencode/tools/memory-') or x.startswith('.opencode/plugins/internal-rag') or x.startswith('.opencode/commands/memory') or x=='.opencode/commands/checkpoint.md' or x=='.irag.yml' or x=='requirements-optional.txt' or x=='pack.py' or '.index.sqlite3' in x
def scan(t):
 root=t/'INTERNAL_RAG'; hits=[]
 if not root.exists(): return hits
 for p in root.rglob('*'):
  if not p.is_file(): continue
  try:
   if p.stat().st_size>5*1024*1024: continue
   s=p.read_text(encoding='utf-8',errors='replace')
  except Exception: continue
  for label,rx in PATTERNS:
   if rx.search(s): hits.append((str(p.relative_to(t)).replace('\\','/'),label))
 return hits
def main():
 ap=argparse.ArgumentParser(description='Audit INTERNAL_RAG privacy and Git exposure.'); ap.add_argument('repo',nargs='?'); ap.add_argument('--no-history',action='store_true'); a=ap.parse_args(); t=repo(Path(a.repo) if a.repo else Path.cwd()); crit=warn=0
 print(f'INTERNAL_RAG PRIVACY CHECK -> {t}')
 ep=gp(t,'info/exclude'); et=ep.read_text(encoding='utf-8',errors='replace') if ep.exists() else ''
 if EXCLUDE_START in et and EXCLUDE_END in et: print(f'[OK] Local Git exclusion is installed: {ep}')
 else: print(f'[WARN] INTERNAL_RAG local exclude block not found: {ep}'); warn+=1
 _,ls,_=git(t,'ls-files'); tr=[x for x in ls.splitlines() if managed(x)]
 if tr:
  print('[CRITICAL] INTERNAL_RAG-related files are currently tracked by Git:'); [print(' ',x) for x in tr[:30]]; crit+=1
 else: print('[OK] No INTERNAL_RAG memory/tool files are currently tracked by Git.')
 hits=scan(t)
 if hits:
  print('[CRITICAL] Potential secrets/credentials found in INTERNAL_RAG memory. Only file names and detector labels are shown.')
  for p,l in hits[:30]: print(f'  {p}: {l}')
  crit+=1
 else: print('[OK] No common credential patterns detected in INTERNAL_RAG.')
 if not a.no_history:
  _,h,_=git(t,'log','--all','--format=','--name-only','--','INTERNAL_RAG',check=False)
  if h.strip(): print('[CRITICAL] Git history contains paths under INTERNAL_RAG/. Deleting current files does not remove old commits.'); crit+=1
  else: print('[OK] No INTERNAL_RAG paths detected in Git commit history.')
 if crit: print(f'\nRESULT: FAIL ({crit} critical issue(s), {warn} warning(s))'); raise SystemExit(3)
 if warn: print(f'\nRESULT: WARN ({warn} warning(s))'); raise SystemExit(2)
 print('\nRESULT: PASS')
if __name__=='__main__': main()
