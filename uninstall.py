#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, shutil, subprocess
from pathlib import Path

VERSION='0.4.0'
AGENTS_START='<!-- INTERNAL_RAG_START -->'; AGENTS_END='<!-- INTERNAL_RAG_END -->'
EXCLUDE_START='# >>> INTERNAL_RAG LOCAL-ONLY >>>'; EXCLUDE_END='# <<< INTERNAL_RAG LOCAL-ONLY <<<'
MANAGED_PATHS=[
 Path('.agents/skills/internal-rag'),
 Path('.opencode/tools/memory-search.ts'),Path('.opencode/tools/memory-context.ts'),Path('.opencode/tools/memory-checkpoint.ts'),Path('.opencode/tools/memory-guard.ts'),
 Path('.opencode/plugins/internal-rag-resilience.ts'),Path('.opencode/plugins/internal-rag-compaction.ts'),
 Path('.opencode/commands/memory.md'),Path('.opencode/commands/memory-check.md'),Path('.opencode/commands/checkpoint.md'),Path('.opencode/commands/memory-guard.md')]

def die(msg): print(f'\nERROR: {msg}'); raise SystemExit(1)
def git(target,*args,check=True):
 p=subprocess.run(['git','-C',str(target),*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if check and p.returncode: die(p.stderr.strip() or 'git failed')
 return p.stdout.strip()
def repo(path):
 path=path.expanduser().resolve(); p=subprocess.run(['git','-C',str(path),'rev-parse','--show-toplevel'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode: die(f'Not a Git repository: {path}')
 return Path(p.stdout.strip()).resolve()
def git_path(target,rel):
 p=Path(git(target,'rev-parse','--git-path',rel)); return (p if p.is_absolute() else target/p).resolve()
def backup_root(target,suffix):
 p=Path.home()/'.internal-rag-backups'/suffix
 try: p.mkdir(parents=True,exist_ok=True); return p
 except OSError:
  p=target.parent/'.internal-rag-backups'/suffix; p.mkdir(parents=True,exist_ok=True); return p
def backup(target,broot,rel):
 if broot is None: return
 s=target/rel
 if not s.exists(): return
 d=broot/rel; d.parent.mkdir(parents=True,exist_ok=True)
 shutil.copytree(s,d,dirs_exist_ok=True) if s.is_dir() else shutil.copy2(s,d)
def remove(p):
 if p.exists(): shutil.rmtree(p) if p.is_dir() else p.unlink()
def clean_agents(target,broot):
 p=target/'AGENTS.md'
 if not p.exists(): return
 text=p.read_text(encoding='utf-8',errors='replace')
 if AGENTS_START not in text or AGENTS_END not in text: return
 backup(target,broot,Path('AGENTS.md'))
 before=text.split(AGENTS_START,1)[0]; after=text.split(AGENTS_END,1)[1]
 if before.endswith('\n\n'): before=before[:-1]
 if after.startswith('\n'): after=after[1:]
 new=before+after
 if new.strip() in {'','# Agent Operating Contract'}: p.unlink(); print('Removed installer-created AGENTS.md')
 else: p.write_text(new,encoding='utf-8'); print('Removed INTERNAL_RAG section from AGENTS.md')
def clean_exclude(target,broot):
 p=git_path(target,'info/exclude')
 if not p.exists(): return
 text=p.read_text(encoding='utf-8',errors='replace')
 if EXCLUDE_START not in text or EXCLUDE_END not in text: return
 if broot is not None:
  d=broot/'_git_metadata'/'info-exclude'; d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)
 before=text.split(EXCLUDE_START,1)[0].rstrip(); after=text.split(EXCLUDE_END,1)[1].lstrip(); out=before+('\n\n' if before and after else '')+after
 p.write_text(out.rstrip()+('\n' if out.strip() else ''),encoding='utf-8'); print('Removed INTERNAL_RAG block from Git local exclude')
def tracked(target):
 out=git(target,'ls-files',check=False); r=[]
 for x in out.splitlines():
  if x.startswith('INTERNAL_RAG/') or x.startswith('.agents/skills/internal-rag/') or x.startswith('.opencode/tools/memory-') or x.startswith('.opencode/plugins/internal-rag') or x.startswith('.opencode/commands/memory') or x=='.opencode/commands/checkpoint.md': r.append(x)
 return r

def main():
 ap=argparse.ArgumentParser(description=f'Remove INTERNAL_RAG v{VERSION} from a Git repository.')
 ap.add_argument('repo',nargs='?'); ap.add_argument('--keep-memory',action='store_true'); ap.add_argument('--no-backup',action='store_true'); a=ap.parse_args()
 target=repo(Path(a.repo) if a.repo else Path.cwd()); stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S'); broot=None if a.no_backup else backup_root(target,f'{target.name}-uninstall-{stamp}')
 if not a.no_backup:
  for rel in MANAGED_PATHS: backup(target,broot,rel)
  backup(target,broot,Path('AGENTS.md'))
  if not a.keep_memory: backup(target,broot,Path('INTERNAL_RAG'))
 t=tracked(target)
 for rel in MANAGED_PATHS: remove(target/rel)
 if not a.keep_memory: remove(target/'INTERNAL_RAG')
 clean_agents(target,broot); clean_exclude(target,broot)
 m=git_path(target,'internal-rag'); shutil.rmtree(m,ignore_errors=True) if m.exists() else None
 for p in [target/'.agents/skills',target/'.agents',target/'.opencode/tools',target/'.opencode/plugins',target/'.opencode/commands',target/'.opencode']:
  if p.exists():
   try:p.rmdir()
   except OSError:pass
 print('\nUNINSTALL COMPLETE'); print('INTERNAL_RAG/ memory was preserved.' if a.keep_memory else 'INTERNAL_RAG/ was removed.')
 if not a.no_backup: print(f'Backup: {broot}')
 if t:
  print('\nIMPORTANT: INTERNAL_RAG-related paths were already tracked by Git. Deleting them now does not erase older commits.')
  for x in t[:20]: print('  tracked:',x)
if __name__=='__main__': main()
