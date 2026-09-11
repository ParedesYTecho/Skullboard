# LSN-001: Tolerancia de Scopes OAuth y Patrón Werewolf

- **ID**: page_lsn_001_oauth_scope_tolerance
- **Date**: 2026-09-11
- **Status**: Distilled
- **Tags**: #oauth #discord #security #ux

## Lección 1: Scopes de Discord OAuth Acumulativos
- **Problema**: set(scopes) == {'identify', 'guilds'} causaba 400 Bad Request: Scopes OAuth no permitidos.
- **Causa**: Cuando un usuario autorizó previamente la app para otras funciones (ej. /verify con 
ole_connections.write), Discord retorna el superconjunto de scopes ya concedidos.
- **Solución**: Validar siempre con subconjunto .issubset() insensible a mayúsculas y espacios:
  {'identify', 'guilds'}.issubset({s.strip().lower() for s in scopes}).

## Lección 2: Patrón Werewolf y Prevención de Bucles
- **Problema**: Tarjetas intermedias de 'Inicia sesión con Discord' frustran la UX de acceso directo al dashboard.
- **Solución**: Si el usuario entra a /dashboard sin autenticar (401), redirigir directamente al endpoint OAuth de Discord.
- **Guardia Crítica**: Guardar bandera uthResult.exchanged. Si falla la verificación de sesión inmediatamente tras intercambiar el código OAuth, detener el flujo y avisar de cookies bloqueadas; nunca llamar a 	riggerDiscordAuth() incondicionalmente tras un callback para no entrar en bucle infinito.

## Lección 3: Nomenclatura Conceptual vs Esquema Real de BD
- **Alerta**: Las tablas históricamente referidas como guild_configs y skullboard_messages se llaman realmente public.settings y public.tracked_messages en PostgreSQL. Nunca asumir que una tabla fue borrada si no aparece con el nombre coloquial; auditar information_schema.tables.
