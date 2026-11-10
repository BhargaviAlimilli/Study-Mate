# StudyMate on Google Cloud trial credits

Plan checked 10 November 2026. This is a cloud deployment independent of the
developer's computer. It uses the existing Compose application, not a tunnel.
No GCP resources are provisioned by these repository files.

## Billing prerequisite

Activate an eligible Google Cloud Free Trial and confirm its remaining credit
and expiry under Billing. Keep the billing account on Free Trial; do not upgrade
to Paid. Google currently offers eligible new customers $300 for 90 days, ending
earlier if credits are exhausted. VM, disk, external IPv4, and network usage
consume credit. This stack is not covered by the ongoing e2-micro free allowance.
Do not assume credit lasts 90 days at the selected resource size. Claude API
usage is separate and remains billable through the existing Claude account.

Official references:
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://cloud.google.com/signup-faqs
- https://docs.cloud.google.com/compute/docs/create-linux-vm-instance

## Create the server

1. Select/create the project `study-mate-demo` in Google Cloud Console. Record
   its actual project ID (Google may append a unique suffix).
2. Open Compute Engine > VM instances. Enable the Compute Engine API if prompted.
3. Choose Create instance and name it `study-mate`.
4. Choose an available region/zone; Mumbai is `asia-south1`. Inspect the cost
   estimate rather than assuming a region has the same price as another.
5. Select general-purpose E2, `e2-standard-4` (4 vCPU, 16 GB RAM), standard
   provisioning, no GPU. This provides room for the existing Compose limits,
   concurrent API/worker model processes, and the operating system. It consumes
   trial credits; it is not an Always Free machine. Do not select Spot for a
   deadline-sensitive demonstration. Capacity/quota still must be available.
6. Under OS/storage choose ordinary Ubuntu 24.04 LTS x86-64 (not Ubuntu Pro),
   with a 50 GB standard persistent boot disk. No extra disks or paid OS licenses.
7. Assign an external IPv4 address. Add the network tag `study-mate-web`.
8. Use a dedicated VPC/subnet or inspect the existing network's firewall rules.
   Permit TCP 80/443 from `0.0.0.0/0` targeting `study-mate-web`. Permit SSH TCP 22
   only from your current public IPv4 `/32`. Remove/avoid broader rules that
   would also allow SSH to this VM. Leave database/API ports private. Do not
   alter rules for unrelated workloads. If using IAP/browser SSH, configure the
   documented IAP access separately; direct SSH restrictions do not enable it.
9. Use the existing public key under VM SSH keys if OS Login is disabled. Choose
   the intended Linux username explicitly (for example `studyadmin`). GCP does
   not assume the Oracle `ubuntu` SSH username. For OS Login-enabled projects,
   use the project's OS Login flow instead of metadata keys. Never upload the
   private key. A matching public key has already been verified locally.
10. Review the estimate, trial balance and expiry, then create. Wait for Running
    and record external IP, SSH username and actual machine type. If trial is
    unavailable, a paid upgrade is required, or quota blocks creation, stop and
    resolve eligibility/quota before proceeding.

## Deploy the existing application

Point your free Duck DNS hostname at the VM external IP. An ephemeral IP may
change after a stop/start; update DNS when it changes. A static IP also consumes
credit and must be released when no longer needed.

From Windows PowerShell, substituting the IP and selected Linux username:

```powershell
ssh -i "C:\Users\chand\Downloads\ssh-key-2026-11-10.key" studyadmin@VM_EXTERNAL_IP
```

Verify the host fingerprint before accepting a first SSH connection. On the VM:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git python3
sudo systemctl enable --now docker
git clone https://github.com/BhargaviAlimilli/Study-Mate.git
cd Study-Mate
```

The deployment changes must first be pushed or copied securely to the VM;
adding this guide does not push them. Private repositories require authentication.

```bash
python3 deploy/free/prepare_env.py --domain YOUR-NAME.duckdns.org
python3 deploy/free/prepare_env.py --check
sudo bash deploy/free/deploy.sh
sudo docker compose --env-file deploy/free/.env -f deploy/free/compose.yml exec api python -m app.create_user --email YOUR-EMAIL --name "YOUR NAME"
python3 deploy/free/check_public.py https://YOUR-NAME.duckdns.org
```

The environment helper privately prompts for the Claude key and generates
database/JWT secrets. Alternatively prepare it locally using the existing ignored
backend key as described in README.md, then copy only the private deployment
environment over SSH and restrict it to owner read/write. Do not print secrets or
commit the environment. Passwords for new learner accounts are also prompted.

The `deploy/free` directory and Compose project name `study-mate-free` are shared
with the Oracle recipe; they do not assert that GCP compute is permanently free.
Existing local images were validated on x86-64. This deployment starts with an
empty database; no development data is transferred automatically.

Open the HTTPS site, sign in, upload a small public PDF and check queued -> ready,
chat, evidence links, quiz submission/feedback, saved conversations, and voice.
Use RELEASE_CHECKLIST.md for the complete workflow. Keep public registration
disabled for an invited-user demo. Refer to README.md for logs and backups.

## Credit monitoring and cleanup

Review Billing > Reports and Credits frequently, and set budget alerts (alerts
are not hard spending caps). A positive resource estimate is expected on GCP;
credit offsets eligible charges while the trial is active. Do not upgrade merely
to keep the deployment running. Export backups off the VM before trial expiry.

Stopping the VM does not remove disk/IP charges. When finished, back up data,
then remove the VM and unwanted disks, snapshots, reserved IPs and other created
resources. Verify billing/resources afterward. Retain credentials and data only
as needed. Deletion must be deliberate because it can permanently remove files.
