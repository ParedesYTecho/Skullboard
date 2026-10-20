# Technical case study: SkullBoard

[Back to the README](../README.en.md) · [Español](caso-tecnico.md)

SkullBoard looks like a small bot: it counts skulls and copies messages. But next to the bot there is an API, a dashboard with Discord login, and a database holding third-party data, and each of those raises its own problems. This document covers the decisions that taught me the most. The code is private, so I describe the design without showing listings.

## Pieces and responsibilities

<img src="../assets/arquitectura.svg" alt="SkullBoard architecture" width="100%">

The bot and the API run in a single Python process deployed on Render. The bot uses `discord.py` with `AutoShardedBot` on top of the `asyncio` loop. The API is a Flask app running in its own thread, and it serves the dashboard: OAuth, per-server settings, rankings and system status. The website is static and served by Vercel, which rewrites `/api` to the backend, so the browser only ever talks to one origin. Data lives in PostgreSQL managed by Supabase.

A single process keeps deployment simple and lets bot and API share caches: when a setting is saved from the dashboard, the API invalidates the bot's cache. The cost is that both share resources, and a serious failure of the process hits both.

## 1. Twenty reactions on the same message

<img src="../assets/flujo.svg" alt="Flow of a reaction" width="100%">

The naive design is obvious: on every reaction, count and update. In a burst that means dozens of requests to Discord and to the database to arrive at the same number.

The fix has three layers. Reaction events are handled in their *raw* form, so they arrive even when the message is not in `discord.py`'s cache. A debouncer groups each message's reactions: it waits two seconds and restarts the wait on every new reaction. The timer carries a generation number so that a stale timer cannot fire a check that no longer applies. Then a per-message lock guarantees that two checks of the same message never overlap.

The lock was the delicate part. A keyed lock that is never cleaned up holds memory forever, and one that is cleaned up badly can be released while another task is waiting on it. The implementation counts references and removes the lock when nobody uses it, even if the waiting task is cancelled. That last condition is easy to overlook.

The same idea applies to deletions. When messages are deleted in bulk, the bot groups queries in batches of up to a hundred identifiers and caps concurrent deletion tasks at eight, so it does not saturate database connections.

Each server's settings, prefix, ignored channels and record are kept in caches that expire after two to five minutes. They are invalidated explicitly on write, so a change made from the dashboard takes effect immediately.

## 2. When the board and reality disagree

A board that copies messages accumulates inconsistencies: duplicates from retries, copies of messages that no longer exist, and stale counts. To repair it, `/resync` walks the hall-of-fame channel and extracts the link to the original message from each copy. It groups copies by original, keeps the newest and deletes the rest. Then it fetches the original: if it is gone, it removes its copies and its record, and if it exists, it fixes the count.

That operation makes many Discord calls, and several servers may run it at once. So they share a global limiter of 8 requests per second, well below the API's global limit. A per-server lock also stops two reconciliations of the same channel from competing.

## 3. A dashboard with Discord login

The dashboard lets users browse rankings and, for administrators, change settings. That requires OAuth2, and authentication is where mistakes are easiest. These are the main decisions.

### Discord tokens never reach the browser

After login the client gets an opaque cookie (`__Host-` in production, with `HttpOnly`, `Secure` and `SameSite=Lax`). The server stores the tokens encrypted with Fernet, keyed by an HMAC of the session identifier. The first version kept sessions in process memory, which were lost on every restart and could not scale past one worker. Moving them to the database forced me to solve token renewal: two simultaneous requests could renew the same session. A conditional reservation on the row itself works as a distributed lock and removes that race. A later logout never recreates the session.

### The OAuth `state` is single-use

It is generated randomly and stored as an HMAC that expires after ten minutes. When Discord redirects back, the backend consumes it, and replaying the request fails. I had designed a second identifier bound to the browser through a flow-specific cookie. I dropped it because the requirement is that the browser receives a single cookie, and the persistent, random, single-use `state` already covered the case. The earlier decision stays on record as superseded.

### Discord returns more scopes than you ask for

If the user had previously authorised the application with other scopes, the response includes them. The first version compared scopes with exact equality and rejected those users with a confusing error. Now the required ones must be present, and casing is normalised.

### The backend does not trust the client on writes

Settings changes require a CSRF header, an allowed origin and administrator permissions checked against Discord. The chosen channel must be visible to the bot before it is saved, because accepting any numeric identifier would let someone point the board at a place it cannot write to.

## 4. A bug the tests could not see

A change that tightened headers and origin checks removed the exception for `GET /api/auth/start`, the one route that did not require an `Origin` header. All tests passed. But browsers do not send `Origin` on same-origin GET requests, and the dashboard calls that route exactly that way, through the Vercel proxy. In production, login would have returned 403 for everyone.

The tests missed it because they sent the header by hand. A review caught it before it reached production, and I confirmed it by building an environment that reproduces the whole path: the real backend, Discord and the database simulated in memory, a local proxy that forwards headers the way Vercel does, and a real Chrome browser. The fix accepts a GET without `Origin` only on that route and only when `Sec-Fetch-Site` does not indicate a cross-site request. The tests now check both sides: same-origin login works, and cross-site requests are rejected.

That environment stayed as part of the test suite. It covers login, session persistence, `state` replay, logout and saving settings.

## Data, security and an honest status page

Tables have row-level security enabled with no policies for public clients. Only the backend's service role has access. I did not add client policies while there was no reliable mapping between Supabase users and Discord server owners, because a guessed policy is worse than none. The database holds identifiers, counters and configuration, not message text.

The status page does not show figures it cannot back up. When the bot's provider is not registered it answers `unknown`, and an uptime and an SLA that were displayed without anything measuring them were removed.

## Testing and deployment

There are three kinds of tests: static checks of project invariants, authentication and route tests with Flask's test client, and the end-to-end walkthrough in a real browser. Deployments come from the protected main branch through pull requests. Render redeploys the backend and Vercel the website, and each previous deployment stays available for rollback.

## Pending

Redesigning the public website and reducing login time.
