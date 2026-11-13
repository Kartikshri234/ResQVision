from django.test import TestCase


class WebShellTests(TestCase):
    def test_homepage_renders_application_shell_and_sets_csrf_cookie(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ResQVision")
        self.assertIn("csrftoken", response.cookies)

    def test_missing_route_returns_not_found(self):
        response = self.client.get("/does-not-exist/")
        self.assertEqual(response.status_code, 404)
