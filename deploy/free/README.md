# Free hosting setup for the training project

**Using Google Cloud instead?** Follow [the GCP trial deployment guide](GCP.md).
The same Compose stack works on an Ubuntu x86-64 VM. GCP uses temporary trial
credits rather than Oracle's ongoing Always Free allowance.

**Plan checked: 10 November 2026.** This setup prepares the application for one
Oracle Always Free VM. It does not create a cloud account, provision a VM, publish
the application, or enroll anything in a paid plan. You keep your existing Claude
key: **hosting is the free part; Claude API calls remain billable**.

## What runs where

```text
Browser --HTTPS--> Caddy --HTTP--> Nginx / React
                                    |
                                  /api/
                                    |
                                  FastAPI
                                 /   |   \
                       PostgreSQL  Qdrant  Redis --> RQ worker
```

All services run on the same VM. No managed PostgreSQL, managed vector database,
paid Redis, paid worker, load balancer, purchased domain, GPU, or CDN is required.
Only Caddy publishes ports 80 and 443. The API, worker, PostgreSQL, Qdrant, and
Redis stay on the private Docker network. Nginx forwards HTTPS information to
the API; Uvicorn trusts only the configured private application subnet.

Named volumes retain original files/learning data, vector data, Redis queue data,
downloaded model artifacts, and TLS certificates. Uploaded originals remain in
PostgreSQL, not repository folders. The deployment has its own Compose project
and starts with an empty database: your Windows development data is not copied
to the server automatically.

## 1. Create only an eligible Always Free VM

Use the Oracle Console, not a paid VM trial recipe. The current official allowance
for an Always Free tenancy is equivalent to **2 Ampere A1 OCPUs and 12 GB RAM**,
with **200 GB total block-volume allowance**, including boot disks. Other account
resources count toward these totals. Choose one eligible Ubuntu ARM64 VM in your
home region, at most 2 OCPUs/12 GB, and a 50 GB boot disk. Confirm the Console marks
the entire configuration as free before creating it. Do not upgrade to PAYG or
substitute a paid shape if free capacity is unavailable.

Account/identity verification may require a card. Capacity is not guaranteed, and
idle VMs may be reclaimed; keep external backups. Free-tier policies can change.
This setup cannot guarantee eligibility or make an unavailable VM available.
The 1 GB AMD micro shape is not a suitable substitute for this full ML stack.

Sources: [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[Oracle Free Tier/account terms](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

## 2. Set up a free hostname and network access

1. Register a free subdomain at [Duck DNS](https://www.duckdns.org/) and point it
   to the VM's public IPv4 address. Use your own unique name, not the example here.
2. In OCI's network security rules, allow TCP 80/443 from the internet. Restrict
   TCP 22 to your own IP for SSH. Do not open 5432, 6333, 6379, or 8000 publicly.
3. Ensure the Ubuntu host firewall also permits 80/443 and your restricted SSH
   connection. OCI rules and the OS firewall are separate layers; Docker-published
   ports must be considered when reviewing host firewall behavior.
4. If you publish an AAAA record, it must point to a working IPv6 route to the VM;
   otherwise remove the stale record in your DNS account.

Caddy obtains and renews free public HTTPS certificates when DNS and inbound
80/443 work. Keep its data volume. Browser microphone features need a secure
context, so use the HTTPS hostname rather than the raw public IP.
[Caddy automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).

## 3. Install prerequisites and copy the code

SSH to your VM using the key you created in OCI. On Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git python3
sudo systemctl enable --now docker
git clone https://github.com/BhargaviAlimilli/Study-Mate.git
cd Study-Mate
```

The deployment files must first be committed/pushed to your repository, or copied
to the VM over your authenticated SSH connection. No push is performed by this
setup. For Docker installation alternatives use the
[official Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/).

Use Docker Compose v2. If your user cannot access Docker, the commands below use
`sudo` rather than automatically granting Docker-group access. You do not need
Node or the full Python dependency environment on the VM; builds happen inside
containers. Initial builds/downloads can take several minutes on the free CPU.
Use native ARM64 images; do not force the server to emulate x86.

## 4. Prepare private configuration

From the repository root on the VM:

```bash
python3 deploy/free/prepare_env.py --domain YOUR-NAME.duckdns.org
```

It prompts privately for your existing Claude key and generates independent random
PostgreSQL and JWT secrets. It writes `deploy/free/.env` with restrictive permissions
and refuses to overwrite an existing file. `.env` is ignored by Git. Do not paste
it into chat, terminal recordings, issues, or a repository.

If preparing locally on Windows with the existing virtual environment, the helper
can copy the key from your already ignored backend configuration without printing it:

```powershell
.\.venv\Scripts\python.exe deploy/free/prepare_env.py --domain YOUR-NAME.duckdns.org --reuse-backend-key
```

Copy that private file to `deploy/free/.env` on the VM using SSH/SCP and keep its
permissions restricted. Do not copy your entire development `.env`: local
addresses and credentials are different. Never regenerate the deployment secrets
on every update; changing a PostgreSQL environment password does not automatically
change an existing database volume's password.

Check it without displaying secrets:

```bash
python3 deploy/free/prepare_env.py --check
```

`APP_SUBNET` defaults to `172.29.0.0/24`. If that subnet conflicts with another VM
network, choose an unused private /24 and keep it consistent; the Compose file
uses it for both network addressing and the trusted reverse-proxy range.

## 5. Deploy

Run from the repository root:

```bash
sudo bash deploy/free/deploy.sh
```

The script checks configuration, builds the backend/frontend, stops this demo's
old app processes during upgrades, starts storage, runs migrations/checkpoint
setup, starts the API/worker, waits for API health, then starts the frontend and
TLS edge. It does not touch the separate local-development Compose project.
Stop/start causes a short maintenance window. Original data remains in volumes.

Open `https://YOUR-NAME.duckdns.org`. The first certificate request and first
embedding-model download can take time. `--wait` health checks establish process
startup, not correct answers or every downstream capability.

## 6. Create your learner account

**Public registration is disabled by default in this shared deployment.** This
prevents anyone who finds the URL from creating an account and spending your
Claude credits. Normal local development keeps registration enabled.

Create an owner/tester account from the VM terminal:

```bash
sudo docker compose --env-file deploy/free/.env -f deploy/free/compose.yml exec api python -m app.create_user --email YOUR-EMAIL --name YOUR-NAME
```

The password is prompted twice and hashed normally; it is not a command argument
or stored in the deployment configuration. Sign in through the website with that
account. You can create additional tester accounts using the same command. The
existing Create account screen returns an understandable 403 when registration
is disabled. Setting `ALLOW_REGISTRATION=true` and redeploying explicitly enables
public registration if you later choose to accept that usage.

No OpenAI key is required for browser dictation/read-aloud. Claude still handles
answers/images/quizzes. Do not enable paid optional providers by accident.

## 7. Verify the deployment

From the VM or another machine with Python:

```bash
python3 deploy/free/check_public.py https://YOUR-NAME.duckdns.org
```

This verifies the frontend, `/api/health`, HTTPS certificate validation, and the
unauthenticated rejection at `/api/auth/me`. It sends no model requests and needs
no token. It deliberately does not disable TLS verification.

Then manually sign in, upload a small public PDF, observe queued -> ready, ask a
question, open evidence, complete a quiz, revisit feedback/history, and test voice.
Use the root release checklist for the complete workflow. Real Claude requests
consume your account's normal quota/credits. Caddy exposes the canonical `/mcp`
endpoint and `/.well-known/*` metadata directly to the backend, while REST uses
`/api/`. Use preconfigured bearer-token MCP clients: the application does not
provide an external-client OAuth login/consent flow.

Read logs without printing resolved configuration:

```bash
sudo docker compose --env-file deploy/free/.env -f deploy/free/compose.yml ps
sudo docker compose --env-file deploy/free/.env -f deploy/free/compose.yml logs --tail 80 edge api rq-worker
```

Avoid bare `docker compose config`: resolved output includes secrets. Use
`config --quiet` for validation. Do not share logs containing private data.

## 8. Updates and backups

Before an update, make a PostgreSQL backup outside the repository:

```bash
sudo bash deploy/free/backup.sh /var/backups/study-mate
git pull --ff-only
sudo bash deploy/free/deploy.sh
```

Copy backups off the VM using SSH/SCP. A dump on a reclaimed/deleted VM is not an
external backup. The PostgreSQL dump includes originals, learning data, and graph
checkpoints; it does not include Qdrant, Redis, or TLS volumes. To make a complete
volume backup, stop this demo cleanly and back up all named volumes using the
[Docker volume backup/restore procedure](https://docs.docker.com/engine/storage/volumes/#back-up-restore-or-migrate-data-volumes),
then start it again. Restore into a disposable instance and verify before relying
on backups. Do not run `down -v`: it deletes retained data.

The deployment does not automatically prune checkpoints/files or enforce per-user
storage/model quotas. Use small public training PDFs, a few invited accounts, and
your provider's available usage controls. Budget alerts are not guaranteed hard
spending caps. No free-hosting plan makes Claude requests free.

## Why this deployment instead of several free managed services?

- [Render free services](https://render.com/docs/free) do not include a free
  background worker; its free web compute is also a poor fit for this CPU-embedding
  stack. A blueprint requiring a paid worker would violate this task's budget.
- [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview) now require
  a paid subscription to create new Docker/Gradio compute Spaces on CPU Basic;
  the zero hourly hardware price does not make account eligibility free.
- This recipe uses no trial credits. If OCI has no available eligible free VM,
  it stops at that requirement rather than silently switching to paid resources.
  The existing local Docker deployment remains an option for your own machine;
  that is self-hosting, not an always-on free cloud VM.

## What is not verified automatically

Local Compose/build/config tests cannot establish OCI account eligibility, ARM64
deployment success on a VM that has not been provided, DNS ownership, inbound
firewall rules, real ACME issuance, a remote backup restore, or a live public URL.
These require your account/VM/hostname. The setup creates no external resources
and makes no claim that the application is already published.
