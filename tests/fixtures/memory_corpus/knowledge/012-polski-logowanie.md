---
id: mem-corp-012-polski-logowanie
type: knowledge
status: active
created: 2024-04-05
verified: 2024-04-05
confidence: high
scope:
  - auth
  - ui
tags:
  - logowanie
  - auth
  - formularz
sources:
  - src/ui/login_form.py:12
links:
  - mem-corp-002-auth-jwt
---

# Formularz logowania waliduje email i hasło

## Knowledge

Formularz logowania w src/ui/login_form.py waliduje adres email oraz długość
hasła (min. 8 znaków) przed wysłaniem do backendu. Po udanym logowaniu
wywoływany jest AuthService.refresh() w celu pobrania tokena JWT.

## Consequence

Błędy walidacji pokazywane są po stronie klienta. Komunikat o niepoprawnych
danych nie zdradza, czy login istnieje.