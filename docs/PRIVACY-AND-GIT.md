# Prywatność i Git

## Domyślna zasada

`INTERNAL_RAG/` jest lokalną pamięcią roboczą i może zawierać ścieżki lokalne, hipotezy oraz informacje operacyjne. Nie zapisuj do niej sekretów.

## Dlaczego `.git/info/exclude`

v0.4 domyślnie używa `.git/info/exclude` zamiast projektowego `.gitignore`. To lokalna konfiguracja danego klonu repo i nie jest commitowana.

Tryb `local` wyklucza:
- `INTERNAL_RAG/`,
- skill INTERNAL_RAG,
- OpenCode tools/commands/plugin INTERNAL_RAG,
- `AGENTS.md` tylko wtedy, gdy instalator utworzył go od zera.

Jeżeli projekt miał wcześniej tracked `AGENTS.md`, jego modyfikacja będzie widoczna w Git. Deinstalator usuwa tylko oznaczoną sekcję INTERNAL_RAG.

## Ignore nie działa na tracked files

Jeżeli plik został już dodany do Git, późniejsze ignore/exclude nie przestaje go śledzić.

Przed push uruchom:

```text
privacy_check.py
```

Oczekiwane: `RESULT: PASS`.

Checker sprawdza obecność lokalnego exclude, tracked INTERNAL_RAG/tools, typowe wzorce credentiali i występowanie `INTERNAL_RAG/` w historii commitów. Nie wypisuje wartości znalezionych sekretów.

## Jeśli INTERNAL_RAG był commitowany

Samo usunięcie plików nie usuwa danych z historii Git. Potrzebne jest osobne czyszczenie historii, np. `git filter-repo`.

## Czy trzeba coś dopisać do `.gitignore` projektu?

Domyślnie: **nie**.

Jeżeli cały zespół świadomie chce wspólnie ignorować pamięć, można dodać:

```gitignore
/INTERNAL_RAG/
```
