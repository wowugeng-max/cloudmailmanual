import unittest
from unittest.mock import patch

from cloudmailmanual_app.services import verification_links
from cloudmailmanual_app.services.verification_links import extract_verification_link


class VerificationLinkExtractionTest(unittest.TestCase):
    def test_mask_http_urls_replaces_matches_with_equal_length_spaces(self):
        href = "https://example.test/verify-email?token=ABC123"
        value = f'<a href="{href}">{href}</a>'
        expected = f'<a href="{" " * len(href)}">{" " * len(href)}</a>'
        mask_http_urls = getattr(verification_links, "mask_http_urls", None)

        self.assertIn("mask_http_urls", verification_links.__all__)
        self.assertIsNotNone(mask_http_urls)
        self.assertEqual(mask_http_urls(value), expected)
        self.assertEqual(len(mask_http_urls(value)), len(value))

    def test_extract_visible_html_text_decodes_data_without_scanning_attributes(self):
        html = (
            '<div title="&gt;ABC123">'
            "Your code is &lt;ABC123&gt;. "
            "Activate using https&#58;//example.test/verify-email?token=XYZ789"
            "</div>"
        )

        self.assertIn("extract_visible_html_text", verification_links.__all__)
        self.assertEqual(
            verification_links.extract_visible_html_text(html),
            (
                "Your code is <ABC123>. "
                "Activate using https://example.test/verify-email?token=XYZ789"
            ),
        )

    def test_extract_visible_html_text_excludes_invisible_elements(self):
        html = (
            "<head>&lt;/head&gt;ABC123</head>"
            "<script>&lt;/script&gt;ABC123</script>"
            "<style>&lt;/style&gt;ABC123</style>"
            "<template>&lt;/template&gt;ABC123</template>"
            "<p>Visible &lt;ABC123&gt;</p>"
        )

        self.assertEqual(
            verification_links.extract_visible_html_text(html),
            "Visible <ABC123>",
        )

    def test_visible_html_text_ignores_mismatched_hidden_end_tags(self):
        cases = (
            (
                "head",
                "<head></style>ABC123</head><p>Visible</p>",
            ),
            (
                "nested_head",
                (
                    "<head><script>SECRET1</script></template>ABC123</head>"
                    "<p>Visible</p>"
                ),
            ),
            (
                "script",
                "<script></head>ABC123</script><p>Visible</p>",
            ),
            (
                "style",
                "<style></template>ABC123</style><p>Visible</p>",
            ),
            (
                "template",
                "<template></head>ABC123</template><p>Visible</p>",
            ),
            (
                "nested_template",
                (
                    "<template><head>SECRET1</head></script>ABC123</template>"
                    "<p>Visible</p>"
                ),
            ),
        )

        for case, html in cases:
            with self.subTest(case=case):
                self.assertEqual(
                    verification_links.extract_visible_html_text(html),
                    "Visible",
                )

    def test_links_stay_hidden_after_mismatched_hidden_end_tags(self):
        href = "https://example.test/verify?token=XYZ789"
        cases = (
            ("head", f'<head></style><a href="{href}">Verify</a></head>'),
            (
                "nested_head",
                (
                    "<head><script>SECRET1</script></template>"
                    f'<a href="{href}">Verify</a></head>'
                ),
            ),
            ("script", f'<script></head><a href="{href}">Verify</a></script>'),
            ("style", f'<style></template><a href="{href}">Verify</a></style>'),
            (
                "template",
                f'<template></head><a href="{href}">Verify</a></template>',
            ),
            (
                "nested_template",
                (
                    "<template><head>SECRET1</head></script>"
                    f'<a href="{href}">Verify</a></template>'
                ),
            ),
        )

        for case, html in cases:
            with self.subTest(case=case):
                self.assertIsNone(extract_verification_link(html))

    def test_mask_http_urls_only_masks_literal_http_urls(self):
        encoded_href = "https&#58;//example.test/verify?token=ABC123"
        literal_href = "https://example.test/verify?token=XYZ789"
        value = f"{encoded_href} then {literal_href}"
        expected = f"{encoded_href} then {' ' * len(literal_href)}"

        masked = verification_links.mask_http_urls(value)

        self.assertEqual(masked, expected)
        self.assertEqual(len(masked), len(value))

    def test_mask_http_urls_keeps_plain_text_entities_literal(self):
        href = (
            "https://example.test/verify?x=1"
            "&NewLine;token=ABC123"
        )
        value = f"Activate using {href} now"
        expected = f"Activate using {' ' * len(href)} now"

        masked = verification_links.mask_http_urls(value)

        self.assertEqual(masked, expected)
        self.assertEqual(len(masked), len(value))

    def test_mask_http_urls_handles_empty_and_non_string_values(self):
        mask_http_urls = getattr(verification_links, "mask_http_urls", None)

        self.assertIsNotNone(mask_http_urls)
        self.assertEqual(mask_http_urls(""), "")
        self.assertEqual(mask_http_urls(None), "")

    def test_extracts_visible_html_bare_activation_url_with_long_query(self):
        href = (
            "https://app.example.test/api/auth/verify-email?"
            "token=eyJhbGciOiJIUzI1NiJ9.synthetic.signature"
            "&callbackURL=%2Fmanage%2Freferral"
        )
        html = (
            "<h1>Activate your account</h1>"
            "<p>Please click the link below to activate your account.</p>"
            f"<p>{href.replace('&', '&amp;')}</p>"
            "<p>If you did not create an account, ignore this email.</p>"
        )

        self.assertEqual(extract_verification_link(html), href)

    def test_extracts_plain_text_bare_verification_url(self):
        href = "https://example.test/verify-email?token=synthetic-value"
        text = f"Activate your account\n\n{href}\n\nIgnore this email if unexpected."

        self.assertEqual(extract_verification_link("", text), href)

    def test_extracts_anchor_whose_visible_label_is_the_full_url(self):
        href = "https://example.test/activate?token=synthetic-value"
        html = f'<a href="{href}">{href}</a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_repeated_href_uses_strongest_occurrence_context(self):
        href = "https://example.test/account?token=synthetic-value"
        html = (
            "<p>Activate your account:</p>"
            f'<a href="{href}">{href}</a>'
        )

        self.assertEqual(extract_verification_link(html), href)

    def test_nearby_action_copy_qualifies_generic_bare_token_url(self):
        href = "https://example.test/account?token=synthetic-value"
        text = f"Complete your account setup using this link: {href}"

        self.assertEqual(extract_verification_link("", text), href)

    def test_action_word_inside_opaque_bare_token_is_not_text_evidence(self):
        text = (
            "Account details: "
            "https://example.test/account?token=prefix-confirm-suffix"
        )

        self.assertIsNone(extract_verification_link("", text))

    def test_repeated_opaque_urls_do_not_become_nearby_action_text(self):
        href = "https://example.test/account?token=prefix-confirm-suffix"
        text = f"Account details: {href} {href}"

        self.assertIsNone(extract_verification_link("", text))

    def test_identical_candidates_are_scored_once(self):
        href = "https://example.test/verify?token=synthetic-value"
        padding = "x" * 160
        text = "".join(
            f"{padding} {href} {padding}"
            for _ in range(100)
        )

        with patch.object(
            verification_links,
            "_score_with_url_evidence",
            return_value=10,
            create=True,
        ) as score:
            self.assertEqual(extract_verification_link("", text), href)

        score.assert_called_once()

    def test_repeated_href_caches_validation_and_url_evidence(self):
        href = "https://example.test/verify?token=synthetic-value"
        text = f"First context {href} {'x' * 400} {href} second context"

        with patch.object(
            verification_links,
            "_is_absolute_http_url",
            wraps=verification_links._is_absolute_http_url,
        ) as validate, patch.object(
            verification_links,
            "urlsplit",
            wraps=verification_links.urlsplit,
        ) as split, patch.object(
            verification_links,
            "_url_evidence",
            wraps=verification_links._url_evidence,
        ) as url_evidence, patch.object(
            verification_links,
            "_score_with_url_evidence",
            return_value=10,
            create=True,
        ) as score:
            self.assertEqual(extract_verification_link("", text), href)

        validate.assert_called_once_with(href)
        self.assertEqual(split.call_count, 2)
        self.assertEqual(url_evidence.call_count, 1)
        self.assertEqual(score.call_count, 2)

    def test_ignores_bare_links_inside_invisible_html_content(self):
        html = (
            "<script>https://example.test/verify?token=script</script>"
            "<style>https://example.test/confirm?token=style</style>"
            "<template>https://example.test/activate?token=template</template>"
            "<p>Read the account update.</p>"
        )

        self.assertIsNone(extract_verification_link(html))

    def test_trims_sentence_punctuation_without_truncating_query(self):
        href = (
            "https://example.test/verify-email?token=synthetic-value"
            "&callbackURL=%2Fmanage%2Freferral"
        )
        text = f"Activate your account here ({href})."

        self.assertEqual(extract_verification_link("", text), href)

    def test_does_not_reconstruct_bare_url_across_whitespace(self):
        text = "Activate using https://\nexample.test/verify?token=synthetic-value"

        self.assertIsNone(extract_verification_link("", text))

    def test_extracts_action_link_and_preserves_original_tracking_href(self):
        href = (
            "https://awstrack.me/L0/https:%2F%2Fservice.example%2Fverify-email"
            "%3Ftoken%3Dredacted/abc"
        )
        html = f'<a href="{href}">Verify Email Address</a>'

        self.assertEqual(extract_verification_link(html), href)

    def test_rejects_anchor_hrefs_with_leading_or_trailing_whitespace(self):
        href = "https://example.test/verify?token=XYZ789"
        cases = (
            ("encoded_newline", f'&#10;{href}'),
            ("encoded_tab", f'&#9;{href}'),
            ("leading_space", f' {href}'),
            ("trailing_space", f'{href} '),
        )

        for case, raw_href in cases:
            with self.subTest(case=case):
                html = f'<a href="{raw_href}">Verify account</a>'
                self.assertIsNone(extract_verification_link(html))

    def test_empty_href_is_skipped_before_valid_action_link(self):
        href = "https://example.test/confirm?token=XYZ789"
        html = (
            '<a href="">Verify account</a>'
            f'<a href="{href}">Confirm account</a>'
        )

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

    def test_rejects_empty_ports_and_malformed_host_shapes(self):
        hrefs = (
            "https://example.test:/verify",
            "https://[2001:db8::1]:/verify",
            "https://example.test:65536/verify",
            "https://example..test/verify",
            r"https://example.test\evil/verify",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Verify account</a>'
                self.assertIsNone(extract_verification_link(html))

    def test_accepts_ipv6_and_explicit_ports(self):
        hrefs = (
            "https://example.test:8443/verify",
            "https://[2001:db8::1]/verify",
            "https://[2001:db8::1]:8443/verify",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Verify account</a>'
                self.assertEqual(extract_verification_link(html), href)

    def test_rejects_invalid_suffixes_after_bracketed_ipv6_host(self):
        hrefs = (
            "https://[2001:db8::1]evil/verify",
            "https://[2001:db8::1]]/verify",
            "https://[2001:db8::1]]:443/verify",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Verify account</a>'
                self.assertIsNone(extract_verification_link(html))

    def test_accepts_bracketed_ipv6_with_no_port_or_valid_port(self):
        hrefs = (
            "https://[2001:db8::1]/verify",
            "https://[2001:db8::1]:443/verify",
        )

        for href in hrefs:
            with self.subTest(href=href):
                html = f'<a href="{href}">Verify account</a>'
                self.assertEqual(extract_verification_link(html), href)

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
