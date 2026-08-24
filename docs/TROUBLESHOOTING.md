# Troubleshooting

`RECOVERY REQUIRED` nie jest błędem — zobacz `RECOVERY.md`.

`GUARD STALE` oznacza zmianę po ostatnim checkpointcie. Zapisz checkpoint i powtórz guard.

Jeżeli OpenCode nie widzi tools: zrestartuj OpenCode, sprawdź `.opencode/tools/`, worktree i w razie potrzeby użyj bezpośrednio `irag.py`.

Jeżeli Warp nie używa skilla: zrestartuj Warp, sprawdź `AGENTS.md`, `.agents/skills/internal-rag/SKILL.md` i jawnie poproś o `internal-rag`.

Jeżeli PowerShell blokuje `.ps1`, uruchom bezpośrednio `python .\install.py "D:\projekt"`.

Backup jest domyślnie w `~/.internal-rag-backups/`. Jeżeli katalog domowy nie jest zapisywalny, skrypt użyje fallbacku obok repozytorium.
