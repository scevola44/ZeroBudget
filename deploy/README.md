# Self-hosted deploy — Proxmox LXC

This folder is everything you need to run ZeroBudget on a self-hosted LXC
container and keep it automatically up to date with the `develop` branch —
without exposing the LXC to the internet or running any tunnel.

## How it works

```
 ┌─────────────────────────┐    merge to develop    ┌───────────────────────┐
 │ GitHub Actions (ci.yml) │  ───────────────────▶  │ ghcr.io/scevola44/    │
 │  backend + frontend +   │   build & push         │ zerobudget:develop    │
 │  deploy jobs            │                        │ (+ sha-<short> tag)   │
 └─────────────────────────┘                        └─────────┬─────────────┘
                                                              │ poll every 5m
                                                              ▼
                                              ┌────────────────────────────┐
                                              │ Proxmox LXC                │
                                              │  ├── db  (postgres:16)     │
                                              │  ├── app (GHCR image)      │
                                              │  └── watchtower            │
                                              └────────────────────────────┘
```

All traffic is **outbound** from the LXC. Nothing inbound from the internet
is required.

## One-time LXC bootstrap

These steps assume a fresh, unprivileged Debian 12 LXC with outbound network
access and root shell.

### 1. Install Docker

```sh
curl -fsSL https://get.docker.com | sh
```

This gives you `docker` and the `docker compose` plugin.

### 2. Log in to GHCR so the LXC can pull the image

Because `scevola44/zerobudget` is a private repository, the LXC needs read
access to GHCR. Create a classic Personal Access Token on GitHub with the
single scope `read:packages`, then on the LXC:

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u scevola44 --password-stdin
```

This writes `/root/.docker/config.json`, which the Watchtower container
mounts read-only so it can keep polling GHCR after the initial pull.

### 3. Drop this `deploy/` folder on the LXC

Either clone the repo (`git clone https://github.com/scevola44/zerobudget.git`)
or `scp` just the `deploy/` folder over — the LXC does **not** need the
application source code, only the compose file.

### 4. Create the secrets file

```sh
cd deploy
cp .env.example .env
# Edit .env and replace the placeholders.
# In particular, generate a real JWT_SECRET:
#   openssl rand -hex 32
```

### 5. Start the stack

```sh
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

First boot will:

1. Pull `postgres:16-alpine` and `ghcr.io/scevola44/zerobudget:develop`.
2. Start Postgres and wait for `pg_isready`.
3. Start the app container, which runs `alembic upgrade head` and then
   `uvicorn app.main:app` on port 8000.
4. Start Watchtower, which begins polling GHCR every 5 minutes.

### 6. Verify

```sh
curl http://localhost:8000/api/health
# → {"status":"ok"}

docker compose logs -f app         # app boot + alembic output
docker compose logs -f watchtower  # scan cycles, update decisions
```

## The auto-update loop (what you should expect)

1. Open a PR against `develop` on GitHub → `backend` + `frontend` CI jobs run.
2. Merge the PR → the `deploy` job builds the Docker image and pushes two
   tags to GHCR: `:develop` (rolling) and `:sha-<shortsha>` (immutable).
3. Within ~5 minutes (the `--interval=300` in the compose file), Watchtower
   on the LXC notices that `:develop` now points to a new digest, pulls the
   new image, stops the `app` container, and starts a new one from the new
   image. Postgres is left alone because it does **not** carry the
   `com.centurylinklabs.watchtower.enable` label.
4. The new `app` container runs `alembic upgrade head` on startup, so any
   new migrations apply automatically.

## Rollback

Every successful deploy also publishes an immutable `sha-<shortsha>` tag.
To roll back to a previous version, edit `docker-compose.prod.yml` on the
LXC and pin the app image, e.g.:

```yaml
  app:
    image: ghcr.io/scevola44/zerobudget:sha-abc1234
```

Then:

```sh
docker compose -f docker-compose.prod.yml --env-file .env up -d app
```

Watchtower will leave the pinned image alone as long as the tag stays the
same. When you want to resume auto-updates, change the tag back to
`:develop` and `docker compose up -d app` again.

## Operational notes

- **Logs**: `docker compose logs -f <service>` (service is `app`, `db`, or
  `watchtower`).
- **Database backups**: not wired up here. The `pgdata` named volume
  persists across restarts; back it up with your preferred Postgres backup
  tool (e.g. `pg_dump` on a cron, or a Proxmox volume snapshot).
- **Changing the poll interval**: edit the `--interval=300` flag in
  `docker-compose.prod.yml`. Values are in seconds.
- **Internet exposure** is deliberately out of scope for this file. If you
  ever want public access, put a reverse proxy (e.g. Caddy or Traefik) on a
  separate LXC and forward only that proxy to the internet — not this one.
