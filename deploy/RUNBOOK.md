# Runbook

How Bot Arena runs in production, and what to do when something has to change. ADR-010 explains why it's built this way.

```
browser ──► Cloudflare Pages  <project>.pages.dev
             ├─ static site + Pyodide           (free, unlimited)
             └─ /api /auth /ws ─► Pages Function (web/src/proxy.ts), adds X-Arena-Origin
                                   │ 100,000 requests/day, then error 1027
                                   ▼
            Google Cloud e2-micro  <name>.duckdns.org   (1 GB/month egress free)
             Caddy (TLS; 403 without the secret; 503 once EGRESS_CAPPED exists)
             └─► arena-api :8000 · arena-worker@1 (jails) · arena-scheduler
                 timers: ops guard (5 min) · ops backup (hourly) ─► gs://<bucket> (same region)
```

Data lives in `/var/lib/arena`, code in `/opt/arena/src` (a git checkout), the virtualenv in `/opt/arena/venv`, and secrets in `/etc/arena/*.env`. To run `ops` commands on the VM:

```bash
sudo -u arena ARENA_DATA_DIR=/var/lib/arena /opt/arena/venv/bin/python -m arena_server.ops status
```

The rest of this file writes that as `ops <command>`.

---

## First setup (the owner, once)

Every account here is free, and none of the steps below creates anything billed. Use the exact flags given: other machine types, disk types and regions are billed.

### 1. Google Cloud

1. Create a project and a billing account at console.cloud.google.com. Google requires a billing account even for the Free Tier.
2. **Budget alert:** Billing → Budgets & alerts → create a budget of €1 with an alert at 1%. Any charge at all then sends you an email.
3. In Cloud Shell or a local `gcloud`, with `PROJECT`, `BUCKET` and `REGION=us-central1` set:

```bash
gcloud config set project "$PROJECT"
gcloud services enable compute.googleapis.com storage.googleapis.com
gcloud iam service-accounts create arena-vm --display-name "Bot Arena VM"
gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=deploy/gcs-lifecycle.json
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:arena-vm@$PROJECT.iam.gserviceaccount.com" --role=roles/storage.objectAdmin
gcloud compute instances create arena --zone="$REGION-a" --machine-type=e2-micro --image-family=debian-13 --image-project=debian-cloud --boot-disk-size=30GB --boot-disk-type=pd-standard --service-account="arena-vm@$PROJECT.iam.gserviceaccount.com" --scopes=storage-rw --tags=arena-web
gcloud compute firewall-rules create arena-web --allow=tcp:80,tcp:443 --target-tags=arena-web
gcloud compute instances describe arena --zone="$REGION-a" --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

The bucket holds private bot code. `--public-access-prevention` keeps it from ever being made public.

### 2. A free subdomain

At duckdns.org, create a name such as `bot-arena` and point it at the IP printed above. The IP only changes if the VM is **stopped and started**, not on a reboot; after that, update it here again.

### 3. GitHub login

Create an OAuth app at github.com/settings/developers:
- Homepage: `https://<project>.pages.dev`
- Callback URL: `https://<project>.pages.dev/auth/github/callback`

### 4. The VM

```bash
gcloud compute ssh arena --zone="$REGION-a"
sudo apt-get install -y git && git clone https://github.com/tomeelow/bot-arena.git /tmp/bot-arena
sudo sh /tmp/bot-arena/deploy/install.sh
```

Then fill in the three env files. `.env.example` lists every variable, and which file it goes in:

| File | Holds |
|---|---|
| `/etc/arena/api.env` | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET` |
| `/etc/arena/caddy.env` | `ARENA_HOST=bot-arena.duckdns.org`, `ARENA_ORIGIN_SECRET` |
| `/etc/arena/backup.env` | `ARENA_BACKUP_BUCKET=<bucket>` |
| `/etc/arena/alerts.env` | `ARENA_HEALTHCHECK_URL=<ping url>`, optional (see Alerts) |

Also add `ARENA_ADMIN_GITHUB_IDS=<your GitHub user id>` to `api.env`, so you can open `/admin`. To find your id, run `curl -s https://api.github.com/users/<you>`.

Generate each secret with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Then deploy:

```bash
sudo arena-update "$(git -C /opt/arena/src rev-parse origin/main)"
curl -s https://bot-arena.duckdns.org/health
```

### 5. Cloudflare Pages

1. In the Cloudflare dashboard, go to Workers & Pages → Create → Pages → *Direct upload*, and name the project (the `<project>` above).
2. Under Settings → Variables and secrets, for Production, add:
   - `ORIGIN` = `https://bot-arena.duckdns.org`
   - `ORIGIN_SECRET` (type *Secret*), the same value as on the VM.
3. Publish the first time from your machine:

```bash
cd web && npm run build && npx --yes wrangler@4.168.0 pages deploy build --project-name <project> --branch main
```

### 6. Turn on deploys from CI

1. On the VM, create a deploy key that can only run `arena-update`:

```bash
sudo -u deploy install -d -m 700 /home/deploy/.ssh
sudo -u deploy ssh-keygen -t ed25519 -N '' -f /home/deploy/ci
echo "restrict,command=\"/usr/local/sbin/arena-deploy-ssh\" $(sudo cat /home/deploy/ci.pub)" | sudo -u deploy tee /home/deploy/.ssh/authorized_keys
sudo cat /home/deploy/ci && sudo rm /home/deploy/ci /home/deploy/ci.pub
ssh-keyscan bot-arena.duckdns.org
```

2. In the GitHub repo, under Settings → Secrets and variables → Actions, add:

| Kind | Name | Value |
|---|---|---|
| Secret | `DEPLOY_SSH_KEY` | the private key printed above |
| Secret | `DEPLOY_KNOWN_HOSTS` | the `ssh-keyscan` output |
| Secret | `CLOUDFLARE_API_TOKEN` | a token with *Cloudflare Pages: Edit* only |
| Variable | `DEPLOY_HOST` | `bot-arena.duckdns.org` |
| Variable | `CLOUDFLARE_ACCOUNT_ID` | your Cloudflare account id |
| Variable | `PAGES_PROJECT` | `<project>` |
| Variable | `DEPLOY` | `on` |

### 7. First checks

1. Log in on the site, upload the starter bot, and watch it validate in the jail:

```bash
journalctl -u arena-worker@1 -f
```

2. Once its placement matches have played, run `ops check`.
3. Do the restore drill below and the kill-switch test, and tick their Phase 9 boxes.

---

## Deploy and roll back

- **Deploy:** merging to `main` does it once `verify` passes. To deploy by hand, run `sudo arena-update <sha>`.
- **Roll back:** run `sudo arena-update <older sha>`. `cat /opt/arena/deployed` shows the current sha.
- **Matches in flight:** a deploy restarts the worker. A match it cuts off is voided by the reaper (after the 20-minute lease) and queued again. It's never rated.
- **Migrations** run on deploy (`ops bootstrap`). They only move forward, so rolling back across a migration means restoring a backup taken before it.

## The kill switch

```bash
ops pause "why"
ops status
ops resume
```

- `pause` stops bot execution and scheduling, and queued matches stay queued. A match already running finishes.
- To stop a running match too, add `sudo systemctl stop arena-worker@1`. The reaper voids it later.
- Use the full stop for anything that looks like a jail escape. Then write an adversarial bot that reproduces it, before you fix anything.

## Budget caps

| Cap | Where | When it's hit |
|---|---|---|
| `matches_per_day` | `settings.toml [budget]` | The scheduler queues nothing more that day |
| `egress_month_bytes` | `settings.toml [budget]` | `ops guard` writes `EGRESS_CAPPED`, and every API call gets 503 until the 1st |
| `disk_pause_fraction` | `settings.toml [budget]` | `ops guard` pauses the ladder. Free space, then run `ops resume` |
| `logs_keep_days`, `live_keep_days` | `settings.toml [budget]` | Older bot logs and live frame files are deleted |
| uploads, comparisons, viewers | `settings.toml [api]` | 429 or 1013 for that user or viewer |
| Pages Functions, 100,000 a day | Cloudflare | Error 1027 until midnight UTC |

**If the egress cap trips early,** find what's sending: `journalctl -u caddy`, and `ops status` for the count. You can lower the cap, but raising it past the free 1 GB means a bill. That needs an ADR, not a config change.

**Once a month,** check Google Cloud Billing → Reports and Cloudflare's usage page, and confirm both show €0.

## Alerts and the health page

`/admin` shows the platform's health to admins: errors, queue wait, match durations, disk and end reasons. `/stats` is the public usage page.

Alerts reach you by email through Healthchecks.io (ADR-011):

1. Create a free Hobbyist account and a check. Set the period to 5 minutes and the grace time to 10 minutes.
2. Put the check's ping URL in `/etc/arena/alerts.env` as `ARENA_HEALTHCHECK_URL`.
3. Wait for the next `arena-guard` run, then look at the check's log.

The check fails, and you get an email, when any of these happens:

| Alert | Threshold |
|---|---|
| A platform error | Any in the last 24 hours |
| Disk full | 80% (`alert_disk_fraction`) |
| Queue wait | A match waited more than an hour (`alert_queue_wait_s`) |
| Ladder paused | The kill switch, or the guard's disk pause |
| Egress cap | This month's budget is spent |
| No ping at all | The VM, the timer or the guard is down |

The failure's body lists the reasons, and so does the guard's journal:

```bash
journalctl -u arena-guard
```

## Backups and the restore drill

`arena-backup.timer` runs hourly. `journalctl -u arena-backup` shows what each run uploaded. To confirm the latest snapshot and the file bundles are there:

```bash
gcloud storage ls "gs://$BUCKET/db/"
gcloud storage ls "gs://$BUCKET/files/"
```

**The drill rebuilds a fresh VM in under an hour.** Time it.

1. `ops pause`, then stop the old VM:

```bash
gcloud compute instances stop arena --zone=...
```

   Stopping first keeps the two VMs from running together. The extra disk only exists for the drill and costs less than a cent; if that's too much, rehearse on the same VM instead (step 4).

2. Create `arena-2` with the same command as in First setup, then run `install.sh` and fill in the three env files.
3. Restore, then start the server:

```bash
sudo -u arena ARENA_DATA_DIR=/var/lib/arena ARENA_BACKUP_BUCKET=<bucket> /opt/arena/venv/bin/python -m arena_server.ops restore
ops check
sudo arena-update <sha>
```

   `ops check` must say `ok`: the ratings rebuilt from results equal the stored ratings, and no replay or bot file is missing.

4. Point DuckDNS at the new IP and check the site. Then delete the old VM:

```bash
gcloud compute instances delete arena --zone=...
```

   **Same-VM rehearsal** (no second disk): restore into another directory.

```bash
sudo install -d -o arena /var/lib/arena-drill
sudo -u arena ARENA_DATA_DIR=/var/lib/arena-drill ARENA_BACKUP_BUCKET=<bucket> /opt/arena/venv/bin/python -m arena_server.ops restore
sudo -u arena ARENA_DATA_DIR=/var/lib/arena-drill /opt/arena/venv/bin/python -m arena_server.ops check
```

   Then remove `/var/lib/arena-drill`.

What a restore can lose: up to an hour of results, plus bot logs (which aren't backed up; they're private debug output and expire anyway).

## Rotating secrets

- **`SESSION_SECRET`:** edit `/etc/arena/api.env`, then `sudo systemctl restart arena-api`. Everyone is logged out.
- **`GITHUB_CLIENT_SECRET`:** generate a new one in the OAuth app, put it in `api.env`, and restart `arena-api`.
- **`ARENA_ORIGIN_SECRET`:**
  1. Set the new value in Pages (`ORIGIN_SECRET`) and redeploy Pages, or wait for the next deploy.
  2. Then update `/etc/arena/caddy.env` and run `sudo systemctl restart caddy`.

  API calls fail with 403 between the two steps.
- **Deploy key:** repeat First setup step 6 and replace `DEPLOY_SSH_KEY`.

## Bumping the engine version (a new season)

An incompatible rules, observation, order or replay change bumps `ENGINE_VERSION` (CLAUDE.md, "Ask before acting").

- **What happens today:** workers void queued matches made for another engine version, and old replays only re-simulate with the engine that made them.
- **Not built yet:** what a season keeps, i.e. how old results, replays and ratings are archived and how the new ladder starts. Decide that in an ADR before the first incompatible bump.

## Logs

```bash
journalctl -u arena-api -u arena-worker@1 -u arena-scheduler -u arena-guard -u arena-backup --since today
```

Logs carry match ids, version ids, end reasons and durations, never bot code or observations.
