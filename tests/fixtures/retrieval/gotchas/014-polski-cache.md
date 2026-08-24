---
id: mem-fix-014-polski-cache
type: gotcha
status: active
created: 2024-04-15
verified: 2024-04-15
scope:
  - cache
  - performance
tags:
  - cache
  - pamięć_podręczna
  - wydajność
sources:
  - src/cache/redis_client.py:25
links: []
last_accessed: 2026-08-24
---

# Pułapka: klucze cache muszą mieć prefiks środowiska

## Knowledge

Klucze w Redis muszą mieć prefiks środowiska (dev_, staging_, prod_). Bez tego dane z dev zanieczyszczają prod.

## Consequence

Wszystkie operacje cache muszą używać helpera z prefiksem. Nie bezpośrednich kluczy.