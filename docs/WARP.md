# Warp

Warp rozpoznaje `AGENTS.md` jako Project Rules oraz skills w `.agents/skills/`.

Po instalacji uruchom Warp ponownie w repozytorium.

Przykład:

```text
Kontynuuj aktualne zadanie zgodnie z AGENTS.md i INTERNAL_RAG.
```

Możesz też jawnie poprosić: `Użyj skill internal-rag`.

Ręczny test na Windows:

```text
python .agents\skills\internal-rag\irag.py context --task "test"
```

OpenCode-specific hooks nie działają w Warp, dlatego checkpoint i guard pozostają ważne.
