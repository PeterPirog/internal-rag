# Konfiguracja (`.irag.yml`, v1.0.0)

INTERNAL_RAG ma rozsądne domyślne ustawienia — plik `.irag.yml` jest opcjonalny.

## Pełny przykład

```yaml
retrieval:
  limit: 10                  # domyślna liczba wyników search/context
  mmr_lambda: 0.5            # 0=maksymalna różnorodność, 1=maksymalna trafność
  min_score: 0.5             # próg score dla BM25
  embeddings: auto           # auto | on | off
  embeddings_model: all-MiniLM-L6-v2   # model sentence-transformers
tokens:
  context_budget: 4000       # estymowany budżet tokenów w context
  warn_ratio: 0.8            # próg ostrzeżenia (nie zaimplementowane w UI, ale w JSON)
checkpoints:
  auto_archive_sessions: true   # archiwizuj snapshoty WORKING_STATE w sessions/.snapshots/
  max_task_stack: 16            # maksymalna głębokość stosu zadań
privacy:
  scan_on_checkpoint: false     # (zarezerwowane) uruchom privacy scan przy checkpoint
```

## Gdzie szukać konfiguracji

1. `<project>/.irag.yml` (jeśli istnieje)
2. Wbudowane domyślne (w `irag.py`)

`irag.py config` wypisuje efektywną konfigurację. `irag.py config --json` — jako JSON.

## Zmienne środowiskowe

- `IRAG_EMBED_MODEL` — nadpisuje `retrieval.embeddings_model`.

## Tryby embeddings

- `auto` (domyślnie) — użyj embeddings jeśli `sentence-transformers` dostępne; w przeciwnym razie BM25.
- `on` — wymuszaj embeddings; jeśli niedostępne, fallback do BM25.
- `off` — zawsze BM25.