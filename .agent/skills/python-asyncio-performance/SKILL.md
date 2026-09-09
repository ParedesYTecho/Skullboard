---
name: python-asyncio-performance
description: >-
  High-performance patterns for Python asyncio applications, Discord bots, and API servers.
  Covers ultra-fast JSON serialization (orjson), custom event loops (uvloop),
  thread-safe LRU/TTL caching (cachetools), connection pooling (aiohttp),
  and memory profiling for zero-leak async architectures.
---

# Python Asyncio Performance & High-Scale Optimization

This skill provides optimization techniques for maximizing throughput and minimizing memory footprint in async Python bots and web backends.

## 1. High-Throughput JSON Parsing (`orjson`)
- Use `orjson.dumps()` and `orjson.loads()` for serializing Gateway payloads and database responses.
- Up to 10x faster than standard library `json` and handles `datetime`, `UUID`, and numpy objects natively.

## 2. Event Loop Optimization (`uvloop`)
- On Linux/POSIX production environments (e.g. Render/Linux servers), install `uvloop` and call `uvloop.install()` before `asyncio.run()`.
- Drops event loop overhead by up to 2-4x, approaching Node.js / Go throughput.

## 3. Safe In-Memory Caching (`cachetools`)
- Replace unbounded Python dictionaries with `cachetools.TTLCache(maxsize=10000, ttl=300)` to prevent memory leaks in long-running bot instances.
- Ensure thread-safe cache mutations when sharing data across Flask threads and Asyncio loops using locks (`threading.Lock` vs `asyncio.Lock`).

## 4. Connection Pooling & Keep-Alive
- Re-use `aiohttp.ClientSession` with connection limits (`TCPConnector(limit=100, keepalive_timeout=60)`) rather than creating ad-hoc sessions per request.
