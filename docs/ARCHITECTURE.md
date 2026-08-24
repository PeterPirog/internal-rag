# Architektura (v1.0.0)

```text
Warp / OpenCode / Claude Code / Cursor
      │
      ├── AGENTS.md
      ├── SKILL.md
      └── .irag.yml (opcjonalna)
               │
               ▼
            irag.py  (CLI, zero-dep rdzeń)
       ┌───────┼─────────┬───────────┬──────────┐
       │       │         │           │          │
    context  checkpoint  search    remember    tasks
       │       │         │           │          │
       └───────┼─────────┴───────────┴──────────┘
               ▼
         INTERNAL_RAG/
       (WORKING_STATE, decisions, knowledge,
        gotchas, failures, hypotheses, sessions, archive)
```

### Rdzeń (zero zależności)
- `irag.py` — wszystkie komendy CLI.
- `WORKING_STATE.md` — write-ahead checkpoint.
- `.checkpoint.json` — fingerprint + metadane ostatniego checkpointu.
- `.tasks.json` — stos zadań (push/resume).
- `.fpcache.json` — cache fingerprint (invalidowany przy checkout).

### Retrieval
- Domyślnie: BM25 (k1=1.5, b=0.75) z MMR (lambda z config).
- Opcjonalnie: sentence-transformers (`irag_embeddings.py`), lazy-loaded, fallback do BM25.
- Stopwords, light stemming, status weighting (active/tentative/superseded/invalid).

### Cykl życia
- `context` porównuje fingerprint z ostatnim checkpointem → `RECOVERY REQUIRED` lub fresh.
- `checkpoint` zapisuje semantyczny stan + fingerprint.
- `guard` wykrywa zmiany po ostatnim checkpointcie.
- `compact` archiwizuje i trimuje WORKING_STATE.
- `push`/`resume` stos zadań z snapshotem stanu.
- `remember`/`show`/`update`/`supersede`/`forget`/`link` — CRUD pamięci trwałej.
- `export`/`import` — transfer JSON między projektami.

### Integracje
- OpenCode: tools (`memory-*`), plugin (auto-checkpoint + compact), commands (`/memory*`, `/checkpoint`).
- Warp: `AGENTS.md` + skill.
- MCP: `irag.py mcp` (JSON-RPC stdio).
- Git hooks (opcjonalne): post-commit auto-checkpoint, post-checkout invalidate, pre-push warn.

### Prywatność
- Domyślnie local-only via `.git/info/exclude`.
- `privacy_check.py` audytuje tracked files, wzorce sekretów, historię git.
- `INTERNAL_RAG/` i tools nigdy nie powinny być commitowane (chyba że `--share-tools`).

Pamięć trwała z `decisions`, `knowledge`, `gotchas`, `failures`, `hypotheses` jest ładowana selektywnie przez retrieval, nigdy w całości.