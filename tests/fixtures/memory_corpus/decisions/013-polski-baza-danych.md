---
id: mem-corp-013-polski-baza-danych
type: decision
status: active
created: 2024-04-10
verified: 2024-04-10
confidence: high
valid_from: 2024-04-10
scope:
  - database
tags:
  - baza_danych
  - postgres
  - decyzja
sources: []
links:
  - mem-corp-001-use-postgres
---

# Decyzja: baza danych PostgreSQL dla wszystkich środowisk

## Knowledge

Postanowiliśmy używać PostgreSQL 16 jako głównej bazy danych we wszystkich
środowiskach (dev, staging, prod). Powodem jest spójność środowisk oraz
obsługa rozszerzenia pgvector.

## Consequence

Wszystkie migracje muszą być kompatybilne z PostgreSQL. Nie używamy
MySQL ani SQLite w środowiskach innych niż testy jednostkowe.