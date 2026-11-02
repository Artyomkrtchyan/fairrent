"""Offline bootstrap checks: fake AWS/Docker only; never contact a real account."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "files/fairrent-backend-start.py"
spec = importlib.util.spec_from_file_location("backend_start", SCRIPT)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "aws_region": "eu-central-1", "ecr_registry": "example.ecr.invalid",
            "backend_image": "example.ecr.invalid/fairrent-backend:demo-v1",
            "db_secret_name": "test-secret", "db_host": "database.invalid",
            "db_port": 5432, "db_name": "fairrent",
        }

    def test_secret_is_file_only_and_auth_is_removed(self):
        calls = []
        password = r"test:password\with-slash"
        def fake_command(arguments, environment, **kwargs):
            calls.append((arguments, environment.copy(), kwargs))
            if arguments[1] == "secretsmanager":
                return json.dumps({"username": "fairrent_app", "password": password})
            if arguments[1] == "ecr":
                return "test-ecr-token"
            if arguments[1] == "container":
                return "old-container-id"
            return ""
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            with patch.object(bootstrap, "command", side_effect=fake_command):
                arguments, environment = bootstrap.prepare(self.config, runtime)
            self.assertNotIn(password, " ".join(arguments))
            self.assertNotIn("PGPASSWORD", " ".join(arguments))
            self.assertIn("PGPASSFILE=/run/secrets/pgpass", arguments)
            self.assertIn("--restart=no", arguments)
            self.assertIn("0.0.0.0:8000:8000", arguments)
            self.assertNotIn("--detach", arguments)
            self.assertNotIn("DOCKER_CONFIG", environment)
            self.assertFalse((runtime / "docker-auth").exists())
            expected = "database.invalid:5432:fairrent:fairrent_app:test\\:password\\\\with-slash\n"
            self.assertEqual((runtime / "pgpass").read_text(), expected)
            login = next(call for call in calls if call[0][1] == "login")
            self.assertEqual(login[2]["stdin"], "test-ecr-token\n")
            self.assertNotIn("test-ecr-token", " ".join(login[0]))
            operations = [call[0][1] for call in calls]
            self.assertLess(operations.index("pull"), operations.index("rm"))

    def test_pull_failure_keeps_old_container_and_removes_token(self):
        calls = []
        def fake_command(arguments, environment, **kwargs):
            calls.append(arguments)
            if arguments[1] == "secretsmanager":
                return json.dumps({"username": "app", "password": "secret"})
            if arguments[1] == "pull":
                raise RuntimeError("pull failed")
            return "token"
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            with patch.object(bootstrap, "command", side_effect=fake_command):
                with self.assertRaises(RuntimeError):
                    bootstrap.prepare(self.config, runtime)
            self.assertFalse(any(call[1] == "rm" for call in calls))
            self.assertFalse((runtime / "docker-auth").exists())
            self.assertFalse((runtime / "pgpass").exists())

    def test_unsafe_password_cannot_inject_a_second_pgpass_entry(self):
        for password in ["secret\n*:*:*:*:injected", "secret\rvalue", "secret\x00value", ""]:
            with self.subTest(password=repr(password)):
                with self.assertRaises(ValueError):
                    bootstrap.pgpass_value(password)

    def test_loopback_binding_is_explicit_and_optional(self):
        def fake_command(arguments, environment, **kwargs):
            if arguments[1] == "secretsmanager":
                return json.dumps({"username": "app", "password": "synthetic"})
            return ""
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bootstrap, "command", side_effect=fake_command):
                arguments, _ = bootstrap.prepare({**self.config, "backend_bind_address": "127.0.0.1"}, Path(directory))
            self.assertIn("127.0.0.1:8000:8000", arguments)
            self.assertNotIn("0.0.0.0:8000:8000", arguments)

    def test_command_failure_does_not_disclose_captured_credentials(self):
        result = subprocess.CompletedProcess(["aws"], 1, stdout="secret-password", stderr="secret-token")
        with patch.object(bootstrap.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as error:
                bootstrap.command(["aws", "secretsmanager"], {})
        self.assertNotIn("secret-password", str(error.exception))
        self.assertNotIn("secret-token", str(error.exception))


if __name__ == "__main__":
    unittest.main()
