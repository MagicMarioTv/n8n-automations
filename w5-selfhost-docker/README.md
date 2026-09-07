# w5-selfhost-docker

n8n running locally in Docker, defined by one compose file, with data that survives the container being destroyed. Week 5 build.

Twelve lines of YAML. The build is small; the point is what it proves.

---

## Quick start

1. Install Docker Desktop. On Windows this requires WSL 2 (see *What broke*).
2. Create a `.env` file next to `docker-compose.yml` with one line:
   ```
   N8N_ENCRYPTION_KEY=<a random string you generate>
   ```
3. `docker compose up -d`
4. Open `http://localhost:5678` and create the owner account.

`.env` is gitignored and is not in this repo. Generate your own key; do not reuse one from anywhere else.

---

## How it works

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - GENERIC_TIMEZONE=America/New_York
      - TZ=America/New_York
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  n8n_data:
```

| Line | What it does |
|---|---|
| `image:` | The prebuilt n8n package, pulled from n8n's registry. Not built here, downloaded. |
| `restart: unless-stopped` | Comes back automatically after a reboot or a crash, unless stopped deliberately |
| `ports: "5678:5678"` | `HOST:CONTAINER`. The browser reaches the left number; n8n listens on the right, inside its own isolated network. They are independent; `"8080:5678"` would move the door without moving n8n. |
| `environment:` | Config passed into the container at startup |
| `${N8N_ENCRYPTION_KEY}` | Substituted from `.env` at runtime. The committed file names the secret; it never contains it. |
| `volumes: n8n_data:/home/node/.n8n` | Storage that lives outside the container, mounted where n8n keeps its database |
| bottom `volumes:` | Declares the named volume so Docker creates it |

---

## The thing this build exists to prove

n8n keeps workflows, credentials, and user accounts in a database inside the container. Containers are disposable. Without a volume, removing one destroys all of it.

The trap is that this is not obvious in daily use. **Stopping and starting the same container preserves the data**, because the container's writable layer survives a stop. So the setup appears to work, for weeks. The loss happens on removal, which is what `docker compose down` does and what every version upgrade does. The mistake and the consequence are separated by enough time that the connection is easy to miss.

### Tested, not assumed

```
1. Created a workflow named volume-test
2. docker compose down     # removes the container entirely
3. docker compose up -d    # builds a brand new one
4. Refreshed the browser
```

**Result:** the workflow was still there. So was the owner account, confirmed by opening the instance in a private window, which prompted for login rather than letting me in, proving the user record persisted rather than a stale cookie fooling me.

The whole database survived a container that no longer exists. That is the volume doing its job.

---

## What broke

Three failures, all in setup rather than in n8n. All three were readable from the output.

### 1. Docker Desktop would not start: WSL missing

```
c:\windows\system32\wsl.exe --version: exit status 1
```

The output was not a version and not an error. It was **usage text**, which is what a program prints when it does not recognize an argument. And the usage list was short: only `--install`, `--list`, `--status`, `--help`, with none of `--shutdown`, `--terminate`, `--export`. That short list is the signature of the bootstrap stub Windows ships to install WSL, not a working WSL.

Docker Desktop runs containers inside WSL 2. There was no WSL. Fixed with `wsl --install` from an elevated prompt plus a reboot.

**The lesson:** the diagnosis was not in the error line, it was in the *shape* of what got printed instead.

### 2. `no configuration file provided: not found`

Ran `docker compose up -d` from the repo root rather than the folder holding `docker-compose.yml`. Compose looks in the current directory only.

The prompt shows where you are standing. That is the first thing to check when a command cannot find something.

### 3. `additional properties 'environemnt' not allowed`

A typo: `n` and `m` transposed. Caught by Compose's schema validation *before* anything was pulled or created.

Worth comparing against the Week 4 build. There, `category` was typed as a plain string, so `"Promotional"`, `"promotional"` and `"Automated/Promotional"` all validated fine and the inconsistency only surfaced on inspection. Here, a strict schema caught a two-letter mistake in under a second and refused to proceed.

**Same mechanism, opposite outcome.** Strict validation is friction for four seconds and prevents silent garbage. Loose validation feels frictionless until something downstream quietly drops data.

---

## Limitations

- **No HTTPS.** The login travels in plaintext. Irrelevant on localhost, unacceptable the moment this has a public address. This is the first thing Week 6 has to fix.
- **`localhost` is not security.** Nothing here is locked down; it is simply unroutable from outside this machine. Change the address and the protection disappears while the config stays identical.
- **SQLite by default.** Fine for one user. A real deployment wants Postgres, which means a second service in this file.
- **The volume is not backed up.** Data survives the container, not the machine. `docker volume rm` or a dead disk still loses everything.
- **No resource limits.** No memory or CPU ceiling on the container.
- **Encryption key is single-copy.** Lose the `.env` and every stored credential becomes unrecoverable, because that key is what decrypts them.

---

## Next

Week 6 puts this same file on a VPS with a real domain and HTTPS, which turns every item above from theoretical into load-bearing. Same twelve lines, a public IP, and consequences.
