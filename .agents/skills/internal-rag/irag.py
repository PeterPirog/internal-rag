#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, subprocess, sys, unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

VERSION='0.4.0'
ALLOWED_TYPES={'decision','knowledge','constraint','gotcha','failure','hypothesis','session'}
ALLOWED_STATUS={'active','tentative','superseded','invalid','archived'}
TYPE_DIR={'decision':'decisions','knowledge':'knowledge','constraint':'knowledge','gotcha':'gotchas','failure':'failures','hypothesis':'hypotheses','session':'sessions'}
SKIP_SEARCH={'README.md','INDEX.md','WORKING_STATE.md'}
INFRA_PREFIXES=('INTERNAL_RAG/','.agents/skills/internal-rag/','.opencode/tools/memory-','.opencode/plugins/internal-rag','.opencode/commands/memory','.opencode/commands/checkpoint')
INFRA_EXACT={'AGENTS.md'}

def project_root():
    p=Path.cwd().resolve()
    try:
        out=subprocess.check_output(['git','-C',str(p),'rev-parse','--show-toplevel'],stderr=subprocess.DEVNULL,text=True).strip()
        if out: return Path(out).resolve()
    except Exception: pass
    return p
ROOT=project_root(); RAG=ROOT/'INTERNAL_RAG'; WORKING=RAG/'WORKING_STATE.md'; CHECKPOINT=RAG/'.checkpoint.json'

def now(): return dt.datetime.now().astimezone().isoformat(timespec='seconds')
def today(): return dt.date.today().isoformat()
def git(*args, binary=False):
    try: return subprocess.check_output(['git','-C',str(ROOT),*args],stderr=subprocess.DEVNULL,text=not binary)
    except Exception: return b'' if binary else ''
def git_text(*args):
    x=git(*args); return x.strip() if isinstance(x,str) else ''
def norm(p): return p.replace('\\','/').lstrip('./')
def infra(p):
    p=norm(p); return p in INFRA_EXACT or any(p.startswith(x) for x in INFRA_PREFIXES)

def tracked_diff_hash(h, cached=False):
    cmd=['git','-C',str(ROOT),'diff','--binary','--no-ext-diff']
    if cached: cmd.append('--cached')
    cmd += ['--','.',':(exclude)INTERNAL_RAG/**',':(exclude)AGENTS.md',':(exclude).agents/skills/internal-rag/**',':(exclude).opencode/tools/memory-*',':(exclude).opencode/plugins/internal-rag*',':(exclude).opencode/commands/memory*',':(exclude).opencode/commands/checkpoint*']
    try:
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        while True:
            chunk=p.stdout.read(1024*1024)
            if not chunk: break
            h.update(chunk)
        p.wait()
    except Exception: h.update(b'DIFF_ERROR')

def untracked_files():
    raw=git('ls-files','--others','--exclude-standard','-z',binary=True)
    if not raw: return []
    return [norm(x) for x in raw.decode('utf-8',errors='replace').split('\0') if x and not infra(x)]

def project_fingerprint():
    h=hashlib.sha256(); h.update(git_text('rev-parse','HEAD').encode())
    tracked_diff_hash(h,False); tracked_diff_hash(h,True)
    for rel in sorted(untracked_files()):
        h.update(rel.encode()); p=ROOT/rel
        try:
            if p.is_file():
                with p.open('rb') as f:
                    while True:
                        c=f.read(1024*1024)
                        if not c: break
                        h.update(c)
        except Exception: h.update(b'ERR')
    return h.hexdigest()

def changed_entries():
    raw=git('status','--porcelain=v1','-z','-uall',binary=True)
    if not raw: return []
    parts=raw.decode('utf-8',errors='replace').split('\0'); out=[]; i=0
    while i<len(parts):
        rec=parts[i]; i+=1
        if not rec or len(rec)<4: continue
        st=rec[:2]; path=norm(rec[3:])
        if 'R' in st or 'C' in st:
            if i<len(parts) and parts[i]:
                old=norm(parts[i]); i+=1
                if not infra(old): out.append((st+':old',old))
        if not infra(path): out.append((st,path))
    seen=set(); result=[]
    for x in out:
        if x not in seen: seen.add(x); result.append(x)
    return result

def default_working():
    return f'''# Current Working State\n\nupdated: {now()}\nbranch: {git_text('branch','--show-current') or 'unknown'}\nbase_commit: {git_text('rev-parse','--short','HEAD') or 'unknown'}\n\n## Objective\n\nNo active objective yet.\n\n## Current request\n\nNone.\n\n## Current phase\n\nIdle.\n\n## Completed\n\n- None.\n\n## In progress\n\n- None.\n\n## Blockers\n\n- None.\n\n## Important active decisions\n\n- None.\n\n## Relevant files\n\n- None.\n\n## Next actions\n\n1. Define the task.\n\n## Checkpoint health\n\n- No task has started.\n\n## Recovery snapshot\n\n- None.\n\n## Memory to retrieve if needed\n\n- None.\n'''

def get_section(text,name):
    m=re.search(rf'(?ms)^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)',text)
    return m.group(1).strip() if m else ''
def set_section(text,name,body):
    body=body.strip() or '- None.'; pat=rf'(?ms)^## {re.escape(name)}\s*\n.*?(?=^## |\Z)'
    repl=f'## {name}\n\n{body}\n\n'
    if re.search(pat,text): return re.sub(pat,repl,text).rstrip()+"\n"
    return text.rstrip()+f'\n\n{repl}'
def set_header(text,key,value):
    pat=rf'(?m)^{re.escape(key)}:.*$'
    if re.search(pat,text): return re.sub(pat,f'{key}: {value}',text)
    marker='# Current Working State\n'
    if text.startswith(marker): return marker+f'\n{key}: {value}\n'+text[len(marker):].lstrip('\n')
    return f'{key}: {value}\n'+text

def save_working(text): RAG.mkdir(exist_ok=True); WORKING.write_text(text.rstrip()+"\n",encoding='utf-8')
def load_checkpoint():
    try: return json.loads(CHECKPOINT.read_text(encoding='utf-8'))
    except Exception: return {}
def save_checkpoint(reason):
    data={'version':VERSION,'at':now(),'reason':reason,'fingerprint':project_fingerprint(),'branch':git_text('branch','--show-current'),'head':git_text('rev-parse','--short','HEAD')}
    CHECKPOINT.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding='utf-8'); return data

def init_repo():
    existed=WORKING.exists(); RAG.mkdir(exist_ok=True)
    for d in ['decisions','knowledge','gotchas','failures','hypotheses','sessions','archive']: (RAG/d).mkdir(exist_ok=True)
    if not existed:
        save_working(default_working()); save_checkpoint('init')
    rebuild_index(); print(f'Initialized INTERNAL_RAG (irag {VERSION})')

def listify(s,numbered=False):
    if s is None: return None
    xs=[x.strip() for x in s.split(';') if x.strip()]
    if not xs: return '- None.'
    return '\n'.join((f'{i}. {x}' if numbered else f'- {x}') for i,x in enumerate(xs,1))

def checkpoint(args):
    if not WORKING.exists(): init_repo()
    text=WORKING.read_text(encoding='utf-8',errors='replace')
    if args.task: text=set_section(text,'Current request',args.task)
    if args.objective: text=set_section(text,'Objective',args.objective)
    if args.phase: text=set_section(text,'Current phase',args.phase)
    for arg,sec,num in [('completed','Completed',False),('in_progress','In progress',False),('blockers','Blockers',False),('decisions','Important active decisions',False),('next','Next actions',True),('memory','Memory to retrieve if needed',False)]:
        v=listify(getattr(args,arg),num)
        if v is not None: text=set_section(text,sec,v)
    entries=changed_entries(); files='\n'.join(f'- `{s}` {p}' for s,p in entries[:50]) or '- No project-code changes detected.'
    if len(entries)>50: files+=f'\n- ... {len(entries)-50} more'
    text=set_section(text,'Relevant files',files)
    text=set_section(text,'Recovery snapshot',f'- Checkpoint reason: {args.reason}\n- Branch: {git_text("branch","--show-current") or "unknown"}\n- HEAD: {git_text("rev-parse","--short","HEAD") or "unknown"}\n{files}')
    text=set_section(text,'Checkpoint health','- CHECKPOINT CURRENT at save time.\n- Run `irag.py guard` before final response.')
    text=set_header(text,'updated',now()); text=set_header(text,'branch',git_text('branch','--show-current') or 'unknown'); text=set_header(text,'base_commit',git_text('rev-parse','--short','HEAD') or 'unknown')
    save_working(text); data=save_checkpoint(args.reason)
    print('CHECKPOINT SAVED'); print('reason:',args.reason); print('fingerprint:',data['fingerprint'][:16]); print('changed_paths:',len(entries))

def context(task,limit):
    if not WORKING.exists(): init_repo()
    text=WORKING.read_text(encoding='utf-8',errors='replace'); cp=load_checkpoint(); cur=project_fingerprint(); saved=cp.get('fingerprint')
    recovery=(not saved) or saved!=cur
    text=set_section(text,'Current request',task)
    if get_section(text,'Objective') in ('','No active objective yet.','None.','- None.'): text=set_section(text,'Objective',task)
    health='- RECOVERY REQUIRED: project code differs from the last checkpoint.\n- Inspect `git status` and `git diff`, reconstruct state, checkpoint it, then run guard.' if recovery else '- Checkpoint fingerprint matches current project state.\n- Create a task-start checkpoint before the first new code edit.'
    text=set_section(text,'Checkpoint health',health); text=set_header(text,'updated',now()); save_working(text)
    print('# INTERNAL_RAG CONTEXT PACKET'); print('irag_version:',VERSION); print('task:',task); print('recovery_required:','YES' if recovery else 'NO')
    if recovery: print('\n!!! RECOVERY REQUIRED !!!\nInspect git status/diff and checkpoint recovered state BEFORE new edits.')
    print('\n## WORKING_STATE\n'+WORKING.read_text(encoding='utf-8',errors='replace')[:10000].rstrip())
    print('\n## CANDIDATE MEMORIES'); results=search(task,limit)
    if not results: print('No relevant durable memories found.')
    for i,(score,p,fm,snip) in enumerate(results,1): print(f'{i}. {p.relative_to(ROOT)} [{fm.get("type","?")}/{fm.get("status","?")}] score={score:.1f}\n   {snip}')
    print('\n## NEXT'); print('RECOVER -> CHECKPOINT -> GUARD OK -> continue.' if recovery else 'Checkpoint before first code edit, then continue.')

def guard():
    cp=load_checkpoint(); saved=cp.get('fingerprint'); cur=project_fingerprint()
    if not saved:
        print('GUARD STALE: no checkpoint fingerprint.'); return 2
    if saved!=cur:
        print('GUARD STALE: project code changed after the last checkpoint.')
        for s,p in changed_entries()[:40]: print(f'- `{s}` {p}')
        return 2
    print('GUARD OK'); print('fingerprint:',cur[:16]); return 0

def slugify(text):
    text=unicodedata.normalize('NFKD',text); text=''.join(c for c in text if not unicodedata.combining(c)); return re.sub(r'[^a-z0-9]+','-',text.lower()).strip('-')[:72] or 'memory'
def parse_fm(text):
    if not text.startswith('---\n'): return {}
    end=text.find('\n---',4)
    if end<0: return {}
    data={}; current=None
    for raw in text[4:end].splitlines():
        if re.match(r'^\s+-\s+',raw) and current:
            data.setdefault(current,[]).append(re.sub(r'^\s+-\s+','',raw).strip()); continue
        m=re.match(r'^([A-Za-z0-9_]+):\s*(.*)$',raw)
        if m:
            k,v=m.group(1),m.group(2).strip(); current=None
            if not v: data[k]=[]; current=k
            else: data[k]=v.strip('"\'')
    return data
def memory_files():
    if not RAG.exists(): return []
    return sorted(p for p in RAG.rglob('*.md') if 'archive' not in p.parts and p.name not in SKIP_SEARCH)
def search(query,limit=8):
    toks=list(dict.fromkeys(re.findall(r'[A-Za-z0-9_./:@+-]{2,}',query.lower()))); out=[]
    for p in memory_files():
        text=p.read_text(encoding='utf-8',errors='replace'); low=text.lower(); fm=parse_fm(text); status=str(fm.get('status','active')).lower()
        if status in {'invalid','archived'}: continue
        rel=str(p.relative_to(ROOT)).lower(); header='\n'.join(text.splitlines()[:25]).lower(); score=0
        for t in toks: score+=rel.count(t)*8+header.count(t)*5+min(low.count(t),8)*1.25
        if status=='active': score+=1
        elif status=='superseded': score-=4
        if score>0: out.append((score,p,fm,' '.join(text.split())[:420]))
    out.sort(key=lambda x:(-x[0],str(x[1]))); return out[:limit]
def remember(args):
    status='tentative' if args.type=='hypothesis' and args.status=='active' else args.status; folder=RAG/TYPE_DIR[args.type]; folder.mkdir(parents=True,exist_ok=True)
    d=dt.date.today().strftime('%Y%m%d'); path=folder/f'{d}-{slugify(args.title)}.md'; n=2
    while path.exists(): path=folder/f'{d}-{slugify(args.title)}-{n}.md'; n+=1
    def yl(name,val):
        xs=[x.strip() for x in val.split(',') if x.strip()]; return f'{name}: []\n' if not xs else f'{name}:\n'+''.join(f'  - {x}\n' for x in xs)
    content='---\n'+f'id: mem-{d}-{slugify(args.title)[:40]}\ntype: {args.type}\nstatus: {status}\ncreated: {today()}\nverified: {today() if args.type!="hypothesis" else "unverified"}\n'+yl('scope',args.scope)+yl('tags',args.tags)+yl('sources',args.evidence)+'---\n\n'+f'# {args.title}\n\n## Knowledge\n\n{args.body.strip()}\n\n## Consequence\n\n{(args.consequence or "To be determined.").strip()}\n'
    path.write_text(content,encoding='utf-8'); rebuild_index(); print(path.relative_to(ROOT))
def rebuild_index():
    RAG.mkdir(exist_ok=True); entries=[]
    for p in memory_files():
        text=p.read_text(encoding='utf-8',errors='replace'); fm=parse_fm(text); title=next((x[2:].strip() for x in text.splitlines() if x.startswith('# ')),p.stem); entries.append((str(fm.get('type','unknown')),str(fm.get('status','unknown')),title,p.relative_to(ROOT)))
    entries.sort(key=lambda x:(x[0],x[2].lower())); lines=['# Memory Index','','Generated by `irag.py index`. Read entries lazily.','']; cur=None
    for typ,status,title,rel in entries:
        if typ!=cur: cur=typ; lines += [f'## {typ}','']
        lines.append(f'- `{rel}` — **{title}** [{status}]')
    if not entries: lines.append('No durable memories yet.')
    (RAG/'INDEX.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(f'Indexed {len(entries)} memories.')
def validate():
    errors=0; warnings=0
    if not WORKING.exists(): print('ERROR INTERNAL_RAG/WORKING_STATE.md missing'); errors+=1
    for p in memory_files():
        fm=parse_fm(p.read_text(encoding='utf-8',errors='replace')); rel=p.relative_to(ROOT)
        for k in ('id','type','status','created'):
            if not fm.get(k): print(f'ERROR {rel}: missing `{k}`'); errors+=1
        if fm.get('type') and fm.get('type') not in ALLOWED_TYPES: errors+=1
        if fm.get('status') and fm.get('status') not in ALLOWED_STATUS: errors+=1
    print(f'Validation complete: {errors} error(s), {warnings} warning(s).'); return 1 if errors else 0

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--version',action='version',version=VERSION); sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('init'); p=sub.add_parser('context'); p.add_argument('--task',required=True); p.add_argument('--limit',type=int,default=6)
    p=sub.add_parser('checkpoint'); p.add_argument('--reason',default='manual'); p.add_argument('--task'); p.add_argument('--objective'); p.add_argument('--phase'); p.add_argument('--completed'); p.add_argument('--in-progress',dest='in_progress'); p.add_argument('--blockers'); p.add_argument('--decisions'); p.add_argument('--next'); p.add_argument('--memory')
    sub.add_parser('guard'); p=sub.add_parser('search'); p.add_argument('--query',required=True); p.add_argument('--limit',type=int,default=8)
    p=sub.add_parser('remember'); p.add_argument('--type',required=True,choices=sorted(ALLOWED_TYPES)); p.add_argument('--status',default='active',choices=sorted(ALLOWED_STATUS)); p.add_argument('--title',required=True); p.add_argument('--scope',default=''); p.add_argument('--tags',default=''); p.add_argument('--evidence',default=''); p.add_argument('--body',required=True); p.add_argument('--consequence',default='')
    sub.add_parser('index'); sub.add_parser('validate'); a=ap.parse_args()
    if a.cmd=='init': init_repo()
    elif a.cmd=='context': context(a.task,a.limit)
    elif a.cmd=='checkpoint': checkpoint(a)
    elif a.cmd=='guard': raise SystemExit(guard())
    elif a.cmd=='search':
        r=search(a.query,a.limit); print('No matching durable memories.' if not r else '\n'.join(f'{i}. {p.relative_to(ROOT)} score={s:.1f}\n   {sn}' for i,(s,p,fm,sn) in enumerate(r,1)))
    elif a.cmd=='remember': remember(a)
    elif a.cmd=='index': rebuild_index()
    elif a.cmd=='validate': raise SystemExit(validate())
if __name__=='__main__': main()
