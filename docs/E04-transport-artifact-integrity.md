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
