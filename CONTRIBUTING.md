# Contributing

Before submitting a change:
1. Edit code or docs.
2. Run `python self_test.py` — it must print `SELF TEST PASS`.
3. Update documentation (keep it in English).
4. For a release, bump `VERSION` and update `CHANGELOG.md`.

Do not use real secrets in tests. Do not commit `INTERNAL_RAG/` memory or `.irag.yml` (they are local-only by default).

Documentation language: **English**.