"""Offline frontend bootstrap checks: no real Docker daemon or AWS requests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "files/fairrent-frontend-start.py"
spec = importlib.util.spec_from_file_location("frontend_start", SCRIPT)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class FrontendBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "aws_region": "eu-central-1", "ecr_registry": "example.ecr.invalid",
            "frontend_image": "example.ecr.invalid/fairrent-frontend:demo-v1",
        }

    def test_host_network_and_single_supervisor_without_database_secret(self):
        calls = []
        def fake_command(arguments, environment, **kwargs):
            calls.append((arguments, environment.copy(), kwargs))
            if arguments[1] == "ecr":
                return "synthetic-ecr-token"
            if arguments[1] == "container":
                return "previous-frontend"
            return ""
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            with patch.object(bootstrap, "command", side_effect=fake_command):
                arguments, environment = bootstrap.prepare(self.config, runtime)
            self.assertIn("--network", arguments)
            self.assertEqual(arguments[arguments.index("--network") + 1], "host")
            self.assertIn("--restart=no", arguments)
            self.assertNotIn("--detach", arguments)
            self.assertNotIn("--publish", arguments)
            self.assertNotIn("synthetic-ecr-token", " ".join(arguments))
            self.assertNotIn("DOCKER_CONFIG", environment)
            self.assertFalse((runtime / "docker-auth").exists())
            operations = [call[0][1] for call in calls]
            self.assertNotIn("secretsmanager", operations)
            self.assertLess(operations.index("pull"), operations.index("rm"))
            login = next(call for call in calls if call[0][1] == "login")
            self.assertEqual(login[2]["stdin"], "synthetic-ecr-token\n")

    def test_pull_failure_does_not_replace_existing_container(self):
        calls = []
        def fake_command(arguments, environment, **kwargs):
            calls.append(arguments)
            if arguments[1] == "pull":
                raise RuntimeError("pull failed")
            return "synthetic-token"
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            with patch.object(bootstrap, "command", side_effect=fake_command):
                with self.assertRaises(RuntimeError):
                    bootstrap.prepare(self.config, runtime)
            self.assertFalse(any(call[1] == "rm" for call in calls))
            self.assertFalse((runtime / "docker-auth").exists())

    def test_foreign_image_is_rejected_before_aws_access(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bootstrap, "command") as command:
                with self.assertRaises(ValueError):
                    bootstrap.prepare({**self.config, "frontend_image": "untrusted/image:latest"}, Path(directory))
                command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
