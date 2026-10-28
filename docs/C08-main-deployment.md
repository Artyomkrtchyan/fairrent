# Deploy main to FairRent AWS

The `Deploy main to AWS` job in `.github/workflows/backend-ci.yml` runs after
all four existing component CI jobs succeed. It deploys only `main`, including
manual runs selected on `main`, and only when repository variable
`AWS_DEPLOY_ENABLED` equals `true`. Pull requests never deploy.

Both images are built from the checked-out commit, published with a unique
SHA/run/attempt tag and deployed by digest. The workflow copies the ASG's
currently active numbered launch template version and changes only its user
data. The existing Ubuntu AMI must contain Docker, AWS CLI, both FairRent systemd
units, bootstrap scripts and nonsecret `/etc/fairrent/{backend,frontend}.json`.
The release boot script changes image references in those JSON files, preserving
database settings. No migrations or demo-data imports run during deployment.

## One-time activation (run by the infrastructure owner)

1. In WSL, apply the local Terraform configuration:

   ```bash
   cd /mnt/c/Users/iwbmf/Desktop/S5/infra/terraform
   export AWS_PROFILE=fairrent
   terraform apply
   terraform output github_deploy_role_arn
   ```

   This creates the GitHub OIDC identity provider and
   `fairrent-github-deploy` role. If the account already has the provider,
   import it instead of creating a duplicate:

   ```bash
   terraform import aws_iam_openid_connect_provider.github \
     arn:aws:iam::566663271715:oidc-provider/token.actions.githubusercontent.com
   ```

   The default trust subject is
   `repo:Artyomkrtchyan/fairrent:ref:refs/heads/main`. If the repository uses
   GitHub's immutable-ID subject format, set `github_main_oidc_subject` in local
   `terraform.tfvars` to the exact main-branch subject before applying. Do not
   broaden it to all repositories or branches. No GitHub environment is used.

2. Review and merge the workflow, `infra/scripts/deploy_asg.py`, Terraform files
   (including `.terraform.lock.hcl`), both Dockerfiles and frontend Nginx/context
   files into `main` through the repository's normal PR process. Include the
   Ansible source and deployment documentation needed to reproduce the AMI.
   Exclude local inventory `hosts`, `terraform.tfvars`, `.terraform/`, state,
   saved plans, credentials, `tmp/` and `.env` files. Do not use `git add .` for
   the current checkout: it contains unrelated local files.

3. In GitHub repository **Settings → Secrets and variables → Actions → Variables**,
   create a repository variable:

   ```text
   AWS_DEPLOY_ENABLED = true
   ```

   AWS access keys, SSH keys and database passwords are not GitHub secrets for
   this workflow. Authentication uses OIDC; EC2 retrieves application credentials
   with its own IAM role.

4. In **Actions → Component CI → Run workflow**, select `main` for the first
   release. Later pushes/merges into `main` trigger the same flow automatically.
   Wait for `Deploy main to AWS` to succeed. The job summary lists image digests,
   launch template version and instance refresh ID.

## Ownership and recovery

- Terraform manages infrastructure and the initial launch template configuration.
  GitHub Actions manages application user data and the ASG's selected launch
  template version. Terraform ignores these two release fields, so a normal
  apply does not undo an application deployment.
- Changing Terraform's `frontend_image` after this handover does not release a
  new frontend. Push application changes to `main` instead.
- Infrastructure changes to AMI, instance profile, network or instance type can
  create a new Terraform launch template version, but the ASG does not
  automatically select it. The owner must deliberately promote that numbered
  version in the ASG, then run deployment again. When replacing the AMI, update
  the IAM policy's allowed image ARN as well. Rebuilt AMIs must preserve the
  same bootstrap contract.
- Deployments are serialized without cancelling an active rollout. A commit
  superseded on `main` skips rollout after publishing. AWS refuses a new rollout
  if another refresh remains active.
- Instance refresh retains 100% healthy capacity, permits 200% during replacement,
  warms instances for 180 seconds and enables auto rollback. Rollback is based on
  AWS/ALB health; it does not prove every UI feature or database query works.
  Existing `/ready` health checks remain in use.
- If AWS rolls back, the workflow fails and prints its status. If the workflow
  times out or is cancelled, the AWS refresh can continue: inspect the ASG's
  refresh status before retrying. Do not terminate the healthy old instance by
  hand during replacement.
- For an application regression with healthy infrastructure, revert the offending
  application commit through a PR to `main`; the revert deploys normally. For
  urgent operational recovery, an infrastructure owner can select a known good
  numbered template version in AWS and refresh instances.
- Do not rerun the old Ansible playbook defaults against active ASG instances:
  they can overwrite the deployed image settings. Use Ansible for AMI building,
  or pass the intended release images explicitly for maintenance.
- Immutable release images accumulate in ECR. Preserve known good images for
  rollback; deleting one used by an active or rollback template prevents future
  instances from starting. No automatic ECR cleanup is enabled here.
- Set `AWS_DEPLOY_ENABLED=false` before tearing down AWS resources. A later main
  push otherwise attempts deployment to the destroyed environment.

References: [GitHub OIDC in AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws),
[AWS instance refresh rollback](https://docs.aws.amazon.com/autoscaling/ec2/userguide/instance-refresh-rollback.html).

These files were prepared locally without running checks or applying AWS changes,
at the infrastructure owner's request. The first cloud run remains necessary to
confirm the account's OIDC subject, IAM permissions and AMI boot behavior.
