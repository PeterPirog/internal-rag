# Architektura

```text
Warp / OpenCode
      │
      ├── AGENTS.md
      └── SKILL.md
              │
              ▼
            irag.py
      ┌───────┼─────────┐
      │       │         │
   context checkpoint search/remember
      │       │         │
      └───────┼─────────┘
              ▼
        INTERNAL_RAG/
```

`WORKING_STATE.md` to write-ahead checkpoint: cel, ukończone prace, stan w toku, blokery, ważne pliki i następne kroki.

`context` porównuje stan Git z ostatnim checkpointem i może zgłosić `RECOVERY REQUIRED`.

`checkpoint` zapisuje semantyczny stan i fingerprint zmian.

`guard` wykrywa zmiany wykonane po ostatnim checkpointcie.

Pamięć trwała z `decisions`, `knowledge`, `gotchas`, `failures`, `hypotheses` jest ładowana selektywnie.

OpenCode dostaje dodatkowe native tools i plugin checkpointów. Warp używa `AGENTS.md`, wspólnego skilla i lokalnego CLI.
