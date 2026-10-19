# Album art in Sonos MCP responses

Status: shipped 2026-10-19. Findings and measurements: `docs/log/2026-10-19-2239-agent-sonos-album-art-spike.md` in the ai-setup repo.

## Behavior

- Track and queue responses return `album_art` as a short URL (about 220 characters), never inline image bytes.
  - `get_info_from` (play, pause, state tools) and `get_queue` return the relay URL `https://<host>:<port>/album-art?u=<speaker art URL>`.
  - soco reports queue art as a relative path (`/getaa?...`). `get_queue` makes it absolute on the speaker, then wraps it in the relay URL.
- `GET /album-art?u=<speaker art URL>` (the relay, `album_art_proxy` in `src/sonos_mcp_server/server.py`):
  - only known speaker hosts are allowed;
  - fetches the image through `SONOS_MCP_ART_SPEAKER_IP` when set (any speaker serves the same art);
  - 30 second upstream timeout;
  - keeps up to 300 images in memory (`_ART_CACHE`); `X-Art-Cache: hit|miss` shows which;
  - `Cache-Control: public, max-age=86400`.
- `get_queue` starts a background warm-up (`_start_art_warmup`): one thread fetches the queue's art one image at a time into the cache, current track first. Only one warm-up runs at a time. Failures are skipped; the relay fetches on demand.

## Configuration

| Variable | Purpose |
|---|---|
| `SONOS_MCP_ART_SPEAKER_IP` | Speaker to fetch art from. Must be a known speaker IP, otherwise ignored. Set it to a fast speaker. |
| `SONOS_MCP_ALLOWED_HOSTS` | Existing. The first host also builds the public relay URL (`https://<host>:<SONOS_MCP_PORT>`), unless `SONOS_MCP_PUBLIC_URL` is set. |

On the mini both live in the launchd plist `sh.sonos-mcp` (one `ssh -tt localhost env ...` command string).

## Why it is built this way (measured 2026-10-19)

- A speaker serves one art request at a time, about 190 KB/s. Four parallel requests to one speaker finished at 2.5, 4.8, 7.3 and 9.6 seconds.
- Speakers differ. The same 179 KB image: Patio 3.4 s; Bridge, Family Room and Master Bedroom 0.9 to 1.5 s.
- The `s=` parameter in `/getaa?s=1&u=...` does not change the image size.
- Through the relay, a cold 19-image queue took 16.9 s wall time (about 1.1 s per image on Bridge). A cache hit took 0.16 s.
- Browser HTTP caching did not help in the cfos gadget, probably because the sandboxed iframe has an opaque origin. The relay cache covers that.
- `sonos-web` (the Pi app) uses the same speaker art URL (node-sonos `ParseDIDLItem`) and fills its queue at the same speed.

## Limits

- The first view of a queue that has not been warmed still fills in over about a second per image.
- The cache is in memory. It empties when the service restarts.
- Executor artifacts cannot show these URLs: their CSP is a hardcoded `img-src data: blob:`.
- cfos gadgets need the relay origin in `GADGET_IMG_ORIGINS` and in the gadget's blueprint `imageOrigins`.

## Not built

- Spotify CDN thumbnails via oEmbed (fast, no credentials, Spotify tracks only).
- Spreading art fetches across several speakers in parallel.
- A persistent (disk) cache.
