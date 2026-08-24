---
id: mem-fix-013-polski-baza-danych
type: decision
status: active
created: 2024-04-10
verified: 2024-04-10
scope:
  - database
tags:
  - baza_danych
  - postgres
  - decyzja
sources: []
links: []
---

# Decyzja: baza danych PostgreSQL dla wszystkich środowisk

## Knowledge

Podjęto decyzję o użyciu PostgreSQL we wszystkich środowiskach (dev, staging, prod). Uzasadnienie: spójność, JSONB, pełnotekstowe wyszukiwanie.

## Consequence

Brak SQLite w środowisku deweloperskim. Wszyscy deweloperzy muszą mieć PostgreSQL.