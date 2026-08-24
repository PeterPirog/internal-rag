# Embeddings (opcjonalne, v1.0.0)

Domyślnie INTERNAL_RAG używa **BM25 + MMR** (czysty Python, zero zależności). Dla lepszego wyszukiwania semantycznego można dodać sentence-transformers.

## Instalacja

```bash
pip install sentence-transformers numpy
```

Pierwsze użycie pobierze model (~80–400 MB, zależnie od modelu) do cache użytkownika.

## Włączenie

W `.irag.yml`:

```yaml
retrieval:
  embeddings: auto      # auto (domyślnie) | on | off
  embeddings_model: all-MiniLM-L6-v2
```

- `auto` — embeddings jeśli pakiet dostępny, w przeciwnym razie BM25.
- `on` — preferuj embeddings, fallback BM25 przy błędzie.
- `off` — zawsze BM25.

## Jak to działa

1. `irag.py` lazy-importuje `irag_embeddings.py` (ten z kolei importuje `sentence_transformers`).
2. Embeddings są cache'owane w pamięci procesu (SHA-256 klucz).
3. Wyniki embeddings są łączone z heurystyką statusu (active/tentative/superseded).
4. Gdy embeddings niedostępne lub zawodzą — automatyczny fallback do BM25+MMR.

## Diagnostyka

```bash
irag.py embeddings-info
irag.py embeddings-info --json
irag.py doctor
```

## Modele

Domyślnie `all-MiniLM-L6-v2` ( szybki, ~80 MB). Można zmienić:

```yaml
retrieval:
  embeddings_model: paraphrase-multilingual-MiniLM-L12-v2   # lepszy dla PL
```

lub `IRAG_EMBED_MODEL=...` env.

## Kiedy embeddings pomagają

- Synonimy i parafrazy (BM25 tego nie łapie).
- Zapytania w innym języku niż treść pamięci.
- Dłuższe, opisowe zapytania.

## Kiedy BM25 wystarcza

- Dokładne dopasowanie tokenów (np. nazwy plików, identyfikatory).
- Małe korpusy pamięci.
- Środowiska bez możliwości instalacji pakietów.