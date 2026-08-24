---
id: mem-fix-020-polski-walidacja
type: knowledge
status: active
created: 2024-05-10
verified: 2024-05-10
scope:
  - validation
  - backend
tags:
  - walidacja
  - błędy
  - backend
sources:
  - src/validators/pesel.py:8
links: []
---

# Walidacja numeru PESEL w backendzie

## Knowledge

Walidacja numeru PESEL sprawdza sumę kontrolną i datę urodzenia. Błędy zwracane jako kody: INVALID_LENGTH, INVALID_CHECKSUM, INVALID_DATE.

## Consequence

Frontend musi mapować kody błędów na polskie komunikaty.