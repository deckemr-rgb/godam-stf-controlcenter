from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
import subprocess
from types import SimpleNamespace
from fastapi import HTTPException

from fastapi import FastAPI
from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stf_api  # noqa: E402


class StfApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = (
            stf_api.STF_URL,
            stf_api.STF_PUBLIC_URL,
            stf_api.STF_TOKEN,
            stf_api.STF_REQUIRE_GODAM_AUTH,
        )
        stf_api.STF_URL = "http://stf-proxy:7100"
        stf_api.STF_PUBLIC_URL = "http://localhost:7100"
        stf_api.STF_TOKEN = "test-token"
        stf_api.STF_REQUIRE_GODAM_AUTH = False
        app = FastAPI()
        app.include_router(stf_api.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        (
            stf_api.STF_URL,
            stf_api.STF_PUBLIC_URL,
            stf_api.STF_TOKEN,
            stf_api.STF_REQUIRE_GODAM_AUTH,
        ) = self.original

    def test_config_does_not_expose_token(self) -> None:
        response = self.client.get("/api/device-farm/config")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertNotIn("token", response.json())

    def test_devices_are_forwarded_through_fixed_endpoint(self) -> None:
        with patch.object(stf_api, "_request", return_value={"devices": [{"serial": "ABC"}]}) as request:
            response = self.client.get("/api/device-farm/devices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["devices"][0]["serial"], "ABC")
        request.assert_called_once_with(
            "GET",
            "/api/v1/devices",
            params={"fields": stf_api.DEVICE_FIELDS},
        )

    def test_reservation_converts_seconds_to_milliseconds(self) -> None:
        with patch.object(stf_api, "_request", return_value={"success": True}) as request:
            response = self.client.post(
                "/api/device-farm/devices/ABC123/reserve",
                json={"timeout_seconds": 120},
            )
        self.assertEqual(response.status_code, 200)
        request.assert_called_once_with(
            "POST",
            "/api/v1/user/devices",
            json={"serial": "ABC123", "timeout": 120000},
        )

    def test_invalid_serial_is_rejected(self) -> None:
        response = self.client.delete("/api/device-farm/devices/bad%20serial/reserve")
        self.assertEqual(response.status_code, 422)

    def test_authentication_is_required_when_enabled(self) -> None:
        stf_api.STF_REQUIRE_GODAM_AUTH = True
        response = self.client.get("/api/device-farm/devices")
        self.assertEqual(response.status_code, 401)

    def test_screenshot_overload_returns_retry_without_adb(self):
        slots = Mock()
        slots.acquire.return_value = False
        with patch.object(stf_api, "_SCREENSHOT_SLOTS", slots), patch.object(stf_api.subprocess, "run") as adb:
            response = self.client.get("/api/device-farm/devices/ABC/screenshot")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "3")
        slots.acquire.assert_called_once_with(timeout=0.5)
        slots.release.assert_not_called()
        adb.assert_not_called()

    def test_screenshot_timeout_releases_slot(self):
        slots = Mock()
        slots.acquire.return_value = True
        with patch.object(stf_api, "_SCREENSHOT_SLOTS", slots), patch.object(stf_api.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 12)):
            response = self.client.get("/api/device-farm/devices/ABC/screenshot")
        self.assertEqual(response.status_code, 503)
        slots.release.assert_called_once()

    def test_diagnostics_reports_busy_and_unauthorized_without_control(self):
        inventory = {"devices": [{"serial": "ABC", "present": True, "ready": True, "using": True}]}
        adb_result = SimpleNamespace(returncode=0, stdout="List of devices attached\nABC\tdevice\nXYZ\tunauthorized\n")
        with patch.object(stf_api, "_request", return_value=inventory) as upstream, patch.object(stf_api.subprocess, "run", return_value=adb_result) as adb:
            response = self.client.get("/api/device-farm/diagnostics")
        data = response.json()
        self.assertTrue(data["read_only"])
        self.assertTrue(data["devices"][0]["busy"])
        self.assertEqual(data["devices"][1]["adb"], "unauthorized")
        self.assertEqual(upstream.call_args.args[0], "GET")
        self.assertEqual(adb.call_args.args[0][-1], "devices")

    def test_diagnostics_does_not_claim_healthy_when_services_fail(self):
        with patch.object(stf_api, "_request", side_effect=HTTPException(503, "STF unreachable")), patch.object(stf_api.subprocess, "run", side_effect=FileNotFoundError):
            data = self.client.get("/api/device-farm/diagnostics").json()
        self.assertFalse(data["adb_ok"])
        self.assertFalse(data["stf_ok"])
        self.assertEqual(len(data["issues"]), 2)


if __name__ == "__main__":
    unittest.main()
