#!/usr/bin/python3
"""Pull the frontend with the EC2 role and run Nginx on the host network."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

AWS = "/usr/local/bin/aws"
DOCKER = "/usr/bin/docker"
NAME = "fairrent-frontend"


def command(arguments, environment, *, stdin=None, timeout=60):
    result = subprocess.run(arguments, input=stdin, text=True, capture_output=True,
                            env=environment, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(arguments[0]).name} {arguments[1]} failed; check ECR permissions and network")
    return result.stdout.strip()


def prepare(config, runtime):
    environment = os.environ.copy()
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_ROLE_ARN", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        environment.pop(key, None)
    environment.update(AWS_CONFIG_FILE="/dev/null", AWS_SHARED_CREDENTIALS_FILE="/dev/null",
                       AWS_EC2_METADATA_DISABLED="false", AWS_PAGER="", AWS_MAX_ATTEMPTS="3")
    registry, region, image = config["ecr_registry"], config["aws_region"], config["frontend_image"]
    if not image.startswith(registry + "/fairrent-frontend:") and not image.startswith(registry + "/fairrent-frontend@sha256:"):
        raise ValueError("Frontend image must reference the configured ECR repository")

    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    docker_config = runtime / "docker-auth"
    docker_config.mkdir(mode=0o700, exist_ok=True)
    environment["DOCKER_CONFIG"] = str(docker_config)
    try:
        token = command([AWS, "ecr", "get-login-password", "--region", region], environment)
        command([DOCKER, "login", "--username", "AWS", "--password-stdin", registry],
                environment, stdin=token + "\n")
        print("ECR authentication succeeded; downloading frontend image", flush=True)
        command([DOCKER, "pull", image], environment, timeout=300)
    finally:
        shutil.rmtree(docker_config)
        environment.pop("DOCKER_CONFIG", None)

    existing = command([DOCKER, "container", "ls", "--all", "--filter",
                        f"name=^/{NAME}$", "--format", "{{.ID}}"], environment)
    if existing:
        command([DOCKER, "rm", "--force", NAME], environment)
    return [DOCKER, "run", "--rm", "--restart=no", "--name", NAME,
            "--network", "host", "--log-driver", "json-file",
            "--log-opt", "max-size=10m", "--log-opt", "max-file=3", image], environment


def main():
    os.umask(0o077)
    try:
        config = json.loads(Path("/etc/fairrent/frontend.json").read_text(encoding="utf-8"))
        arguments, environment = prepare(config, Path("/run/fairrent-frontend"))
        print("Starting frontend/Nginx under systemd supervision", flush=True)
        os.execve(DOCKER, arguments, environment)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        print("Frontend startup failed. Check EC2 role, ECR image, network and port 80 availability.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
