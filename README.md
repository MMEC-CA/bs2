# bs2
Owned by mmec-ca.

This repository contains a Cloudflare Workers site served at `erd.mmec.ca/bs2/`.

## Deployment

Pushes to `main` auto-deploy via GitHub Actions (`.github/workflows/deploy.yml`).
Required repo secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.

Manual deploy:
```
npx wrangler@4 deploy
```

## Upgrading to a dynamic Worker (Durable Objects, KV, etc.)

This scaffold is static-assets only. To add dynamic capabilities, mirror the
`gm1` pattern: add a `main: "./src/worker.js"` entry, move assets into a
subdirectory (e.g. `./_site`), and declare Durable Object / KV bindings in
`wrangler.jsonc`. The Cloudflare account hosting these sites already supports
Durable Objects and WebSockets.
