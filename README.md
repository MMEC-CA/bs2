# bs2
Owned by mmec-ca.

Cloudflare Worker with Durable Object support, served at `erd.mmec.ca/bs2/`.

## Architecture

- **Worker entry**: `src/worker.js` — routes dynamic requests (WebSocket upgrades under
  `*/api/signal/ws`) to a Durable Object; serves static assets via `env.ASSETS` for
  everything else.
- **Durable Object**: declared under `durable_objects.bindings` in `wrangler.jsonc`,
  implemented under `src/`. In-memory by default; use `ctx.storage` for persistent
  state (check the `migrations` block in `wrangler.jsonc` for whether the class is
  KV-backed `new_classes` or SQLite-backed `new_sqlite_classes`).
- **Static assets**: served from the directory declared in `wrangler.jsonc` under
  `assets.directory`.

## Signaling endpoint

`wss://erd.mmec.ca/bs2/api/signal/ws?peerId=<id>[&room=<code>]`

- No `room` param → peers auto-group by WAN IP (same network → same room).
- With `room=<code>` → explicit room joining, e.g. via a QR code.

## Deploy

Pushes to `main` auto-deploy via GitHub Actions (`.github/workflows/deploy.yml`).
Required repo secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.

Manual deploy:
```
npx wrangler@4 deploy
```
