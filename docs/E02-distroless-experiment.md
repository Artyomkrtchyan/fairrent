# E02 minimal backend runtime experiment

The previous Python 3.12 Debian 13 API image passed full component CI but reported 47 HIGH OS advisories.

This isolated experiment uses an unprivileged distroless Debian 13 API stage and copies only the tested Python runtime, application and required shared libraries. The secret, dependency, frontend image, and backend Trivy gates remain enabled; no ignore list or security threshold was reduced.

Initial distroless Security CI passed all 10 jobs. Component CI exposed missing shared libraries. Those were added individually (`libffi.so.8`, `libstdc++.so.6`, `libgcc_s.so.1`) with direct diagnostic evidence. On commit f1262d1, all ten E02 security checks and all Component CI jobs passed (including the API image inference import test). A subsequent HTTP /health startup smoke test has been added to the consolidation branch and requires fresh CI validation.

No live deployment or AWS/IAM changes. Do not merge this experiment or represent the runtime as verified until the final runs pass.
