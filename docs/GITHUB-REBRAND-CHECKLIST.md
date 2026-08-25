# GitHub rebrand checklist — internal-rag → mcp-light-memory

This document prepares the GitHub repository rename so it can be done with
minimal friction. The rename itself must be performed manually (GitHub
Settings → General → Repository name) because automated renames via the API
require owner permissions and are intentionally left as a manual step.

## Target

- **New repo name:** `mcp-light-memory`
- **New full slug:** `PeterPirog/mcp-light-memory`
- **Suggested description:** `Lightweight local-first persistent memory for coding agents and MCP clients.`
- **Short tagline:** `Small, local, durable memory for MCP-powered coding workflows.`
- **Suggested topics:** `mcp`, `model-context-protocol`, `agent-memory`, `rag`, `local-first`, `sqlite`, `python`, `coding-agents`, `warp`, `opencode`, `pycharm`, `developer-tools`
- **Homepage/docs:** link to the README (no separate site yet).

## Pre-rename (already done in this rebrand)

- [x] README, docs, examples, code, tests updated to the new brand.
- [x] `mlm.py` CLI shim added; `irag.py` kept as legacy alias.
- [x] MCP `serverInfo.name` updated to `mcp-light-memory` / `mcp-light-memory-router`.
- [x] Logo + icon assets in `docs/assets/`.
- [x] Migration document: `docs/MIGRATION-TO-MCP-LIGHT-MEMORY.md`.
- [x] Branding note: `docs/BRANDING.md`.
- [x] Rebrand consistency tests: `tests/test_rebrand.py`.
- [x] `VERSION` → `1.7.0`; `CHANGELOG.md` 1.7.0 section added.
- [x] AGENTS.md markers updated to `MCP_LIGHT_MEMORY_START`/`END`.

## Rename steps (manual, in GitHub UI)

1. Go to **Settings → General** for `PeterPirog/internal-rag`.
2. Change **Repository name** to `mcp-light-memory`. Click **Rename**.
3. GitHub automatically creates a redirect from the old URL to the new one.
   Existing clones continue to work via the redirect, but update remotes
   anyway (see below).
4. Update the **Description** field to the suggested text above.
5. Update the **Topics** field with the suggested topics above.
6. (Optional) Upload `docs/assets/logo.svg` as the social preview image
   (Settings → Social preview → Edit → Upload). A 1280×640 banner can be
   composed from the logo + wordmark; see `docs/BRANDING.md`.

## Post-rename checklist

- [ ] Update local remotes:
  ```bash
  git remote set-url origin https://github.com/PeterPirog/mcp-light-memory.git
  git remote -v  # verify
  ```
- [ ] Update badge URLs in `README.md` if they reference the old slug
  (the version/license/python badges are static shields and do not reference
  the repo slug, so no change is needed for those).
- [ ] Update any hardcoded `PeterPirog/internal-rag` URLs in docs/scripts
  (search the repo for `internal-rag` after the rename and update the
  remaining user-facing references).
- [ ] Re-run CI on the new default branch to confirm green.
- [ ] Tag `v1.7.0` (already created locally; push after rename if not yet
  pushed, or re-push to confirm the tag points at the rebrand commit).
- [ ] Announcement (see below).

## Redirect expectations

After the GitHub rename:
- `https://github.com/PeterPirog/internal-rag` → redirects to
  `https://github.com/PeterPirog/mcp-light-memory`.
- Old `git clone` URLs continue to work via redirect.
- Old issue/PR URLs continue to work via redirect.
- Old release URLs continue to work via redirect.
- The redirect is permanent as long as the old name is not re-registered by
  someone else (GitHub reserves the old name for a period).

## Announcement suggestions

**Headline:** `MCP Light Memory — lightweight local-first persistent memory for coding agents and MCP clients (formerly internal-rag)`

**Body (short):**
> We're rebranding `internal-rag` to **MCP Light Memory** (`mcp-light-memory`).
> Same lightweight, local-first, zero-dependency agent memory — new name,
> new CLI alias `mlm`, refreshed docs/examples, and a simple logo. Existing
> installs keep working: `irag.py` and `INTERNAL_RAG/` are preserved as
> deprecated aliases. No data migration required. See
> `docs/MIGRATION-TO-MCP-LIGHT-MEMORY.md` for details.

**Release:** tag `v1.7.0` with the CHANGELOG section as the release notes.

## Package / index considerations

The core is intentionally **not** published to PyPI (it is a single-file
drop-in, not a `pip install` package). If a future `pip install
mcp-light-memory` distribution is desired, the package name
`mcp_light_memory` is reserved by this rebrand; the module filename
`irag.py` would then live inside `mcp_light_memory/` with an
`__init__.py` re-export. This is out of scope for 1.7.0.