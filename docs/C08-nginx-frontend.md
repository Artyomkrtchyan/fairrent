# C08 frontend image with Nginx

The frontend runs on the same EC2 instances as the API, behind the existing ALB.
This replaces the planned S3/CloudFront frontend deployment for C08. No cloud
resource is provisioned and no server is modified by these local build files.

```text
Browser --HTTPS--> ALB --HTTP:80--> Nginx
                                    |-- /              -> compiled React/Vite
                                    |-- /api/v1/...     -> 127.0.0.1:8000
                                    |-- /health,/ready -> 127.0.0.1:8000
```

## Build locally (from repository root)

Use the current reviewed frontend source from main, not an older infrastructure
branch snapshot. Keep local infrastructure work before bringing main into the
branch. Updating Git, publishing images and applying infrastructure are manual
user actions at this stage.

```bash
docker build --platform linux/amd64 \
  -f frontend/Dockerfile -t fairrent-frontend:local .

docker build --platform linux/amd64 --target verification \
  -f frontend/Dockerfile .
```

The repository root is required because source files import shared contracts.
`frontend/Dockerfile.dockerignore` excludes local .env files, node_modules, build
output and unrelated repository content. Builder dependencies are installed from
package-lock.json. TypeScript and production build must pass. The runtime image
contains Nginx and static output only; Node and build tools are not copied.
Base tags can be overridden using NODE_IMAGE/NGINX_IMAGE build arguments; pin
their digests in a release pipeline when locking a reproducible toolchain.

VITE_API_MODE is real, and VITE_API_BASE_URL is empty. API calls therefore use the
same origin as the page. API failures are not converted into index.html or zero
values. The normal empty API dataset remains empty; these files do not add data.
The image packages the existing UI, including its existing demo labels/fixtures;
selecting real API mode does not replace every static UI element with live data.

## Offline integration check (Docker, no AWS or RDS)

After building, from repository root in WSL:

```bash
FAIRRENT_FRONTEND_TEST_IMAGE=fairrent-frontend:local \
  python3 -m unittest discover -s infra/tests -p test_frontend_nginx.py -v
```

The test uses a local fake API and the actual frontend/Nginx image. Its temporary
containers are removed afterwards. It checks SPA fallback, hashed assets, API
paths/query/body/auth forwarding, HTTPS forwarding metadata, genuine API errors
and a database-readiness failure. No real secret is used.

## Deployment prerequisites (not applied yet)

1. Create a private ECR repository fairrent-frontend with immutable tags.
2. Extend the EC2 role's scoped ECR pull policy to this repository. Preserve the
   separate GetAuthorizationToken permission on resource *.
3. Publish the image under a unique immutable tag or SHA digest.
4. Run `infra/ansible/frontend.yml` on the intended host. It installs a frontend
   systemd bootstrap which pulls that version with the EC2 role, runs Nginx with
   --network host and lets systemd supervise its lifecycle. For a clean AMI builder
   use `-e '{"target_hosts":"ami_builder","frontend_start":false}'` after
   installing backend.yml with backend_start=false. No ECR pull occurs in this mode.
   Do not run two process managers for one container.
5. Keep backend publication on 0.0.0.0:8000 for the initial dual-service AMI;
   after traffic cutover, change backend_bind_address to 127.0.0.1 in a later
   rollout. The frontend shares host networking so it reaches the backend's
   127.0.0.1:8000 endpoint in either case.
6. Change the target group/ALB egress/backend SG inbound from 8000 to Nginx port
   80. Keep the health path /ready, and allow port 80 only from ALB SG.
7. Produce and test a clean new AMI, update the Launch Template and roll out the
   ASG. Do not simply change ports on live instances still serving the old image.

The port/AMI switch needs a staged Terraform plan so requests are not routed to
port 80 on an instance that only serves 8000. Keep the existing backend-only
deployment serving traffic until a Nginx-enabled target passes /ready. Do not
blindly apply all of the prerequisite changes at once.

Keep backend_bind_address at its default 0.0.0.0 for the first dual-service AMI,
so new instances still pass the existing ALB:8000 health checks during rollout.
After all ASG instances have Nginx, attach a second port-80 target group and wait
for healthy targets before switching listeners. Detach the old target group only
after the domain checks pass. Then remove ALB:8000 SG rules and switch the backend
to loopback in a subsequent AMI/config rollout. This deliberately separates the
application rollout from the traffic cutover.

frontend.yml starts and checks the application only when frontend_start=true.
On a running host, use journalctl -u fairrent-frontend for startup diagnostics;
AWS login output and credentials are never written to the application journal.

ALB terminates HTTPS using the issued fairrent.online certificate. Nginx preserves
the ALB's forwarded protocol. The same-origin /api client needs no new CORS rule.
GitHub Actions/OIDC and rolling ASG deployment remain a subsequent C08 step.

## MapLibre worker MIME type

Vite emits a maplibre-gl-worker-*.mjs asset. Nginx's standard MIME table does not
map this extension in the deployed base image, resulting in application/octet-stream
and browser worker failures. The server includes the standard MIME table and adds
application/javascript for mjs. Keep the standard table so CSS/JS MIME types are
preserved. The Docker integration suite verifies the worker's actual HTTP headers.
After updating an existing deployment, hard-reload or disable browser cache once:
the old worker URL was served with immutable caching and an incorrect MIME type.
