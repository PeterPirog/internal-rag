# Release checklist

1. Ustaw poprawną wersję w `VERSION` i `CHANGELOG.md`.
2. Zweryfikuj datę i źródła w `docs/COMPATIBILITY.md`.
3. Uruchom `python self_test.py` na Windows i Linux (GitHub Actions robi oba systemy).
4. Sprawdź, czy paczka nie zawiera prywatnych ścieżek ani prawdziwych credentiali.
5. Utwórz ZIP jako GitHub Release asset.
6. Nie commituj ZIP-a do repozytorium źródłowego — `.gitignore` ignoruje `*.zip`.
