# FairRent EC2 provisioning

Run Ansible from WSL. `ansible.cfg` selects `hosts` and the local SSH key.
On a Windows-mounted directory explicitly select the trusted configuration:

```bash
export ANSIBLE_CONFIG="$PWD/ansible.cfg"
ansible-playbook backend.yml --syntax-check
ansible-playbook backend.yml
```

Install Docker with `docker-playbook.yml` and AWS CLI with `aws-cli.yml` first.
The EC2 instance profile needs ECR pull permissions and GetSecretValue for
`fairrent/dev/backend-db`. The secret must contain `username` and `password`
matching the existing PostgreSQL application role. No local AWS profile is used
on the server. The instance needs outgoing access to AWS APIs and ECR.

## Autonomous boot

`backend.yml` imports `backend-service.yml` and installs systemd supervision
instead of directly managing the container with community.docker. Do not enable
a second Docker restart policy. The first application replaces the existing
container and briefly interrupts backend requests. Later unchanged Ansible runs
leave the service running.

At boot, systemd runs `/usr/local/sbin/fairrent-backend-start.py`, which:

1. Reads nonsecret settings from `/etc/fairrent/backend.json`.
2. Uses the EC2 instance role to retrieve application credentials.
3. Authenticates to ECR using a temporary Docker config inside `/run`.
4. Pulls the selected immutable image tag, then deletes the registry token.
5. Writes a root-only PostgreSQL password file under `/run/fairrent-backend`.
6. Replaces the backend container and runs it in the foreground under systemd.

The image currently runs as root, allowing libpq to read the 0600 password file.
The file is mounted read-only and selected via PGPASSFILE; PGPASSWORD is not
stored in Docker container metadata. Credentials are not baked into templates.
`/run` is temporary storage and is removed at reboot; systemd also cleans the
runtime directory on service stop. Root/Docker administrators can still read
runtime secrets. Passwords containing newlines or NUL are rejected.

systemd retries startup after 20 seconds if credentials, ECR or networking are
temporarily unavailable. It restarts exited containers, but does not restart a
live container merely because /ready fails. ALB checks /ready independently.
No database migrations run on boot. Secret changes take effect on service restart.
PGSSLMODE=require preserves the existing encrypted connection configuration;
certificate/hostname verification with the RDS CA bundle remains a follow-up.

## Verification (run manually on EC2)

```bash
sudo systemctl status fairrent-backend --no-pager
sudo journalctl -u fairrent-backend -n 50 --no-pager
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/ready
```

After a successful deployment, reboot EC2 manually. Reconnect and repeat these
checks and the existing ALB requests without rerunning Ansible. The public IP
may change after an EC2 stop/start; a reboot normally preserves it.

## AMI preparation is a separate step

Frontend/Nginx service provisioning is in `frontend.yml`. Run backend.yml first.
For a clean dual-service builder, run both with backend_start=false and
frontend_start=false respectively, selecting the ami_builder group. Both services
are enabled for future boot but remain stopped during provisioning. Port changes
and traffic cutover are documented in ../../docs/C08-nginx-frontend.md.

Do not create an AMI from the current running development instance yet. It has
previously contained Docker metadata with PGPASSWORD and registry credentials.
For a clean image, provision a fresh Ubuntu builder with Docker, AWS CLI and
this playbook using `-e '{"backend_start": false}'`. This enables the service
without starting the application or retrieving secrets. Plan the stopped-builder
image capture separately; do not reboot it into a secret-enabled service before
capture. ASG launch templates must attach the correct instance profile and
Backend SG and provide public IPv4/outgoing routing in the current network.
