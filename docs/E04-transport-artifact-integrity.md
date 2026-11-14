
## Server intentionally offline — November 14, 2026

The team confirmed that the server was deliberately turned off and the public link is not currently active. The earlier DNS failure was therefore not sufficient evidence of an application or TLS configuration defect.

Offline CI now independently verifies the committed Terraform ALB HTTPS certificate/redirect configuration and checks synthetic certificate hostname rejection and SHA-256 artifact tampering. The workflow separately records that live deployment verification is not executed. **This is offline-configuration acceptance only**, not proof that live TLS or DNS is currently functioning.

- [Offline E04 verification run](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43630648329): four jobs passed; live HTTPS job skipped as intended.
- To exercise live TLS, restart the approved server, restore or confirm public DNS, ensure the ACM certificate is correct, then set GitHub Actions repository variable `FAIRRENT_E04_LIVE_ENABLED=true` or manually dispatch E04 with `verify_live=true`. The live job is then required to pass, and cannot be silently ignored.
- If the deployed hostname differs from `fairrent.online`, set `FAIRRENT_PUBLIC_HOSTNAME` to the correct approved host (hostname only). Do not guess the load balancer URL.
- The live acceptance evidence and owner sign-off remain pending while the deployment is offline.
# E04 — Transport and artifact integrity verification

Owner: Mane (verification). Infrastructure/IAM owner: Artyom. Model/data artifact owner: ML/data team. Related: #50.

## Scope and controls
- The E04 CI workflow checks the publicly documented `fairrent.online` endpoint without credentials. It validates the certificate chain and hostname, tests HTTP-to-HTTPS redirects, and checks initial HTML for obvious insecure resource links.
- It also demonstrates SHA-256 rejection of a **synthetic** modified artifact. This negative control establishes the check's behavior, **not** the provenance or authenticity of production models.
- Existing ML tests include tampered package/dataset checks in `ml/tests/test_inference.py` and `ml/tests/test_calibrate_intervals.py`. Actual published artifact validation, manifest trust and runtime loader enforcement require owner confirmation.
- No AWS resources, database privileges, IAM policies, production artifacts, or deployment settings are changed in this PR.

## Results
| Verification | Evidence | Status |
| --- | --- | --- |
| Valid public TLS certificate, chain and hostname | [E04 CI run](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43492720400): DNS failure before TLS (No address associated with hostname) | BLOCKED: confirm correct hostname/DNS with Artyom |
| HTTP redirect to HTTPS | E04 transport job | Not reached: DNS prerequisite failed |
| Initial HTML static mixed-content indication | E04 transport job | Not reached; cannot rule out dynamic/browser mixed content |
| Synthetic SHA-256 tampering rejected | [E04 CI run](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43492720400): passed | Verified synthetic-only negative control |
| Production B07 model/dataset manifest integrity | Trusted manifest, published image digest, serving loader logs | Owner verification pending |
| Database least-privilege and private boundaries | Artyom-controlled security-group and SQL role evidence | Owner verification pending |
| Sensitive application logs and exports | Sanitized example and agreed redaction/retention rules | Owner verification pending |

## Follow-up acceptance
1. Record exact workflow URL, commit SHA, UTC date and conclusion after E04 CI executes. Investigate failures rather than weakening the checks.
2. Verify mixed-content warnings with browser DevTools on owned staging; inspect TLS termination/redirect rules with Artyom.
3. With the model owner, use an **approved synthetic artifact** and trusted manifest to show actual model-loading code rejects a modified file, without copying production files or credentials.
4. Ask backend/deployment owner to verify production DB grants, RDS ingress boundaries and whether API/CloudWatch logs include sensitive request bodies, authorization headers, unredacted location/contact data or secrets. Record sanitized evidence and retention.
5. Document owner sign-off, remediation, and re-test results before closing E04. No claim of complete transport/asset security is made by a synthetic negative control alone.

## Transport blocker — November 13, 2026

From a GitHub-hosted runner, `openssl s_client` failed to resolve `fairrent.online` (OpenSSL `BIO_lookup_ex`: *No address associated with hostname*). This is a **DNS/reachability or hostname issue**, not evidence of an invalid certificate: no TLS handshake occurred. Infrastructure owner must confirm the correct hostname or restore DNS, then rerun certificate, redirect and mixed-content checks. No DNS/AWS changes were made in this branch.

## DNS recovery and CI hostname configuration — November 14, 2026

The E04 HTTPS test requires a publicly resolvable public hostname. GitHub Actions reported a DNS lookup failure for fairrent.online before it could attempt TLS.

1. Infrastructure owner: confirm the current public hostname and DNS provider/registrar. If fairrent.online remains the target, inspect nameservers, A/AAAA/ALIAS records, DNSSEC and domain registration. Obtain the real ALB target via the authorized Terraform command: `terraform output -raw alb_dns_name`. Never guess the ALB address.
2. If the deployment moved to a different public hostname, set the GitHub Actions repository variable `FAIRRENT_PUBLIC_HOSTNAME` to that exact hostname, without https:// or a path. Ensure the ACM certificate covers it. E04 defaults to fairrent.online if the variable is not set.
3. Rerun the E04 workflow. The DNS prerequisite, TLS chain and hostname check, HTTP redirect and initial HTML checks must all pass. Check browser DevTools separately for dynamic mixed content.
4. Record verified public hostname, UTC time, workflow URL, deployment digest and infrastructure owner sign-off.

No domain, DNS, IAM, AWS or Terraform deployment settings were changed here. Failed public DNS must not be silently interpreted as an HTTPS security success.
