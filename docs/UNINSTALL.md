# Uninstall (v1.0.1)

## Full cleanup of a repo

Windows:

```powershell
python .\uninstall.py "D:\project"
```

Linux/macOS:

```bash
python3 uninstall.py "/project"
```

The uninstaller creates a backup outside the repo, then removes `INTERNAL_RAG/`, the skill, the OpenCode integration, the INTERNAL_RAG section from `AGENTS.md`, the INTERNAL_RAG block from `.git/info/exclude`, and the local manifest.

To keep the memory: `--keep-memory`.

To skip the backup: `--no-backup`.

After uninstall, run `git status --short`. If INTERNAL_RAG was ever committed, uninstalling does not clean the history.