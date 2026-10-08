import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import farm_automation
import run_reports
import stf_api


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patcher = patch.object(run_reports, "REPORT_DIR", Path(self.temp.name))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def report(self, statuses):
        return {"run_id": "a" * 32, "platform": "instagram", "target": "test", "jobs": [
            {"serial": str(index), "status": status, "token": "private", "result": result}
            for index, (status, result) in enumerate(statuses)
        ]}

    def test_zero_comments_are_not_reported_as_success(self):
        data = run_reports.summarize(self.report([("completed", {"comments_posted": 0})] * 10 + [("error", None)] * 6))
        self.assertEqual(data["status"], "needs_review")
        self.assertEqual(data["summary"]["no_comments_recorded"], 10)
        self.assertEqual(data["summary"]["error"], 6)
        self.assertEqual(data["summary"]["verified"], 0)
        self.assertNotIn("token", data["jobs"][0])

    def test_nonzero_worker_result_is_still_unverified(self):
        data = run_reports.summarize(self.report([("completed", {"comments_posted": 1})]))
        self.assertEqual(data["jobs"][0]["outcome"], "unverified")
        self.assertFalse(data["jobs"][0]["verified"])

    def test_missing_result_is_not_success(self):
        data = run_reports.summarize(self.report([("completed", None)]))
        self.assertEqual(data["summary"]["unverified"], 1)

    def test_all_failed_and_stopped_have_distinct_terminal_states(self):
        for state, expected in [("error", "error"), ("missing", "error"), ("stopped", "stopped"), ("starting", "running")]:
            self.assertEqual(run_reports.summarize(self.report([(state, None)]))["status"], expected)

    def test_reports_survive_session_loss_and_never_expose_tokens(self):
        report = self.report([("completed", {"comments_posted": 0})])
        run_reports.save_report(report)
        data = run_reports.read_report(report["run_id"])
        self.assertTrue(data["archived"])
        self.assertNotIn("token", data["jobs"][0])
        self.assertEqual(len(run_reports.list_reports()), 1)

    def test_path_traversal_and_corrupt_report_are_rejected(self):
        self.assertIsNone(run_reports.read_report("../secret"))
        (Path(self.temp.name) / ("b" * 32 + ".json")).write_text("not-json")
        self.assertEqual(run_reports.list_reports(), [])

    def client(self):
        app = FastAPI()
        app.include_router(farm_automation.router)
        app.dependency_overrides[stf_api._require_godam_session] = lambda: None
        return TestClient(app)

    def test_history_endpoint_reads_archives_without_starting_jobs(self):
        run_reports.save_report(self.report([("error", None)]))
        with patch.dict(farm_automation._RUNS, {}, clear=True), patch.object(farm_automation.MobileSession, "start_engagement") as start:
            response = self.client().get("/api/farm-automation/runs")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["runs"][0]["archived"])
        start.assert_not_called()

    def test_detail_reads_archive_after_restart(self):
        run_reports.save_report(self.report([("error", None)]))
        with patch.dict(farm_automation._RUNS, {}, clear=True):
            response = self.client().get("/api/farm-automation/runs/" + "a" * 32)
        self.assertEqual(response.json()["status"], "error")

    def test_whitespace_preview_is_invalid(self):
        response = self.client().post("/api/farm-automation/ml/preview", json={"caption": "   "})
        self.assertEqual(response.status_code, 422)

    def test_preview_declares_uncalibrated_model_and_no_fake_accounts(self):
        response = self.client().post("/api/farm-automation/ml/preview", json={"caption": "Contoh teks untuk simulasi"})
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["execute"])
        self.assertFalse(data["model_info"]["calibrated"])
        self.assertEqual(data["account_ranking"], [])
        self.assertEqual(data["device_assignments"], [])


if __name__ == "__main__":
    unittest.main()
