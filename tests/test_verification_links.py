from unittest import TestCase

from cloudmailmanual_app.services.verification_links import extract_verification_link


class VerificationLinkExtractionTest(TestCase):
    def test_extracts_action_link_and_preserves_original_tracking_href(self):
        href = (
            "https://awstrack.me/L0/https:%2F%2Fservice.example%2Fverify-email"
            "%3Ftoken%3Dredacted/abc"
        )
        html = f'<a href="{href}">Verify Email Address</a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_prefers_verify_action_over_footer_links(self):
        html = (
            '<a href="https://example.test/">Company logo</a>'
            '<a href="https://example.test/preferences">Manage preferences</a>'
            '<a href="https://example.test/confirm?token=abc">Confirm account</a>'
        )

        self.assertEqual(
            extract_verification_link(html),
            "https://example.test/confirm?token=abc",
        )

    def test_rejects_unsafe_relative_and_unrelated_links(self):
        html = (
            '<a href="javascript:alert(1)">Verify</a>'
            '<a href="data:text/html,verify">Verify</a>'
            '<a href="mailto:help@example.test">Confirm</a>'
            '<a href="/verify-email?token=abc">Verify</a>'
            '<a href="https://example.test/privacy">Privacy policy</a>'
        )

        self.assertIsNone(extract_verification_link(html))

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
