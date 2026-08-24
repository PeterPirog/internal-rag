# START HERE

If you return to INTERNAL_RAG after months or years, follow these steps:

1. Install into the target repo:

```powershell
python .\install.py "D:\path\to\project"
```

2. Restart Warp/OpenCode.
3. In the repo run:

```powershell
python .agents\skills\internal-rag\irag.py context --task "current task"
```

4. If `RECOVERY REQUIRED` appears, follow `docs/RECOVERY.md`.
5. Before publishing the repo run `privacy_check.py`.
6. To fully clean the final project, run `uninstall.py`.
7. Run `irag.py doctor` for a health check.

Full documentation: `README.md` and the `docs/` directory.