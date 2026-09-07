# n8n-automations

Weekly automation builds, one folder per week. Part of a 28-week push from media content operations into AI workflow automation.

Each build ships whether or not it's pretty. Every folder has the exported workflow JSON and a README covering what it does, why it's built that way, what broke, and what it can't do yet.

I work in content operations at Warner Bros. Discovery, where I automate encoding and OTT delivery pipelines. These are the deliberate practice builds.

## Builds

| Week | Build | What it covers |
|---|---|---|
| 1 | [w1-rss-notifier](./w1-rss-notifier) | RSS polling, keyword filtering, Discord webhook |
| 2 | [w2-webhook-http](./w2-webhook-http) | Inbound webhooks, payload validation, structured HTTP responses |
| 3 | [w3-gmail-auto-label](./w3-gmail-auto-label) | Gmail OAuth2, API vs workflow filtering, per-item writes |
| 4 | [w4-ai-email-digest](./w4-ai-email-digest) | Basic LLM Chain, structured output validation, cost per run |
| 5 | [w5-selfhost-docker](./w5-selfhost-docker) | Docker Compose, volumes and data persistence, env-var secrets | 
| 6 | [w6-vps-deploy](./w6-vps-deploy) | Public VPS, pinned version, Caddy reverse proxy, real HTTPS |
| 7–8 | [w7-media-request-triage](./w7-media-request-triage) | Public form intake, enum-constrained classifier, hand-labeled eval set *(day 1 of 2 — ships 2026-09-12)* |

## Themes I care about

Automation that runs once in a demo is easy. These builds pay attention to the parts that decide whether something survives in production:

- **Idempotency** — what happens if this runs twice?
- **Error handling** — retries, backoff, and where failures land
- **Cost** — which steps actually need an LLM, and which are just plumbing
- **Verification** — how do you know it worked, rather than assuming

## Stack

n8n (self-hosted and cloud) · Python · REST APIs · webhooks · Docker
