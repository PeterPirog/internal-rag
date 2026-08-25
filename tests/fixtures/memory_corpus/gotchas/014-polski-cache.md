---
id: mem-corp-014-polski-cache
type: gotcha
status: active
created: 2024-04-15
verified: 2024-04-15
confidence: high
scope:
  - cache
  - performance
tags:
  - cache
  - pamiec_podreczna
  - wydajnosc
sources:
  - src/cache/redis_client.py:25
links:
  - mem-corp-003-redis-cache
---

# Pułapka: pamięć podręczna Redis nie unieważnia się po rollu deploy

## Knowledge

Po wdrożeniu nowej wersji klucze w Redis pozostają stare, ponieważ TTL
wynosi 30 minut i nie jest czyszczony przy deploy. Objaw to użycie starej
konfiguracji przez użytkowników tuż po wdrożeniu.

## Consequence

Po każdym deployu należy ręcznie wywołać `flushdb` na środowiskach
mieszkalnych lub zwiększyć wersję klucza (cache busting).