#!/usr/bin/python3
"""Start the backend using the EC2 role; keep credentials in temporary /run files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

AWS = "/usr/local/bin/aws"
DOCKER = "/usr/bin/docker"
NAME = "fairrent-backend"


def command(arguments, environment, *, stdin=None, timeout=60):
    result = subprocess.run(arguments, input=stdin, text=True, capture_output=True,
                            env=environment, timeout=timeout, check=False)
    if result.returncode:
        # stdout can contain secrets. Never include it or subprocess input in errors.
        raise RuntimeError(f"{Path(arguments[0]).name} {arguments[1]} failed; check IAM, network and configuration")
    return result.stdout.strip()


def pgpass_value(value):
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n\x00"):
        raise ValueError("Invalid database credential or connection setting")
    return value.replace("\\", "\\\\").replace(":", "\\:")


def prepare(config, runtime):
    """Prepare before replacing the old container; return a foreground Docker command."""
    environment = os.environ.copy()
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_ROLE_ARN", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        environment.pop(key, None)
    environment.update(AWS_CONFIG_FILE="/dev/null", AWS_SHARED_CREDENTIALS_FILE="/dev/null",
                       AWS_EC2_METADATA_DISABLED="false", AWS_PAGER="", AWS_MAX_ATTEMPTS="3")
    region = config["aws_region"]
    registry = config["ecr_registry"]
    image = config["backend_image"]
    bind_address = config.get("backend_bind_address", "0.0.0.0")
    if bind_address not in {"0.0.0.0", "127.0.0.1"}:
        raise ValueError("Unsupported backend bind address")
    if not image.startswith(registry + "/fairrent-backend:") and not image.startswith(registry + "/fairrent-backend@sha256:"):
        raise ValueError("Backend image must reference the configured ECR repository")
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)

    secret_text = command([AWS, "secretsmanager", "get-secret-value", "--secret-id",
                           config["db_secret_name"], "--region", region,
                           "--query", "SecretString", "--output", "text", "--no-cli-pager"], environment)
    secret = json.loads(secret_text)
    values = [config["db_host"], str(config["db_port"]), config["db_name"],
              secret["username"], secret["password"]]
    pass_line = ":".join(pgpass_value(value) for value in values) + "\n"

    docker_config = runtime / "docker-auth"
    docker_config.mkdir(mode=0o700, exist_ok=True)
    environment["DOCKER_CONFIG"] = str(docker_config)
    try:
        token = command([AWS, "ecr", "get-login-password", "--region", region], environment)
        command([DOCKER, "login", "--username", "AWS", "--password-stdin", registry],
                environment, stdin=token + "\n")
        print("ECR authentication succeeded; downloading backend image", flush=True)
        command([DOCKER, "pull", image], environment, timeout=300)
    finally:
        # Registry tokens are needed only while pulling. /run is cleared at reboot.
        shutil.rmtree(docker_config)
        environment.pop("DOCKER_CONFIG", None)

    temporary = runtime / "pgpass.new"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(pass_line)
    temporary.chmod(0o600)
    passfile = runtime / "pgpass"
    temporary.replace(passfile)

    existing = command([DOCKER, "container", "ls", "--all", "--filter",
                        f"name=^/{NAME}$", "--format", "{{.ID}}"], environment)
    if existing:
        command([DOCKER, "rm", "--force", NAME], environment)

    arguments = [DOCKER, "run", "--rm", "--restart=no", "--name", NAME,
                 "--publish", f"{bind_address}:8000:8000", "--log-driver", "json-file",
                 "--log-opt", "max-size=10m", "--log-opt", "max-file=3",
                 "--mount", f"type=bind,src={passfile},dst=/run/secrets/pgpass,readonly",
                 "--env", f"PGHOST={config['db_host']}",
                 "--env", f"PGPORT={config['db_port']}",
                 "--env", f"PGDATABASE={config['db_name']}",
                 "--env", f"PGUSER={secret['username']}",
                 "--env", "PGSSLMODE=require", "--env", "PGPASSFILE=/run/secrets/pgpass", image]
    return arguments, environment


def main():
    os.umask(0o077)
    try:
        config = json.loads(Path("/etc/fairrent/backend.json").read_text(encoding="utf-8"))
        arguments, environment = prepare(config, Path("/run/fairrent-backend"))
        print("Starting backend container under systemd supervision", flush=True)
        os.execve(DOCKER, arguments, environment)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        # Exception payloads and malformed JSON may contain a password.
        print("Backend startup failed. Check IAM role, secret fields, ECR image and network access.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
