"""Local Docker integration: built frontend + Nginx + a controlled fake API.

Build fairrent-frontend:local first. Run from WSL; no AWS calls or real secrets.
"""
import json
import os
import re
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from uuid import uuid4

FAKE_API = r'''
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs

class Handler(BaseHTTPRequestHandler):
    ready = 200
    def log_message(self, *args):
        pass
    def handle_request(self):
        path = urlsplit(self.path).path
        status = 200
        if path == "/api/test/readiness":
            Handler.ready = int(parse_qs(urlsplit(self.path).query)["status"][0])
        elif path == "/ready":
            status = Handler.ready
        elif path == "/api/not-found":
            status = 404
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
        payload = json.dumps({"path": self.path, "method": self.command,
                              "body": body, "authorization": self.headers.get("Authorization"),
                              "proto": self.headers.get("X-Forwarded-Proto"),
                              "host": self.headers.get("Host")}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    do_GET = handle_request
    do_POST = handle_request

HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
'''


class FrontendNginxTests(unittest.TestCase):
    @classmethod
    def docker(cls, *arguments):
        return subprocess.run(["docker", *arguments], check=True, text=True,
                              capture_output=True).stdout.strip()

    @classmethod
    def setUpClass(cls):
        suffix = uuid4().hex[:12]
        cls.api = "fairrent-nginx-test-api-" + suffix
        cls.web = "fairrent-nginx-test-web-" + suffix
        try:
            cls.docker("run", "--detach", "--name", cls.api,
                       "--publish", "127.0.0.1::80", "python:3.10-slim",
                       "python", "-u", "-c", FAKE_API)
            address = cls.docker("port", cls.api, "80/tcp").splitlines()[0]
            cls.base = "http://" + address
            cls.docker("run", "--detach", "--name", cls.web,
                       "--network", "container:" + cls.api,
                       os.environ.get("FAIRRENT_FRONTEND_TEST_IMAGE", "fairrent-frontend:local"))
            for _ in range(60):
                try:
                    if cls.request("/ready")[0] == 200:
                        return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(1)
            raise RuntimeError("Local Nginx test image did not become ready")
        except Exception:
            for name in (cls.web, cls.api):
                log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
                print(log.stdout, log.stderr)
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for name in (cls.web, cls.api):
            subprocess.run(["docker", "rm", "--force", name], capture_output=True)

    @classmethod
    def request(cls, path, *, data=None, headers=None):
        request = urllib.request.Request(cls.base + path, data=data, headers=headers or {})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read().decode()

    def test_spa_route_loads_index_without_caching_it(self):
        status, headers, body = self.request("/analytics")
        self.assertEqual(status, 200)
        self.assertIn('<div id="root">', body)
        self.assertIn("no-store", headers["Cache-Control"])

    def test_hashed_assets_exist_and_missing_assets_are_not_html(self):
        _, _, index = self.request("/")
        asset = re.search(r'(?:src|href)="(/assets/[^"?]+\.js)"', index)
        self.assertIsNotNone(asset)
        status, headers, _ = self.request(asset.group(1))
        self.assertEqual(status, 200)
        self.assertIn("immutable", headers["Cache-Control"])
        self.assertEqual(self.request("/assets/not-a-real-file.js")[0], 404)

    def test_api_keeps_path_query_authorization_and_https(self):
        path = "/api/v1/listings?district_id=kentron&page=2"
        status, headers, body = self.request(path, headers={
            "Authorization": "Bearer synthetic-test-token", "X-Forwarded-Proto": "https",
        })
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(result["path"], path)
        self.assertEqual(result["authorization"], "Bearer synthetic-test-token")
        self.assertEqual(result["proto"], "https")

    def test_map_worker_is_served_as_javascript(self):
        # This Vite asset retains .mjs. Nginx's default MIME table only maps .js.
        workers = self.docker("exec", self.web, "find", "/usr/share/nginx/html/assets",
                              "-name", "maplibre-gl-worker-*.mjs").splitlines()
        self.assertTrue(workers, "Could not find MapLibre worker in the built frontend")
        status, headers, _ = self.request("/assets/" + workers[0].rsplit("/", 1)[1])
        self.assertEqual(status, 200)
        self.assertIn(headers.get_content_type(), {"text/javascript", "application/javascript"})

    def test_api_post_body_reaches_backend(self):
        payload = b'{"latitude":40.18,"longitude":44.51}'
        status, _, body = self.request("/api/v1/valuations", data=payload,
                                       headers={"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["method"], "POST")
        self.assertEqual(json.loads(body)["body"], payload.decode())

    def test_api_404_does_not_become_spa_success(self):
        status, headers, body = self.request("/api/not-found")
        self.assertEqual(status, 404)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["path"], "/api/not-found")

    def test_readiness_failure_reaches_load_balancer(self):
        self.request("/api/test/readiness?status=503")
        try:
            status, headers, body = self.request("/ready")
            self.assertEqual(status, 503)
            self.assertIn("application/json", headers["Content-Type"])
            self.assertEqual(json.loads(body)["path"], "/ready")
        finally:
            self.request("/api/test/readiness?status=200")


if __name__ == "__main__":
    unittest.main()
