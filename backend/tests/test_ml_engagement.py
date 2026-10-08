import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml_engagement import AccountProfile, EngagementPlanner


class EngagementPlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = EngagementPlanner()
        self.accounts = [
            AccountProfile(
                account_id="news-account",
                topics=["berita masyarakat teknologi"],
                success_rate=0.8,
                minutes_since_last_use=180,
            ),
            AccountProfile(
                account_id="cooldown-account",
                topics=["kuliner"],
                success_rate=0.4,
                minutes_since_last_use=5,
            ),
        ]

    def test_preview_is_dry_run_and_plans_account_switch(self):
        plan = self.planner.plan(
            platform="instagram",
            caption="Berita masyarakat tentang teknologi yang menarik dan bermanfaat",
            tone="positif",
            target_topics=["berita", "masyarakat", "teknologi"],
            recent_comments=[],
            accounts=self.accounts,
            device_serials=["DEVICE-1", "DEVICE-2"],
            current_accounts={"DEVICE-1": "old-account"},
        )
        self.assertEqual(plan["mode"], "dry-run")
        self.assertFalse(plan["execute"])
        self.assertTrue(plan["safety_gate"]["mass_engagement_disabled"])
        self.assertEqual(len(plan["device_assignments"]), 2)
        self.assertTrue(plan["device_assignments"][0]["switch_required"])
        self.assertTrue(all(not item["execute"] for item in plan["decisions"]))

    def test_risky_caption_blocks_all_actions(self):
        plan = self.planner.plan(
            platform="instagram",
            caption="Klik link gratis, transfer sekarang untuk jaminan untung crypto",
            tone="positif",
            target_topics=["promo"],
            recent_comments=[],
            accounts=self.accounts,
            device_serials=["DEVICE-1"],
        )
        self.assertFalse(plan["safety_gate"]["passed"])
        self.assertTrue(all(not item["recommended"] for item in plan["decisions"]))

    def test_operator_feedback_updates_online_model(self):
        plan = self.planner.plan(
            platform="instagram",
            caption="Informasi teknologi yang baik dan bermanfaat",
            tone="netral",
            target_topics=["teknologi"],
            recent_comments=[],
            accounts=self.accounts,
            device_serials=[],
        )
        result = self.planner.learn(plan["plan_id"], "comment", True)
        self.assertTrue(result["updated"])
        self.assertEqual(result["action"], "comment")


if __name__ == "__main__":
    unittest.main()
