import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import app


class LocalCorsTests(unittest.TestCase):
    def test_local_frontend_is_allowed(self):
        response = TestClient(app).options("/api/device-farm/devices", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")

    def test_untrusted_site_cannot_read_local_api_in_browser(self):
        response = TestClient(app).options("/api/device-farm/devices", headers={
            "Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET",
        })
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)
