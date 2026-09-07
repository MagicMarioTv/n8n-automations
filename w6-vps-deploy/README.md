# w6-vps-deploy

n8n running on a public VPS, reachable over real HTTPS at [n8n.mariomoreno.dev](https://n8n.mariomoreno.dev), not `localhost`, a machine anyone on the internet can find. Week 6 build.

Same two files' worth of concept as Week 5. The difference is everything Week 5 could leave implicit: a pinned version, a real domain, a certificate, and a second container whose only job is answering the door.

---

## Quick start

1. Provision a VPS (DigitalOcean droplet, Ubuntu 24.04, 1GB RAM was enough) and note its IPv4 address.
2. Buy a domain and add an **A record** pointing a subdomain at that IP, for example `n8n` → `198.211.112.8`. Wait for it to propagate (`getent hosts your.subdomain` should return the IP).
3. SSH in, install Docker Engine + the Compose plugin from Docker's own apt repo (not Ubuntu's bundled version, which is older).
4. Copy `docker-compose.yml` and `Caddyfile` into a directory on the server (this build used `/opt/n8n`), editing the domain in both to match yours.
5. Create `.env` next to them:
   ```
   N8N_ENCRYPTION_KEY=<a random string — this build used `openssl rand -hex 32`>
   ```
6. `docker compose up -d`
7. Visit `https://your.domain` and create the owner account.

`.env` is gitignored and is not in this repo, same rule as Week 5. This is a fresh key for this instance; it does not need to match the local Week 5 key, since this is a separate n8n install, not a migration.

---

## How it works

### `docker-compose.yml`

Same shape as Week 5's `n8n` service, plus a second container. Only what changed or is new is explained below; see Week 5's README for the rest.

| Line | What it does |
|---|---|
| `image: ...n8n:2.35.7` | **Pinned**, unlike Week 5's untagged image. n8n 2.0 shipped as a hardening release and n8n's own docs now recommend an exact version tag over the `latest`/`stable` channel. Without it, this VPS and the local Week 5 instance could silently drift onto different versions. `2.35.7` was chosen by checking what the local instance was actually running first, so both match. |
| *(no `ports:` on `n8n`)* | Deliberate removal. Week 5 published `5678:5678` straight to the browser. Here, Caddy is the only thing the outside world talks to, and `n8n` stays reachable only inside Docker's own network, by service name (`n8n:5678`), which Compose wires up automatically between services in the same file. |
| `N8N_HOST` / `N8N_PROTOCOL` | Tell n8n its real public identity: `n8n.mariomoreno.dev` over `https`, not `localhost` over `http`. |
| `N8N_WEBHOOK_URL` | The URL n8n registers with external services for webhooks. **Note:** the older `WEBHOOK_URL` variable was deprecated exactly at n8n 2.35.0. This build checked n8n's current docs before writing this line rather than relying on memorized syntax, specifically because that deprecation would have silently produced a working-looking but wrong webhook URL. |
| `N8N_PROXY_HOPS=1` | Tells n8n to trust one layer of reverse proxy in front of it, so it correctly reads the real client IP/protocol from Caddy's forwarded headers instead of seeing every request as if it came from Caddy itself. |
| `caddy:` service | The second container. Owns ports 80 and 443, the only ports exposed to the internet in this whole stack. |
| `./Caddyfile:/etc/caddy/Caddyfile` | Hands Caddy its config, read from the same directory as the compose file. |
| `caddy_data` volume | Where Caddy stores the certificate it gets from Let's Encrypt. Without persisting this, every container rebuild would mean re-requesting a fresh cert, which Let's Encrypt rate-limits. |

### `Caddyfile`

```
n8n.mariomoreno.dev {
    reverse_proxy n8n:5678
}
```

Three lines, doing a lot: the domain on its own line is enough for Caddy to request and auto-renew a real Let's Encrypt certificate for it: no separate certbot step, no manual renewal cron job. `reverse_proxy n8n:5678` forwards everything to n8n's internal address, over the Docker network, the same internal-name mechanism the compose file relies on.

**Why Caddy over nginx:** nginx would need a separate certbot install and a manual renewal timer wired up correctly. Caddy's entire pitch is folding that into the webserver itself: fewer moving parts to misconfigure on a personal box, at the cost of the finer-grained control nginx offers.

**Why a subdomain, not the root domain:** `n8n.mariomoreno.dev`, not `mariomoreno.dev`. The root is reserved for a portfolio site landing here later in the roadmap (Week 17), alongside per-project subdomains for the two remaining builds. Putting n8n there today would mean re-pointing DNS, re-issuing a certificate, and updating every webhook URL already baked into workflows, later, to make room. Deciding the domain's shape once, now, avoids that.

---

## Idempotency

Compose itself is idempotent: running `docker compose up -d` again with an unchanged file does nothing, since both containers already match what's declared. The interesting case is what happens to *data* across a full container removal, which this build tested directly rather than assumed:

```
1. Created and activated a test webhook workflow, confirmed it returns real JSON over the public URL
2. docker compose down     # removes both containers entirely
3. docker compose up -d    # rebuilds them from the same image + volumes
4. Checked the result two ways
```

**Result:** the workflow was still there and still active. The owner account was still there too, but proving that one took two tries. The already-logged-in browser tab just... stayed logged in, no prompt at all, which is *not* proof of anything: that tab held a cookie signed with the encryption key, and since the key lives in `.env` on disk (not inside the container), a cookie signed with it can still validate after a rebuild whether or not the account record itself survived. The real test was a fresh incognito window with zero prior cookie. That one correctly demanded real credentials, and they worked. **A logged-in browser tab proves the browser remembers a token. Only a fresh session proves the server remembers the account.**

---

## What broke

Two real failures, both application-level, neither infrastructure. By the time these happened, DNS, Docker, Caddy, and HTTPS were all already working correctly.

### 1. `{"code":0,"message":"Unused Respond to Webhook node found in the workflow"}`

The webhook fired, reached n8n over the public HTTPS URL, and n8n replied, just not with the configured response body. The Webhook node's **Respond** setting had defaulted to `Immediately`, which sends back n8n's own default reply the instant the request lands and never actually hands off to the connected Respond to Webhook node, hence "unused." Changed the setting to `Using 'Respond to Webhook' Node`, republished, and the real response body came back correctly on the next call.

**Worth separating clearly:** this looked like it could be a deploy problem (wrong response = something's misconfigured), but the JSON coming back at all was actually proof the deploy had already fully succeeded. Reading the message precisely, as an application-level complaint about node wiring rather than a network or certificate error, was the difference between debugging the right layer and the wrong one.

### 2. `Cannot GET /`, once, immediately after the container restart

Right after `docker compose down && docker compose up -d`, the first reload of an already-open browser tab returned this: Express's (n8n's underlying web framework) generic no-route response, not an n8n error page. A second reload seconds later worked normally. Read plainly: this was a race between the request and n8n finishing its own startup and registering its routes. The container reports `Up` the moment its process starts, not the moment it's actually ready to serve every path. Not treated as a real bug; treated as a reason to give a freshly restarted instance a few seconds before trusting the first response it gives.

---

## Limitations

- **Root-only SSH access.** No separate non-root user was created; this build SSHs in as `root` directly. A more hardened setup creates a dedicated sudo user and disables root login entirely. Skipped for time today, though worth doing before this box holds anything higher-stakes than a portfolio demo.
- **No firewall configured.** DigitalOcean droplets ship with no firewall active by default, and none was added here. Ports 22, 80, and 443 are reachable by anyone who scans the IP, not just legitimate traffic.
- **SQLite, not Postgres.** Same trade-off as Week 5, now on a box other people can actually reach. Fine for one user; a real multi-user deployment wants Postgres as a separate service in this file.
- **The volume is not backed up.** Data survives the container, not the droplet. A dead disk or a `docker volume rm` still loses everything: workflows, credentials, and the owner account alike.
- **Pinned means not auto-patched.** `2.35.7` will not pick up security fixes on its own. Upgrades are now a deliberate, tested action rather than something that happens on a routine `docker compose pull`, which is the point, but it's a responsibility, not a set-and-forget.
- **n8n 3.0's breaking changes are announced for October 2026**, during this roadmap's flagship build window. This instance stays pinned on the 2.x line through that window on purpose; the upgrade is scheduled for after the flagship ships, run through n8n's own Migration Report first.

---

## Next

Weeks 7 to 8 build Project 1 on top of this box, the first thing this VPS exists to host, rather than a test workflow proving it can.
