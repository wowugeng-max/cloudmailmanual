import unittest


class AppStructureTest(unittest.TestCase):
    def test_create_app_exposes_existing_routes(self):
        from cloudmailmanual_app.factory import create_app

        app = create_app()
        routes = {rule.rule for rule in app.url_map.iter_rules()}

        self.assertIn("/", routes)
        self.assertIn("/login", routes)
        self.assertIn("/api/register", routes)
        self.assertIn("/api/query-code", routes)
        self.assertIn("/api/history/accounts", routes)
        self.assertIn("/api/settings/mail-profiles", routes)
        self.assertIn("/api/domain-bodies", routes)

    def test_services_are_split_from_flask_routes(self):
        from cloudmailmanual_app.services.domains import generate_domain_bodies
        from cloudmailmanual_app.services.registration import generate_app_password, generate_profile

        profile = generate_profile()
        password = generate_app_password()
        domains = generate_domain_bodies(3, industry="mail", avoid_digits=True)

        self.assertIn("name", profile)
        self.assertEqual(len(password), 12)
        self.assertEqual(len(domains), 3)
        self.assertTrue(all(not any(ch.isdigit() for ch in item) for item in domains))


if __name__ == "__main__":
    unittest.main()
