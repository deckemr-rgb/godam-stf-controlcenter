import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mobile_session import PLATFORMS, normalize_actions, platform_action_options, supported_actions


class MobilePlatformTests(unittest.TestCase):
    def test_all_requested_social_platforms_are_registered(self):
        self.assertEqual(
            set(PLATFORMS),
            {"instagram", "tiktok", "x", "facebook", "threads"},
        )

    def test_every_platform_has_android_package_and_target_url(self):
        for platform, spec in PLATFORMS.items():
            with self.subTest(platform=platform):
                self.assertTrue(spec.packages)
                self.assertIn("{target}", spec.profile_url)
                self.assertTrue(spec.like_patterns)
                self.assertTrue(spec.comment_patterns)
                self.assertTrue(spec.submit_patterns)

    def test_every_platform_supports_share_with_safe_confirmation(self):
        for platform, spec in PLATFORMS.items():
            with self.subTest(platform=platform):
                self.assertTrue(spec.share_patterns, platform)
                self.assertTrue(spec.share_confirm_patterns, platform)

    def test_repost_only_supported_on_x_tiktok_facebook(self):
        for platform in ("x", "tiktok", "facebook"):
            with self.subTest(platform=platform):
                self.assertTrue(PLATFORMS[platform].repost_patterns)
        for platform in ("instagram", "threads"):
            with self.subTest(platform=platform):
                self.assertFalse(PLATFORMS[platform].repost_patterns)

    def test_supported_actions_order_and_platform_filter(self):
        self.assertEqual(supported_actions("x"), ("like", "comment", "share", "repost"))
        self.assertEqual(supported_actions("instagram"), ("like", "comment", "share"))

    def test_normalize_actions_defaults_to_like_and_comment(self):
        self.assertEqual(normalize_actions("instagram", None), ["like", "comment"])
        self.assertEqual(normalize_actions("instagram", []), ["like", "comment"])

    def test_normalize_actions_sorts_and_deduplicates(self):
        self.assertEqual(
            normalize_actions("x", ["repost", "like", "like", " repost "]),
            ["like", "repost"],
        )

    def test_normalize_actions_rejects_unknown_and_unsupported(self):
        with self.assertRaises(ValueError):
            normalize_actions("instagram", ["like", "download"])
        with self.assertRaises(ValueError):
            normalize_actions("instagram", ["repost"])

    def test_platform_action_options_match_normalize(self):
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                options = platform_action_options(platform)
                self.assertEqual([item["id"] for item in options], ["like", "comment", "share", "repost"])
                self.assertEqual(
                    [item["id"] for item in options if item["supported"]],
                    list(supported_actions(platform)),
                )


if __name__ == "__main__":
    unittest.main()
