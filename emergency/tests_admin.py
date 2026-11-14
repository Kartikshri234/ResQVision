from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .models import Hospital, PoliceStation


class AdminOverviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="overview-admin",
            email="overview@example.com",
            password="AdminPassword9!",
        )
        PoliceStation.objects.create(name="Overview Police", latitude=12.0, longitude=77.0)
        Hospital.objects.create(name="Overview Hospital", latitude=12.1, longitude=77.1)

    def test_admin_overview_returns_console_sections(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/admin/overview/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"accounts", "police", "hospitals", "recent_logins", "activity"})
        self.assertEqual(response.data["police"][0]["name"], "Overview Police")
        self.assertEqual(response.data["hospitals"][0]["name"], "Overview Hospital")

    def test_non_admin_cannot_read_admin_overview(self):
        user = User.objects.create_user(
            username="overview-police",
            password="PolicePassword9!",
            role=User.Role.POLICE,
            is_approved=True,
        )
        self.client.force_authenticate(user)

        self.assertEqual(self.client.get("/api/admin/overview/").status_code, 403)
