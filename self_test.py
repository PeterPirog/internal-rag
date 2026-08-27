#!/usr/bin/env python3
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent

def run(cmd,cwd,expected=0,env=None):
 e=os.environ.copy(); e.update(env or {})
 p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=e)
 if p.returncode!=expected:
  print('COMMAND FAILED:',cmd); print('EXPECTED',expected,'GOT',p.returncode); print('STDOUT:\n',p.stdout); print('STDERR:\n',p.stderr); raise SystemExit(1)
 return p

def init_repo(p,with_agents=False,env=None):
 run(['git','init'],p,env=env); run(['git','config','user.email','test@example.com'],p,env=env); run(['git','config','user.name','INTERNAL_RAG Test'],p,env=env)
 (p/'app.py').write_text("print('v1')\n",encoding='utf-8')
 if with_agents: (p/'AGENTS.md').write_text('# Existing project rules\n\nKeep this exact line.\n',encoding='utf-8')
 run(['git','add','.'],p,env=env); run(['git','commit','-m','init'],p,env=env)

def need(c,m):
 if not c: raise AssertionError(m)

def main():
 tmp=Path(tempfile.mkdtemp(prefix='internal-rag-selftest-')); home=tmp/'home'; home.mkdir(); env={'HOME':str(home),'USERPROFILE':str(home)}; print('test root:',tmp)
 try:
  # Fresh local install
  r=tmp/'fresh'; r.mkdir(); init_repo(r,env=env)
  x=run([sys.executable,str(HERE/'install.py'),str(r)],HERE,env=env); need('PROJECT INSTALLATION COMPLETE' in x.stdout,'install')
  need(run(['git','status','--short'],r,env=env).stdout.strip()=='','local install polluted git status')
  cli=r/'.agents/skills/internal-rag/irag.py'
  c=run([sys.executable,str(cli),'context','--task','modify app'],r,env=env); need('recovery_required: NO' in c.stdout,c.stdout)
  run([sys.executable,str(cli),'checkpoint','--reason','task-start'],r,env=env); need('GUARD OK' in run([sys.executable,str(cli),'guard'],r,env=env).stdout,'guard')
  (r/'app.py').write_text("print('v2')\n",encoding='utf-8')
  need('GUARD STALE' in run([sys.executable,str(cli),'guard'],r,expected=2,env=env).stdout,'stale guard')
  need('RECOVERY REQUIRED' in run([sys.executable,str(cli),'context','--task','resume'],r,env=env).stdout,'recovery')
  run([sys.executable,str(cli),'checkpoint','--reason','recovery','--completed','app.py modified','--next','test app'],r,env=env)
  run([sys.executable,str(cli),'guard'],r,env=env)
  need('RESULT: PASS' in run([sys.executable,str(HERE/'privacy_check.py'),str(r)],HERE,env=env).stdout,'privacy pass')
  sec=r/'INTERNAL_RAG/knowledge/secret-test.md'; sec.write_text('secret = TEST_SECRET_VALUE_1234567890\n',encoding='utf-8')
  need('Potential secrets' in run([sys.executable,str(HERE/'privacy_check.py'),str(r),'--no-history'],HERE,expected=3,env=env).stdout,'secret detector'); sec.unlink()
  run([sys.executable,str(HERE/'uninstall.py'),str(r)],HERE,env=env)
  need(not (r/'INTERNAL_RAG').exists(),'memory remains'); need(not (r/'AGENTS.md').exists(),'created AGENTS remains')
  need(run(['git','status','--short'],r,env=env).stdout.strip()=='M app.py','uninstall residue')

  # Existing tracked AGENTS should restore exactly
  r2=tmp/'existing'; r2.mkdir(); init_repo(r2,with_agents=True,env=env); orig=(r2/'AGENTS.md').read_text(encoding='utf-8')
  run([sys.executable,str(HERE/'install.py'),str(r2)],HERE,env=env)
  need(run(['git','status','--short'],r2,env=env).stdout.strip()=='M AGENTS.md','tracked agents status')
  run([sys.executable,str(HERE/'uninstall.py'),str(r2)],HERE,env=env)
  need((r2/'AGENTS.md').read_text(encoding='utf-8')==orig,'AGENTS not restored exactly')
  need(run(['git','status','--short'],r2,env=env).stdout.strip()=='','dirty after restore')

  # Shared-tools mode
  r3=tmp/'shared'; r3.mkdir(); init_repo(r3,env=env)
  run([sys.executable,str(HERE/'install.py'),str(r3),'--share-tools'],HERE,env=env)
  st=run(['git','status','--short'],r3,env=env).stdout
  need('INTERNAL_RAG/' not in st,'memory visible in shared mode'); need('.agents/' in st or '.opencode/' in st,'tools not visible in shared mode')

  # Sparse retrieval smoke test
  run([sys.executable,str(HERE/'install.py'),str(r3)],HERE,env=env)
  cli3=r3/'.agents/skills/internal-rag/irag.py'
  run([sys.executable,str(cli3),'remember','--type','decision','--title','Use Postgres','--body','Use Postgres for database','--tags','db,postgres','--force'],r3,env=env)
  run([sys.executable,str(cli3),'remember','--type','gotcha','--title','Pool timeout','--body','asyncpg pool exhausts under load','--tags','db,async','--force'],r3,env=env)
  sr=run([sys.executable,str(cli3),'search','--query','asyncpg pool','--limit','5'],r3,env=env)
  need('pool' in sr.stdout.lower(),'sparse retrieval smoke: pool not found')
  need('asyncpg' in sr.stdout.lower(),'sparse retrieval smoke: asyncpg not found')

  # SQLite index smoke test
  run([sys.executable,str(cli3),'index','--rebuild'],r3,env=env)
  ix=run([sys.executable,str(cli3),'index','--status'],r3,env=env)
  need('SQLite' in ix.stdout or 'indexed' in ix.stdout.lower(),'sqlite index status')
  sr2=run([sys.executable,str(cli3),'search','--query','asyncpg','--limit','3'],r3,env=env)
  need('asyncpg' in sr2.stdout.lower(),'sqlite index: search after rebuild')

  print('\nSELF TEST PASS')
  print('- local-only install')
  print('- recovery + guard')
  print('- privacy check + secret detector')
  print('- clean uninstall')
  print('- existing AGENTS preservation')
  print('- shared-tools mode')
  print('- sparse retrieval smoke')
  print('- SQLite index smoke')
 finally:
  shutil.rmtree(tmp,ignore_errors=True)
if __name__=='__main__': main()
