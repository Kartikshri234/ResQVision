from django.test import TestCase
from rest_framework.test import APIClient

from .models import OTP, User


class AuthenticationFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="approved-user",
            password="CorrectPassword9!",
            email="user@example.com",
            role=User.Role.POLICE,
            is_approved=True,
        )

    def test_login_me_and_logout_round_trip(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "CorrectPassword9!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], self.user.username)

        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_invalid_login_is_rejected(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid", response.data["detail"])

    def test_otp_reset_consumes_code_and_allows_new_password(self):
        otp = OTP.issue(self.user)
        response = self.client.post(
            "/api/auth/reset-password/",
            {
                "identifier": self.user.username,
                "code": otp.code,
                "new_password": "NewCorrectPassword9!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        otp.refresh_from_db()
        self.assertTrue(otp.used)
        self.assertTrue(self.user.__class__.objects.get(pk=self.user.pk).check_password("NewCorrectPassword9!"))
