# Deploying the Terra.ai demo (single VPS, invite-only)

This guide takes you from a bare Ubuntu VPS to a live, TLS-secured, invite-only demo at
`https://your-domain` in under an hour. The stack is defined in `docker-compose.prod.yml`:

- **caddy** — the only public-facing service (ports 80/443). Terminates TLS with an
  automatic Let's Encrypt certificate and reverse-proxies to the UI (WebSockets included).
- **ui** — Streamlit frontend. All API calls happen server-side inside the Streamlit
  process, so only this one domain is needed; the API is never exposed to browsers.
- **api** — FastAPI backend. Internal docker network only, no public port.
- **ollama** — local LLM runtime. Internal only. Optional at runtime: the demo works
  without any model pulled (see [VPS sizing](#1-pick-a-vps)).

## 1. Pick a VPS

| Mode | Min RAM | Recommended |
|---|---|---|
| Heuristic-only (summarizer "none", hash embeddings) | **2 GB, 1 vCPU** | 4 GB, 2 vCPU |
| With `llama3.2` (3B) + `nomic-embed-text` pulled | **6 GB, 2 vCPU** | 8 GB, 4 vCPU |

Disk: 25 GB is plenty (images ~3 GB, llama3.2 ~2 GB, nomic-embed-text ~0.3 GB).

If your VPS is too small for an LLM, that's fine: pick summarizer **"none"** in the UI
and the app uses a deterministic heuristic summarizer — answers are still KB-grounded
and citation-backed, just less fluent. You can skip step 7 entirely in that case.

Any Ubuntu 22.04/24.04 (or Debian 12) box from Hetzner/DigitalOcean/Linode works.

## 2. Point DNS at the VPS

At your DNS provider, create an **A record** for the demo domain pointing at the VPS's
public IPv4 address, e.g.

```
demo.yourcompany.com    A    203.0.113.10
```

Wait until `dig +short demo.yourcompany.com` (or an online DNS checker) returns the IP.
Let's Encrypt will fail if DNS isn't propagated yet. Also make sure the VPS firewall /
cloud security group allows inbound **80** and **443**.

## 3. Install Docker + the compose plugin

SSH in as root (or a sudo user) and run Docker's official install script:

```bash
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version   # both should print versions
```

(The script installs the `docker compose` plugin. On Ubuntu you can equivalently
`apt install docker.io docker-compose-v2`.)

## 4. Clone the repo

```bash
git clone <your-repo-url> terra-ai
cd terra-ai
```

## 5. Write the `.env` file

Create `.env` in the repo root (`nano .env`). Every variable, one line each:

```bash
# REQUIRED — the domain from step 2. Caddy gets a Let's Encrypt cert for it.
DEMO_DOMAIN=demo.yourcompany.com

# REQUIRED for invite-only multi-user mode — your Supabase project's URL and anon key
# (Supabase dashboard -> Project Settings -> API). If you leave BOTH unset, the app
# runs in single-user "local" mode with no login screen — do NOT do that on a public demo.
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...

# REQUIRED for invite-only signups — the code new users must enter to register.
# Anything long and unguessable; share it privately with invitees.
DEMO_INVITE_CODE=some-long-random-string

# OPTIONAL — enables the web-search fallback when the KB can't answer. Omit to keep
# the demo KB-only (answers fall back to "no answer" / model knowledge instead).
TAVILY_API_KEY=tvly-...

# OPTIONAL — per-user request throttle (requests/minute). Omit for the default.
RATE_LIMIT_PER_MINUTE=20
```

Never commit `.env` — it holds secrets.

## 6. Build and start

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes a few minutes. Caddy will fetch the TLS certificate on first request;
within ~30 seconds `https://demo.yourcompany.com` should show the Terra.ai login screen.

## 7. Pull the Ollama models (skip on a small VPS)

```bash
docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.2
docker compose -f docker-compose.prod.yml exec ollama ollama pull nomic-embed-text
```

Models persist in the `ollama_models` volume, so this is one-time. In the UI, pick
summarizer `ollama:llama3.2`; on a small VPS leave it on `none` (heuristic).

## 8. Create the first user

Open `https://demo.yourcompany.com`, click **Sign up**, enter an email + password and
the `DEMO_INVITE_CODE` value from your `.env`. If your Supabase project has email
confirmation enabled (Auth -> Providers -> Email), either confirm via the email link or
turn confirmation off for a friction-free demo. Each user gets isolated chats/memories.

## 9. Sanity checks

```bash
# All four services should be "Up" / "running"
docker compose -f docker-compose.prod.yml ps

# Watch logs (Ctrl-C to exit). Look for uvicorn "Application startup complete"
# and no Caddy certificate errors.
docker compose -f docker-compose.prod.yml logs -f --tail=100

# Health check from INSIDE the docker network (the API has no public port):
docker compose -f docker-compose.prod.yml exec api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz').read().decode())"

# Cross-container variant (also proves the internal DNS name 'api' resolves):
docker compose -f docker-compose.prod.yml exec caddy wget -qO- http://api:8000/healthz
```

Then, in the browser: log in, ask a finance question ("how do I build an emergency
fund?") and a healthcare question, and confirm answers carry citations.

## 10. Rotating the invite code

When a code leaks or a demo round ends:

```bash
nano .env                          # change DEMO_INVITE_CODE
docker compose -f docker-compose.prod.yml up -d api   # recreate api with the new env
```

Existing users keep working (they already have accounts); only *new* signups need the
new code.

## Everyday operations

```bash
# Update to the latest code
git pull && docker compose -f docker-compose.prod.yml up -d --build

# Stop / start everything
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# What's using the RAM?
docker stats --no-stream
```

Data (vector indexes, chat/memory/analytics SQLite DBs) lives in the `app_data` volume
and pulled models in `ollama_models` — both survive `down`/`up` and rebuilds. Only
`docker compose down -v` deletes them, so don't pass `-v` unless you mean it.
