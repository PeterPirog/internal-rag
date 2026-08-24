---
id: mem-fix-012-polski-logowanie
type: knowledge
status: active
created: 2024-04-05
verified: 2024-04-05
scope:
  - auth
  - ui
tags:
  - logowanie
  - auth
  - formularz
sources:
  - src/ui/login_form.py:12
links: []
---

# Formularz logowania waliduje email i hasło

## Knowledge

Formularz logowania sprawdza format email oraz minimalną długość hasła (8 znaków). Błędy wyświetlane są w języku polskim.

## Consequence

Walidacja po stronie klienta musi być spójna z walidacją serwera.