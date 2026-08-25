---
id: mem-corp-020-polski-walidacja
type: knowledge
status: active
created: 2024-05-10
verified: 2024-05-10
confidence: high
scope:
  - validation
  - backend
tags:
  - walidacja
  - bledy
  - backend
sources:
  - src/validators/pesel.py:8
links: []
---

# Walidacja numeru PESEL w backendzie

## Knowledge

Walidacja numeru PESEL odbywa się w src/validators/pesel.py. Sprawdzana jest
długość (11 cyfr), suma kontrolna oraz data urodzenia wyprowadzona z ciągu.
Błędny PESEL zwraca HTTP 422 ze zlokalizowanym komunikatem.

## Consequence

Frontend nie musi powtarzać logiki sumy kontrolnej, ale może pokazać
natychmiastową podpowiedź dla długości.