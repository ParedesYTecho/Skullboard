<p align="center">
  <img src="assets/banner.svg" alt="SkullBoard" width="100%">
</p>

<p align="center">
  <a href="https://discord.com/oauth2/authorize?client_id=1367463352774955059&permissions=277025508352&scope=bot+applications.commands"><b>Add to Discord</b></a>
  &nbsp;·&nbsp;
  <a href="https://skullboard.vercel.app">Website</a>
  &nbsp;·&nbsp;
  <a href="https://skullboard.vercel.app/dashboard">Dashboard</a>
  &nbsp;·&nbsp;
  <a href="docs/technical-case-study.md">Technical case study</a>
  &nbsp;·&nbsp;
  <a href="README.md">Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstatus&query=%24.bot.guilds&label=servers&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Servers where SkullBoard is installed right now (live data)">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstatus&query=%24.bot.members&label=members&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Total members across those servers (live data)">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstats&query=%24.commands&label=commands&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Available commands (live data)">
  <img src="https://img.shields.io/github/v/release/ParedesYTecho/Skullboard?label=version&color=c9caff&labelColor=131318&style=flat-square" alt="Latest published version">
  <br>
  <sub>Live data from the bot. Members add up every server, including bots and people who are in several.</sub>
</p>

SkullBoard is a Discord bot for communities that already use the 💀 reaction as applause. When a message collects enough skulls, the bot copies it into a channel of its own: the server's hall of fame. It also keeps score. It knows who has the most skulls, which messages were the most voted this month and this year, and what the current record is.

It started in May 2025 as a personal project and is still running. This repository is its showcase: it explains what the bot does and how it is built. The source code is private.

The website and the bot's messages are in Spanish. This page is the English summary.

## How it works

<img src="assets/flujo.svg" alt="Six stages from a reaction to the featured message" width="100%">

Someone reacts to a message with 💀. If the count reaches the threshold the server has set, SkullBoard posts the message in the hall-of-fame channel with its author, text, image if any, and a link to the original. Each new skull updates that same post instead of creating another one, and the marker changes from 💀 to ☠️ once the threshold is doubled. If the original message is deleted, the copy is removed too.

## What it includes

<table>
  <tr>
    <td width="33%" valign="top"><img src="assets/icon-tablon.svg" width="44" alt=""><br><b>Automatic board</b><br><sub>Copies messages that reach the threshold. Optional auto-pin for the most voted.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-ranking.svg" width="44" alt=""><br><b>Rankings</b><br><sub>Most voted users and messages for each server, with monthly and yearly tops.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-ajustes.svg" width="44" alt=""><br><b>Per-server settings</b><br><sub>Channel, threshold, prefix and ignored channels, server by server.</sub></td>
  </tr>
  <tr>
    <td width="33%" valign="top"><img src="assets/icon-avisos.svg" width="44" alt=""><br><b>Author notice</b><br><sub>Direct message when their message enters the board. Turn it off with <code>/notify</code>.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-dashboard.svg" width="44" alt=""><br><b>Web dashboard</b><br><sub>Log in with Discord, browse rankings and, if you administer, change settings.</sub></td>
    <td width="33%" valign="top"><img src="assets/icon-comandos.svg" width="44" alt=""><br><b>22 commands</b><br><sub>Slash and text. The full list is on <a href="https://skullboard.vercel.app/#comandos">the website</a>.</sub></td>
  </tr>
</table>

SkullBoard stores identifiers and counters. It does not store message text. Details are in the [privacy policy](https://skullboard.vercel.app/privacy) (Spanish).

## Dashboard

<img src="assets/screens/dashboard-duo.png" alt="Dashboard ranking and settings with demo data" width="100%">

Screenshots use demo data. Left: a server's ranking. Right: the settings page, visible to administrators only.

## Getting started

1. [Invite the bot](https://discord.com/oauth2/authorize?client_id=1367463352774955059&permissions=277025508352&scope=bot+applications.commands) to your server.
2. Pick the hall-of-fame channel with `/set_channel`.
3. Set how many skulls are needed with `/set_min`. One is enough by default.

That is all it needs. `/setup_pin`, `/ignore` and `/prefix` are optional, and everything can also be changed from the [dashboard](https://skullboard.vercel.app/dashboard).

## FAQ

<details>
<summary>Which permissions does the bot ask for?</summary>

View channels, send messages (including in threads), embed links, attach files, read message history and use application commands. Auto-pin also needs the ability to pin messages in the board channel.
</details>

<details>
<summary>Does it store my messages?</summary>

No. It stores server, channel, message and author identifiers, the skull count and the server's settings. Message text stays on Discord. More in the [privacy policy](https://skullboard.vercel.app/privacy) (Spanish).
</details>

<details>
<summary>How much does it cost?</summary>

It is free.
</details>

<details>
<summary>Where do I ask for help or suggest something?</summary>

Use the contact form on the [website](https://skullboard.vercel.app/#contacto).
</details>

## What's new

- `v2.6.0` (12 Sep 2026): redesigned website and dashboard, with search, filters and per-server settings drafts.
- `v2.5.1` (3 Sep 2026): live system status and a leaderboard with avatars and message links.
- `v2.5.0` (1 Sep 2026): dashboard with Discord login and settings from the browser.

Every version is in the [changelog](CHANGELOG.md) (Spanish) and the [releases](https://github.com/ParedesYTecho/Skullboard/releases).

## Behind the bot

An event-driven bot looks simple until twenty people react to the same message within two seconds.

<img src="assets/arquitectura.svg" alt="Architecture: Discord, a Python process on Render running the bot and the Flask API, Supabase, and the web on Vercel" width="100%">

- Reaction bursts. Each message has a two-second timer that restarts with every reaction, plus a lock that prevents two checks from overlapping. Twenty reactions in a row produce one check.
- Discord rate limits. Bulk operations such as reconciling a whole board with `/resync` go through a global limiter of 8 requests per second for the whole process, so running them on several servers at once does not exhaust the bot's quota.
- Dashboard sessions. The browser gets an opaque cookie. Discord tokens are encrypted on the server and never reach the client. The OAuth `state` is stored as an HMAC and works only once.
- Closed-by-default database. Tables have row-level security with no public policies. Only the backend can read them.
- Testing. Static checks, authentication tests, and a local environment that runs the real backend with simulated Discord and database behind a proxy that mirrors production. A real browser walks through login, settings and logout.

The [technical case study](docs/technical-case-study.md) goes deeper into four concrete problems and how they were solved.

## Links

[Website](https://skullboard.vercel.app) · [Dashboard](https://skullboard.vercel.app/dashboard) · [Changelog](https://skullboard.vercel.app/cambios) · [Terms](https://skullboard.vercel.app/terms) · [Privacy](https://skullboard.vercel.app/privacy) · [Contact](https://skullboard.vercel.app/#contacto)

<p align="center">
  <sub>A project by GlobalFerociouS · © 2025–2026 SkullBoard. All rights reserved</sub>
</p>
