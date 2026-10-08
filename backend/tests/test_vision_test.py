import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stf_api
import vision_test


class VisionTestApiTests(unittest.TestCase):
    def setUp(self):
        vision_test._ANALYSES.clear()
        app = FastAPI()
        app.include_router(vision_test.router)
        app.dependency_overrides[stf_api._require_godam_session] = lambda: None
        self.client = TestClient(app)

    def test_config_never_exposes_api_key(self):
        with patch.object(vision_test, "OPENAI_API_KEY", "super-secret"), patch.object(vision_test, "ALLOWED_PACKAGES", {"com.example.debug"}):
            response = self.client.get("/api/vision-test/config")
        self.assertTrue(response.json()["configured"])
        self.assertNotIn("api_key", response.json())
        self.assertNotIn("super-secret", response.text)

    def test_analyze_requires_valid_serial_and_package(self):
        response = self.client.post("/api/vision-test/analyze", json={
            "serial": "bad serial", "goal": "open settings", "expected_package": "not-package",
        })
        self.assertEqual(response.status_code, 422)

    def test_denied_social_package_cannot_be_analyzed(self):
        with patch.object(vision_test, "ALLOWED_PACKAGES", {"com.instagram.android"}), patch.object(vision_test, "_current_package", return_value="com.instagram.android"):
            response = self.client.post("/api/vision-test/analyze", json={
                "serial": "ABC", "goal": "open screen", "expected_package": "com.instagram.android",
            })
        self.assertEqual(response.status_code, 403)

    def test_analyze_fails_closed_on_package_mismatch(self):
        with patch.object(vision_test, "ALLOWED_PACKAGES", {"com.example.debug"}), patch.object(vision_test, "_current_package", return_value="com.other.app"):
            response = self.client.post("/api/vision-test/analyze", json={
                "serial": "ABC", "goal": "open screen", "expected_package": "com.example.debug",
            })
        self.assertEqual(response.status_code, 409)

    def test_local_policy_overrides_model_recommendation(self):
        model = {
            "screen_summary": "Test screen", "goal_reached": False, "recommended_index": 0, "warnings": [],
            "candidates": [
                {"label": "Publish", "description": "Post publicly", "x": 500, "y": 500, "confidence": 0.99, "risk": "safe_navigation", "reason": "Visible"},
                {"label": "Next", "description": "Open the next local page", "x": 800, "y": 900, "confidence": 0.92, "risk": "safe_navigation", "reason": "Navigation"},
            ],
        }
        with patch.object(vision_test, "ALLOWED_PACKAGES", {"com.example.debug"}), \
             patch.object(vision_test, "_current_package", return_value="com.example.debug"), \
             patch.object(vision_test, "_capture", return_value=(b"png", 1080, 1920)), \
             patch.object(vision_test, "_call_vision", return_value=model):
            response = self.client.post("/api/vision-test/analyze", json={
                "serial": "ABC", "goal": "open next page", "expected_package": "com.example.debug",
            })
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["candidates"][0]["decision"], "block")
        self.assertEqual(data["candidates"][1]["decision"], "allow")
        self.assertIsNone(data["recommended_index"])

    def test_execution_is_disabled_by_default(self):
        with patch.object(vision_test, "VISION_EXECUTION_ENABLED", False):
            response = self.client.post("/api/vision-test/analyses/none/click", json={
                "candidate_index": 0, "confirmation": "execute-approved-test-click",
            })
        self.assertEqual(response.status_code, 403)

    def test_allowed_fresh_candidate_maps_normalized_coordinates(self):
        analysis_id = "a" * 32
        vision_test._ANALYSES[analysis_id] = {
            "analysis_id": analysis_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "serial": "ABC", "package": "com.example.debug", "screen": {"width": 1080, "height": 1920},
            "candidates": [{"decision": "allow", "x": 500, "y": 250}],
        }
        adb_result = Mock(returncode=0)
        with patch.object(vision_test, "VISION_EXECUTION_ENABLED", True), \
             patch.object(vision_test, "ALLOWED_PACKAGES", {"com.example.debug"}), \
             patch.object(vision_test, "_current_package", return_value="com.example.debug"), \
             patch.object(vision_test, "_adb", return_value=adb_result) as adb:
            response = self.client.post(f"/api/vision-test/analyses/{analysis_id}/click", json={
                "candidate_index": 0, "confirmation": "execute-approved-test-click",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["coordinates"], {"x": 540, "y": 480})
        adb.assert_called_once_with("ABC", "shell", "input", "tap", "540", "480", timeout=8)

    def test_blocked_candidate_never_reaches_adb(self):
        analysis_id = "b" * 32
        vision_test._ANALYSES[analysis_id] = {
            "analysis_id": analysis_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "serial": "ABC", "package": "com.example.debug", "screen": {"width": 1080, "height": 1920},
            "candidates": [{"decision": "block", "x": 500, "y": 250}],
        }
        with patch.object(vision_test, "VISION_EXECUTION_ENABLED", True), patch.object(vision_test, "_adb") as adb:
            response = self.client.post(f"/api/vision-test/analyses/{analysis_id}/click", json={
                "candidate_index": 0, "confirmation": "execute-approved-test-click",
            })
        self.assertEqual(response.status_code, 403)
        adb.assert_not_called()


if __name__ == "__main__":
    unittest.main()
