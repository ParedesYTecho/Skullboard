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
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fskullboard.vercel.app%2Fapi%2Fstatus&query=%24.bot.guilds&label=servers+running+SkullBoard&color=c9caff&labelColor=131318&style=flat-square&cacheSeconds=3600" alt="Servers where SkullBoard is installed right now (live data)">
</p>

SkullBoard is a Discord bot for communities that already use the 💀 reaction as applause. When a message collects enough skulls, the bot copies it into a channel of its own: the server's hall of fame. It also keeps score. It knows who has the most skulls, which messages were the most voted this month and this year, and what the current record is.

It started in May 2025 as a personal project and is still running. This repository is its showcase: it explains what the bot does and how it is built. The source code is private.

The website and the bot's messages are in Spanish. This page is the English summary.

## How it works

<img src="assets/flujo.svg" alt="Six stages from a reaction to the featured message" width="100%">

Someone reacts to a message with 💀. If the count reaches the threshold the server has set, SkullBoard posts the message in the hall-of-fame channel with its author, text, image if any, and a link to the original. Each new skull updates that same post instead of creating another one, and the marker changes from 💀 to ☠️ once the threshold is doubled. If the original message is deleted, the copy is removed too.

## What it includes

- Automatic board, with optional auto-pin for messages that reach a higher threshold.
- Per-server rankings: users with the most skulls, most voted messages, and monthly and yearly tops.
- Per-server settings: destination channel, threshold, command prefix and ignored channels.
- Direct-message notice to the author when their message makes it to the board. Each user can turn it off with `/notify`.
- Web dashboard with Discord login, to browse rankings and, for administrators, change settings without typing commands.
- Slash and text commands: 22 in total, [listed on the website](https://skullboard.vercel.app/#comandos).

SkullBoard stores identifiers and counters. It does not store message text. Details are in the [privacy policy](https://skullboard.vercel.app/privacy) (Spanish).

## Dashboard

<table>
  <tr>
    <td width="50%"><img src="assets/screens/dashboard-ranking.png" alt="User ranking of a demo server"></td>
    <td width="50%"><img src="assets/screens/dashboard-ajustes.png" alt="Settings screen of a demo server"></td>
  </tr>
</table>

Screenshots use demo data. Left: a server's ranking. Right: the settings page, visible to administrators only.

## Getting started

1. [Invite the bot](https://discord.com/oauth2/authorize?client_id=1367463352774955059&permissions=277025508352&scope=bot+applications.commands) to your server.
2. Pick the hall-of-fame channel with `/set_channel`.
3. Set how many skulls are needed with `/set_min`. One is enough by default.

That is all it needs. `/setup_pin`, `/ignore` and `/prefix` are optional, and everything can also be changed from the [dashboard](https://skullboard.vercel.app/dashboard).

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
