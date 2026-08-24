# Troubleshooting (v1.0.0)

`RECOVERY REQUIRED` nie jest błędem — zobacz `RECOVERY.md`. `irag.py diff` pokaże co się zmieniło.

`GUARD STALE` oznacza zmianę po ostatnim checkpointcie. Zapisz checkpoint i powtórz guard.

Jeżeli OpenCode nie widzi tools: zrestartuj OpenCode, sprawdź `.opencode/tools/`, worktree i w razie potrzeby użyj bezpośrednio `irag.py`.

Jeżeli Warp nie używa skilla: zrestartuj Warp, sprawdź `AGENTS.md`, `.agents/skills/internal-rag/SKILL.md` i jawnie poproś o `internal-rag`.

Jeżeli PowerShell blokuje `.ps1`, uruchom bezpośrednio `python .\install.py "D:\projekt"`.

Embeddings niedostępne: `irag.py doctor` i `irag.py embeddings-info` pokażą status. Zainstaluj `pip install sentence-transformers numpy` lub użyj BM25 (domyślnie).

`irag.py mcp` nie odpowiada: serwer czyta stdin linia po linii (JSON-RPC). Upewnij się że klient wysyła `initialize` przed `tools/call`.

Hooki git nie uruchamiają się: sprawdź `.git/hooks/` i `irag_hooks.py status`. Na Windows upewnij się że git używa bash (Git for Windows).

Backup jest domyślnie w `~/.internal-rag-backups/`. Jeżeli katalog domowy nie jest zapisywalny, skrypt użyje fallbacku obok repozytorium.

`irag.py doctor` zgłasza braki — uruchom `irag.py init` aby utworzyć strukturę katalogów.