# START HERE

Jeżeli wracasz do INTERNAL_RAG po miesiącach lub latach, wykonaj kolejno:

1. Zainstaluj do docelowego repo:

```powershell
python .\install.py "D:\sciezka\do\projektu"
```

2. Uruchom ponownie Warp/OpenCode.
3. W repo wykonaj:

```powershell
python .agents\skills\internal-rag\irag.py context --task "aktualne zadanie"
```

4. Jeżeli pojawi się `RECOVERY REQUIRED`, użyj `docs/RECOVERY.md`.
5. Przed publikacją repo uruchom `privacy_check.py`.
6. Aby całkowicie oczyścić finalny projekt, uruchom `uninstall.py`.

Pełna dokumentacja: `README.md` i katalog `docs/`.
