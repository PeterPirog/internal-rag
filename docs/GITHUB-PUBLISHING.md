# Umieszczenie INTERNAL_RAG na własnym GitHub

Ten dokument dotyczy **repozytorium INTERNAL_RAG**, a nie projektu, w którym INTERNAL_RAG jest tymczasowo instalowany.

## 1. Rozpakuj release

Rozpakuj `internal-rag-v0.4-github-ready.zip` do osobnego katalogu, np.:

```text
D:\GitHub\internal-rag
```

## 2. Zainicjalizuj Git

```powershell
cd "D:\GitHub\internal-rag"
git init
git add .
git commit -m "Initial INTERNAL_RAG v0.4.0"
```

## 3. Utwórz puste repo na GitHub

Nie dodawaj zdalnie osobnego README/licencji, jeżeli chcesz uniknąć konfliktu pierwszego commita.

## 4. Podłącz remote i push

Użyj adresu własnego repozytorium:

```powershell
git branch -M main
git remote add origin <TWOJ-ADRES-REPO>
git push -u origin main
```

## 5. Release ZIP

Plik ZIP może być dodany jako GitHub Release asset. Nie ma potrzeby commitować ZIP-a do repo, ponieważ `.gitignore` ignoruje `*.zip`.

## 6. Co warto zachować przez lata

Najważniejsze pliki do przyszłego odtworzenia sposobu działania:
- `README.md`,
- `START_HERE.md`,
- `docs/ARCHITECTURE.md`,
- `docs/PRIVACY-AND-GIT.md`,
- `docs/COMPATIBILITY.md`,
- `CHANGELOG.md`,
- `VERSION`,
- `self_test.py`.

Po aktualizacji Warp/OpenCode uruchom `self_test.py` i sprawdź źródła z `docs/COMPATIBILITY.md`.
