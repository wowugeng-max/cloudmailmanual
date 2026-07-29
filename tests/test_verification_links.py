import unittest
from unittest.mock import patch

from cloudmailmanual_app.services.verification_links import extract_verification_link


class VerificationLinkExtractionTest(unittest.TestCase):
    def test_extracts_action_link_and_preserves_original_tracking_href(self):
        href = (
            "https://awstrack.me/L0/https:%2F%2Fservice.example%2Fverify-email"
            "%3Ftoken%3Dredacted/abc"
        )
        html = f'<a href="{href}">Verify Email Address</a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_prefers_verify_action_over_footer_links(self):
        html = (
            '<a href="https://example.test/confirm?token=abc">Confirm account</a>'
            '<a href="https://example.test/preferences">Manage preferences</a>'
            '<a href="https://example.test/privacy">Privacy policy</a>'
            '<a href="https://example.test/contact">Company footer</a>'
        )

        self.assertEqual(
            extract_verification_link(html),
            "https://example.test/confirm?token=abc",
        )

    def test_rejects_unsafe_relative_and_unrelated_links(self):
        cases = (
            ("javascript", '<a href="javascript:alert(1)">Verify</a>'),
            ("data", '<a href="data:text/html,verify">Verify</a>'),
            ("mailto", '<a href="mailto:help@example.test">Confirm</a>'),
            ("relative", '<a href="/verify-email?token=abc">Verify</a>'),
            (
                "unrelated_http",
                '<a href="https://example.test/privacy">Privacy policy</a>',
            ),
        )

        for case, html in cases:
            with self.subTest(case=case):
                self.assertIsNone(extract_verification_link(html))

    def test_skips_unsafe_and_unrelated_links_before_valid_action(self):
        html = (
            '<a href="javascript:alert(1)">Verify</a>'
            '<a href="https://example.test/privacy">Privacy policy</a>'
            '<a href="/confirm?token=relative">Confirm</a>'
            '<a href="https://example.test/activate?token=abc">Activate account</a>'
        )

        self.assertEqual(
            extract_verification_link(html),
            "https://example.test/activate?token=abc",
        )

    def test_tolerates_malformed_html_and_missing_href(self):
        html = (
            '<a>Missing href</a><a href="https://example.test/activate?token=abc">'
            '<strong>Activate</strong>'
        )

        self.assertEqual(
            extract_verification_link(html),
            "https://example.test/activate?token=abc",
        )

    def test_returns_none_when_no_action_evidence_exists(self):
        html = '<a href="https://example.test/news">Read our news</a>'

        self.assertIsNone(extract_verification_link(html))

    def test_token_evidence_without_action_word_is_not_a_candidate(self):
        html = (
            '<a href="https://example.test/account?token=redacted">'
            "Open account"
            "</a>"
        )

        self.assertIsNone(extract_verification_link(html))

    def test_prefers_first_action_link_when_scores_are_equal(self):
        first_href = "https://first.example.test/verify"
        second_href = "https://second.example.test/verify"
        html = (
            f'<a href="{first_href}">Verify account</a>'
            f'<a href="{second_href}">Verify account</a>'
        )

        self.assertEqual(extract_verification_link(html), first_href)

    def test_does_not_match_activate_inside_deactivate_text(self):
        html = (
            '<a href="https://example.test/account">'
            "Deactivate account"
            "</a>"
        )

        self.assertIsNone(extract_verification_link(html))

    def test_does_not_match_complete_inside_opaque_token_value(self):
        html = (
            '<a href="https://example.test/account?token=incomplete123">'
            "Open account"
            "</a>"
        )

        self.assertIsNone(extract_verification_link(html))

    def test_ignores_action_words_in_opaque_query_and_fragment_values(self):
        hrefs = (
            "https://example.test/account?token=confirm",
            "https://example.test/account?token=abc-confirm-xyz",
            "https://example.test/account#token=activate",
            "https://example.test/account?signature=complete",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Open account</a>'
                self.assertIsNone(extract_verification_link(html))

    def test_does_not_use_hostname_as_url_action_evidence(self):
        html = (
            '<a href="https://verify.example.test/privacy">'
            "Privacy policy"
            "</a>"
        )

        self.assertIsNone(extract_verification_link(html))

    def test_verification_support_word_is_not_an_action(self):
        html = (
            '<a href="https://example.test/account">'
            "Verification details"
            "</a>"
        )

        self.assertIsNone(extract_verification_link(html))

    def test_accepts_bounded_actions_in_url_path_query_and_fragment(self):
        hrefs = (
            "https://example.test/verify-email",
            "https://example.test/account?action=verify",
            "https://example.test/account#confirm",
            "https://example.test/account?confirm=1",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Open account</a>'
                self.assertEqual(extract_verification_link(html), href)

    def test_extracts_action_from_aws_encoded_tracking_path(self):
        href = (
            "https://awstrack.me/L0/https:%2F%2Fservice.test%2Fapi%2Fverify-email"
            "%3Ftoken%3Dredacted/abc"
        )
        html = f'<a href="{href}">Click here</a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_ignores_encoded_query_values_after_tracking_path_separator(self):
        href = (
            "https://awstrack.me/L0/https:%2F%2Fservice.test%2Fapi%2Faccount"
            "%3Ftoken%3Dconfirm/abc"
        )
        html = f'<a href="{href}">Click here</a>'

        self.assertIsNone(extract_verification_link(html))

    def test_ignores_invisible_anchor_text(self):
        cases = (
            ("script", "confirm()"),
            ("style", "verify"),
            ("template", "complete"),
        )

        for tag, hidden_text in cases:
            with self.subTest(tag=tag):
                html = (
                    '<a href="https://example.test/news">'
                    f"<{tag}>{hidden_text}</{tag}>Read news"
                    "</a>"
                )
                self.assertIsNone(extract_verification_link(html))

    def test_treats_noscript_text_as_visible_anchor_text(self):
        href = "https://example.test/account"
        html = f'<a href="{href}"><noscript>Verify account</noscript></a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_rejects_malformed_absolute_http_urls(self):
        hrefs = (
            "https://example.test/verify now",
            "https://example.test/\x00verify",
            "https://./verify",
            "https://user@example.test/verify",
            "https://example.test:invalid/verify",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Verify account</a>'
                self.assertIsNone(extract_verification_link(html))

    def test_returns_none_for_non_string_html_without_parsing(self):
        parser_path = (
            "cloudmailmanual_app.services.verification_links._AnchorParser"
        )
        with patch(parser_path) as parser:
            self.assertIsNone(extract_verification_link(b"not html"))

        parser.assert_not_called()

    def test_does_not_swallow_unexpected_parser_errors(self):
        feed_path = (
            "cloudmailmanual_app.services.verification_links._AnchorParser.feed"
        )
        with patch(feed_path, side_effect=RuntimeError("unexpected parser failure")):
            with self.assertRaisesRegex(RuntimeError, "unexpected parser failure"):
                extract_verification_link("<a href='https://example.test/verify'>")


if __name__ == "__main__":
    unittest.main()
