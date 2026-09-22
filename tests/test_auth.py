import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from auth import Authentication, AuthError


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.auth = Authentication(Path(self.directory.name) / "auth.json")
        self.original_auth = app.auth
        app.auth = self.auth
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        app.auth = self.original_auth
        self.directory.cleanup()

    def request(self, method, path, data=None, cookie="", origin=None, marker=False):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if marker:
            headers["X-Wakeboard-Request"] = "1"
        connection.request(method, path, json.dumps(data) if data is not None else None, headers)
        response = connection.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        connection.close()
        return result

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    def test_first_setup_requires_server_code_and_protects_all_panel_routes(self):
        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'id="login-form"', body)
        self.assertNotIn(b'id="scan-results"', body)
        status, _, body = self.request("GET", "/api/auth/status")
        self.assertEqual(json.loads(body), {"configured": False, "authenticated": False})

        for path in ("/app.js", "/style.css", "/favicon.svg", "/api/version", "/api/state", "/index.html", "/auth.py", "/data/devices.json", "/unknown"):
            with self.subTest(method="GET", path=path):
                self.assertEqual(self.request("GET", path)[0], 401)
        for method, path in (
            ("POST", "/api/scan"), ("POST", "/api/devices"),
            ("POST", "/api/wake"), ("POST", "/api/auth/logout"),
            ("POST", "/unknown"), ("PUT", "/api/devices/" + "a" * 32),
            ("DELETE", "/api/devices/" + "a" * 32),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path)[0], 401)

        password = "bezpieczne hasło testowe 123"
        data = {"code": self.auth.setup_code, "password": password}
        self.assertEqual(self.request("POST", "/api/auth/setup", data, origin=self.origin)[0], 403)
        self.assertEqual(self.request("POST", "/api/auth/setup", {**data, "code": "wrong"}, origin=self.origin, marker=True)[0], 403)
        self.assertEqual(self.request("POST", "/api/auth/setup", data, origin="http://evil.example", marker=True)[0], 403)
        status, headers, _ = self.request("POST", "/api/auth/setup", data, origin=self.origin, marker=True)
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        stored = self.auth.path.read_text(encoding="utf-8")
        self.assertNotIn(password, stored)
        self.assertIn('"algorithm": "scrypt-v1"', stored)
        if os.name != "nt":
            self.assertEqual(self.auth.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.request("POST", "/api/auth/setup", data, origin=self.origin, marker=True)[0], 409)
        self.assertEqual(self.request("GET", "/api/version")[0], 401)
        self.assertEqual(self.request("GET", "/api/version", cookie=cookie)[0], 200)
        self.assertIn(b'id="scan-results"', self.request("GET", "/", cookie=cookie)[2])
        self.assertEqual(self.request("GET", "/app.js", cookie=cookie)[0], 200)
        self.assertEqual(self.request("POST", "/api/devices", {}, cookie=cookie, origin=self.origin)[0], 403)
        self.assertEqual(self.request("POST", "/api/devices", {}, cookie=cookie, origin="http://evil.example", marker=True)[0], 403)
        with patch.object(app.devices, "add", return_value={"id": "a" * 32, "name": "PC", "ip": "", "mac": "A0:B1:C2:D3:E4:F5"}) as add:
            status, _, _ = self.request("POST", "/api/devices", {
                "name": "PC", "ip": "", "mac": "A0:B1:C2:D3:E4:F5",
            }, cookie=cookie, origin=self.origin, marker=True)
            self.assertEqual(status, 201)
            add.assert_called_once()
        self.assertEqual(self.request("GET", "/unknown", cookie=cookie)[0], 404)

        app.auth = Authentication(self.auth.path)
        self.assertEqual(self.request("GET", "/api/version", cookie=cookie)[0], 401)
        self.assertEqual(self.request("POST", "/api/auth/login", {"username": "admin", "password": "wrong"}, origin=self.origin, marker=True)[0], 401)
        status, headers, _ = self.request("POST", "/api/auth/login", {"username": "admin", "password": password}, origin=self.origin, marker=True)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("POST", "/api/auth/logout", cookie=cookie, origin=self.origin, marker=True)[0], 200)
        self.assertEqual(self.request("GET", "/api/version", cookie=cookie)[0], 401)

    def test_login_attempts_are_limited(self):
        self.auth.failures["192.0.2.1"] = [time.monotonic()] * 10
        with self.assertRaises(AuthError) as error:
            self.auth._check_limit("192.0.2.1")
        self.assertEqual(error.exception.status, 429)


if __name__ == "__main__":
    unittest.main()
