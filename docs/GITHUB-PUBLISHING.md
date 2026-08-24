# Publishing INTERNAL_RAG to your own GitHub

This document covers the **INTERNAL_RAG repository**, not a project where INTERNAL_RAG is temporarily installed.

## 1. Unpack a release

Unpack `internal-rag-v1.0-github-ready.zip` into a separate directory, e.g.:

```text
D:\GitHub\internal-rag
```

## 2. Initialize Git

```powershell
cd "D:\GitHub\internal-rag"
git init
git add .
git commit -m "Initial INTERNAL_RAG v1.0.1"
```

## 3. Create an empty repo on GitHub

Do not add a remote README/license if you want to avoid a first-commit conflict.

## 4. Connect remote and push

Use your own repo address:

```powershell
git branch -M main
git remote add origin <YOUR-REPO-ADDRESS>
git push -u origin main
```

Note: to push `.github/workflows/`, the git token needs the `workflow` scope. Without it, remove the workflow file before pushing, then add it via the GitHub UI or with a properly scoped token.

## 5. Release ZIP

The ZIP can be added as a GitHub Release asset. No need to commit the ZIP to the repo because `.gitignore` ignores `*.zip`.

## 6. What to preserve long-term

The most important files for future reconstruction:
- `README.md`,
- `START_HERE.md`,
- `docs/ARCHITECTURE.md`,
- `docs/PRIVACY-AND-GIT.md`,
- `docs/COMPATIBILITY.md`,
- `docs/CLI.md`,
- `CHANGELOG.md`,
- `VERSION`,
- `self_test.py`.

After updating Warp/OpenCode, run `self_test.py` and check the sources in `docs/COMPATIBILITY.md`.