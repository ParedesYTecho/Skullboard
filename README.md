<p align="center">
  <img src="assets/banner.svg" alt="SkullBoard" width="100%">
</p>

<p align="center">
  <a href="https://discord.com/oauth2/authorize?client_id=1367463352774955059&permissions=277025508352&scope=bot+applications.commands"><b>Añadir a Discord</b></a>
  &nbsp;·&nbsp;
  <a href="https://skullboard.vercel.app">Web</a>
  &nbsp;·&nbsp;
  <a href="https://skullboard.vercel.app/dashboard">Dashboard</a>
  &nbsp;·&nbsp;
  <a href="docs/caso-tecnico.md">Caso técnico</a>
  &nbsp;·&nbsp;
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstatus&query=%24.bot.guilds&label=servidores&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Servidores donde SkullBoard está instalado ahora mismo (dato en vivo)">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstatus&query=%24.bot.members&label=miembros&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Suma de miembros de esos servidores (dato en vivo)">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstats&query=%24.commands&label=comandos&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Comandos disponibles (dato en vivo)">
  <img src="https://img.shields.io/github/v/release/ParedesYTecho/Skullboard?label=versi%C3%B3n&color=c9caff&labelColor=131318&style=flat-square" alt="Última versión publicada">
  <br>
  <sub>Datos en vivo del bot. Los miembros suman todos los servidores, incluidos bots y personas que están en varios.</sub>
</p>

SkullBoard es un bot de Discord para comunidades que ya usan la reacción 💀 como aplauso. Cuando un mensaje reúne suficientes calaveras, el bot lo copia en un canal propio: el tablón de honor del servidor. También lleva la cuenta. Sabe quién acumula más, cuáles son los mensajes más votados del mes y del año, y cuál es el récord actual.

Empezó en mayo de 2025 como proyecto personal y sigue en marcha. Este repositorio es su escaparate: explica qué hace el bot y cómo está construido. El código fuente es privado.

## Cómo funciona

<img src="assets/flujo.svg" alt="Seis etapas desde una reacción hasta el mensaje destacado" width="100%">

Alguien reacciona con 💀 a un mensaje. Si el recuento alcanza el umbral que ha fijado el servidor, SkullBoard lo publica en el canal de destacados con su autor, su texto, la imagen si la hay y un enlace al original. Cada calavera nueva actualiza esa misma publicación en lugar de crear otra, y el marcador pasa de 💀 a ☠️ cuando se duplica el umbral. Si el mensaje original se borra, la copia desaparece también.

## Qué incluye

<table>
  <tr>
    <td width="33%" valign="top"><img src="assets/icon-tablon.svg" width="44" alt=""><br><b>Tablón automático</b><br><sub>Copia los mensajes que alcanzan el umbral. Auto-pin opcional para los más votados.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-ranking.svg" width="44" alt=""><br><b>Rankings</b><br><sub>Usuarios y mensajes más votados de cada servidor, con tops del mes y del año.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-ajustes.svg" width="44" alt=""><br><b>Configuración propia</b><br><sub>Canal, umbral, prefijo y canales ignorados, servidor por servidor.</sub></td>
  </tr>
  <tr>
    <td width="33%" valign="top"><img src="assets/icon-avisos.svg" width="44" alt=""><br><b>Aviso al autor</b><br><sub>Mensaje directo cuando su mensaje entra en el tablón. Se desactiva con <code>/notify</code>.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-dashboard.svg" width="44" alt=""><br><b>Dashboard web</b><br><sub>Inicia sesión con Discord, consulta rankings y, si administras, cambia los ajustes.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-comandos.svg" width="44" alt=""><br><b>22 comandos</b><br><sub>Slash y de texto. La lista completa está en <a href="https://skullboard.vercel.app/#comandos">la web</a>.</sub></td>
  </tr>
</table>

SkullBoard guarda identificadores y contadores. No guarda el texto de los mensajes. Los detalles están en la [política de privacidad](https://skullboard.vercel.app/privacy).

## Dashboard

<img src="assets/screens/dashboard-duo.png" alt="Ranking y ajustes del dashboard con datos de demostración" width="100%">

Capturas con datos de demostración. A la izquierda, el ranking de un servidor. A la derecha, los ajustes, que solo ven los administradores.

## Empezar

1. [Invita el bot](https://discord.com/oauth2/authorize?client_id=1367463352774955059&permissions=277025508352&scope=bot+applications.commands) a tu servidor.
2. Elige el canal de destacados con `/set_channel`.
3. Ajusta cuántas calaveras hacen falta con `/set_min`. Por defecto basta una.

Con eso ya funciona. `/setup_pin`, `/ignore` y `/prefix` son opcionales, y todo se puede cambiar también desde el [dashboard](https://skullboard.vercel.app/dashboard).

## Preguntas frecuentes

<details>
<summary>¿Qué permisos pide el bot?</summary>

Ver canales, enviar mensajes (también en hilos), insertar enlaces, adjuntar archivos, leer el historial y usar comandos de aplicación. Para el auto-pin necesita además poder fijar mensajes en el canal del tablón.
</details>

<details>
<summary>¿Guarda mis mensajes?</summary>

No. Guarda identificadores de servidor, canal, mensaje y autor, el recuento de calaveras y la configuración del servidor. El texto de los mensajes se queda en Discord. Más detalles en la [política de privacidad](https://skullboard.vercel.app/privacy).
</details>

<details>
<summary>¿Cuánto cuesta?</summary>

Es gratis.
</details>

<details>
<summary>¿Dónde pido ayuda o propongo algo?</summary>

En el formulario de contacto de la [web](https://skullboard.vercel.app/#contacto).
</details>

## Novedades

- `v1.9.2` (12 sep 2026): web y dashboard rediseñados, con búsqueda, filtros y borradores de ajustes por servidor.
- `v1.9.1` (3 sep 2026): estado del sistema en vivo y leaderboard con avatares y enlaces al mensaje.
- `v1.9` (1 sep 2026): dashboard con inicio de sesión de Discord y ajustes desde el navegador.

Todas las versiones están en el [historial de cambios](CHANGELOG.md) y en las [releases](https://github.com/ParedesYTecho/Skullboard/releases).

## Detrás del bot

Un bot que reacciona a eventos parece sencillo hasta que veinte personas reaccionan al mismo mensaje en dos segundos. 
<img src="assets/arquitectura.svg" alt="Arquitectura: Discord, proceso Python en Render con el bot y la API Flask, Supabase y la web en Vercel" width="100%">

- Ráfagas de reacciones. Cada mensaje tiene un temporizador de dos segundos que se reinicia con cada reacción, y un lock que impide dos comprobaciones simultáneas. Veinte reacciones seguidas producen una sola comprobación.
- Límites de Discord. Las operaciones masivas, como reconciliar un tablón entero con `/resync`, pasan por un limitador global de 8 peticiones por segundo para todo el proceso, así que lanzarlas en varios servidores a la vez no agota el cupo del bot.
- Sesiones del dashboard. El navegador recibe una cookie opaca. Los tokens de Discord se cifran en el servidor y nunca llegan al cliente. El `state` de OAuth se guarda como HMAC y solo sirve una vez.
- Base de datos cerrada por defecto. Las tablas tienen RLS sin políticas públicas. Solo el backend puede leerlas.
- Pruebas. Hay comprobaciones estáticas, pruebas de autenticación y un entorno local que ejecuta el backend real con Discord y la base de datos simulados, detrás de un proxy equivalente al de producción. Un navegador real recorre el login, los ajustes y el cierre de sesión.

El [caso técnico](docs/caso-tecnico.md) cuenta con más detalle cuatro problemas concretos y cómo se resolvieron.

## Enlaces

[Web](https://skullboard.vercel.app) · [Dashboard](https://skullboard.vercel.app/dashboard) · [Historial de cambios](https://skullboard.vercel.app/cambios) · [Términos](https://skullboard.vercel.app/terms) · [Privacidad](https://skullboard.vercel.app/privacy) · [Contacto](https://skullboard.vercel.app/#contacto)

<p align="center">
  <sub>Proyecto de GlobalFerociouS · © 2025–2026 SkullBoard. Todos los derechos reservados</sub>
</p>
