# Installation (v1.7.0)

## Requirements

```text
python --version   # 3.8+
git --version
```

The target project should be a Git repository. If it is not, the installer will ask whether to initialize one (Git is required for fingerprinting, recovery detection, and checkpoints).

## Recommended mode: local-only

Windows:

```powershell
python .\install.py "D:\projects\my-project"
```

Linux/macOS:

```bash
python3 install.py "/home/user/projects/my-project"
```

On success you will see `INSTALLATION COMPLETE`.

The installer:
1. creates a backup,
2. preserves existing memory,
3. installs the skill and CLI (`irag.py`, `irag_embeddings.py`, `irag_hooks.py`),
4. installs the OpenCode integration (tools, plugin, commands),
5. updates only the marked section of `AGENTS.md`,
6. configures `.git/info/exclude` (including `.irag.yml`),
7. runs `init` and `validate`.

## Share-tools mode

If you want to commit integrations into the target project:

```text
python install.py "D:\project" --share-tools
```

`INTERNAL_RAG/` remains locally ignored.

## Optional: embeddings

```bash
pip install -r requirements-optional.txt
```

In `.irag.yml`:

```yaml
retrieval:
  embeddings: auto
```

## Optional: git hooks

```bash
python3 .agents/skills/internal-rag/irag_hooks.py install
```

See `docs/GIT-HOOKS.md`.

## Optional: MCP server

See `docs/MCP.md`.

## Update

Run the new `install.py` on the same repo. Existing `WORKING_STATE.md` and memory directories are preserved.