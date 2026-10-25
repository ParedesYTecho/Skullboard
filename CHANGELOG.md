# Historial de cambios

Resumen de las versiones de SkullBoard. El historial completo, con más detalle, está en la [web](https://skullboard.vercel.app/cambios).

<details>
<summary>Numeración de versiones</summary>

El 25 de octubre de 2026 las versiones se renumeraron para coincidir con las de la web. El contenido y las fechas no cambian. Equivalencias con la numeración anterior:

| Ahora | Antes | | Ahora | Antes |
|---|---|---|---|---|
| v1.9.2 | v2.6.0 | | v1.5 | v2.3.0 |
| v1.9.1 | v2.5.1 | | v1.4 | v2.2.0 |
| v1.9 | v2.5.0 | | v1.3 | v2.1.0 |
| v1.8 | v2.4.2 | | v1.2 | v2.0.0 |
| v1.7.1 | v2.4.1 | | v1.1 | v1.5.0 |
| v1.7 | v2.4.0 | | v1.0 | v1.0.0 |
| v1.6 | v2.3.1 | | | |

</details>

## v1.9.2 · 12 de septiembre de 2026
Interfaz web y dashboard rediseñados para móvil y escritorio. El dashboard incorpora búsqueda de servidores y filtros por autor, canal, fecha o ID, borradores de ajustes por servidor y direcciones que recuerdan el servidor y la pestaña abiertos.

## v1.9.1 · 3 de septiembre de 2026
Estado del sistema en vivo (`/api/status`) con modal de salud de cada componente. Pie de página nuevo. El leaderboard muestra el avatar y el nombre del autor, con enlaces para saltar al mensaje, y el panel solo lista servidores donde el bot está o donde eres administrador.

## v1.9 · 1 de septiembre de 2026
Dashboard con inicio de sesión de Discord (OAuth2): ajustes del servidor y leaderboard desde el navegador. `AutoShardedBot`, alertas de fallos por webhook, aviso al propietario cuando faltan permisos en el canal del tablón y soporte PWA.

## v1.8 · 1 de septiembre de 2026
Cachés con expiración y tamaño acotado, `orjson`, `uvloop` y un endpoint de salud con el consumo de memoria.

## v1.7.1 · 18 de agosto de 2026
Navegación unificada, modo claro de alto contraste, buscador de comandos con botón de copiado y direcciones sin `.html`. Reintento con espera creciente en el arranque del bot cuando Discord responde 429.

## v1.7 · 17 de agosto de 2026
Rankings y estadísticas calculados en la base de datos mediante RPC. Reintentos con *backoff* y *jitter* ante cortes de red, lock por clave a prueba de cancelaciones, debouncer de reacciones y validación anti-CSRF en OAuth2. Mejoras de accesibilidad con teclado.

## v1.6 · 14 de julio de 2026
Web oficial en Vercel con métricas en vivo, formulario de contacto y comando `sk!stats`. Los autores que dejaron el servidor vuelven a mostrar su nombre en los rankings.

## v1.5 · 5 de julio de 2026
Purgas masivas bajo control (semáforo de borrado y lotes de cien), limitador global para `/resync` y mensajes claros cuando un comando de servidor se usa por mensaje directo.

## v1.4 · 24 de junio de 2026
Comando `/resync` para recontar calaveras y eliminar duplicados. `/reset` solo para el propietario del servidor. Términos de servicio y política de privacidad.

## v1.3 · 8 de mayo de 2026
Rankings con `/leaderboard`, `/server_stats`, `/top_month` y `/top_year`. Auto-pin con `/setup_pin`, avisos personales con `/notify` y herramientas de importación histórica para el propietario del bot.

## v1.2 · 30 de diciembre de 2025
Cliente asíncrono de Supabase, comando `/stats` y registro estructurado con niveles de severidad.

## v1.1 · 19 de junio de 2025
Datos en PostgreSQL en la nube en lugar de archivos JSON, eventos de reacción en bruto, OAuth2 y Linked Roles de Discord, y prefijo configurable por servidor.

## v1.0 · 1 de mayo de 2025
Primera versión: starboard de calaveras con umbral configurable, imágenes y GIFs en el mensaje destacado, comandos básicos de configuración y control de duplicados.
