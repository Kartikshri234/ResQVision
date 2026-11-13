from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient

from accounts.models import User

from .models import Accident, Alert, Camera, Hospital, PoliceStation, SystemSetting


class AccidentIngestionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="AdminPassword9!"
        )
        self.police_station = PoliceStation.objects.create(
            name="Central Police",
            latitude=12.9716,
            longitude=77.5946,
        )
        self.hospital = Hospital.objects.create(
            name="Central Hospital",
            latitude=12.9720,
            longitude=77.5950,
            accepting_emergencies=True,
        )
        self.police_user = User.objects.create_user(
            username="police",
            password="PolicePassword9!",
            role=User.Role.POLICE,
            police_station=self.police_station,
            is_approved=True,
        )
        self.hospital_user = User.objects.create_user(
            username="hospital",
            password="HospitalPassword9!",
            role=User.Role.HOSPITAL,
            hospital=self.hospital,
            is_approved=True,
        )
        self.camera = Camera.objects.create(
            camera_id="CAM-TEST",
            name="Test Camera",
            latitude=12.9716,
            longitude=77.5946,
            road_name="Test Road",
        )
        SystemSetting.objects.create(
            pk=1, min_confidence=0.7, auto_alert=True, notify_radius_km=25
        )

    def test_ingest_requires_api_key(self):
        response = self.client.post(
            "/api/ingest/",
            {"camera_id": "CAM-TEST", "confidence": 95},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Accident.objects.count(), 0)

    def test_high_confidence_ingest_persists_and_notifies_services(self):
        response = self.client.post(
            "/api/ingest/",
            {
                "camera_id": "CAM-TEST",
                "confidence": 95,
                "severity": "high",
                "location": "Test Road",
                "people_count": 2,
            },
            format="json",
            HTTP_X_API_KEY=settings.AI_SERVICE_API_KEY,
        )
        self.assertEqual(response.status_code, 201)
        accident = Accident.objects.get(accident_id=response.data["accident_id"])
        self.assertEqual(accident.status, "alert_sent")
        self.assertEqual(Alert.objects.filter(accident=accident).count(), 2)

        detail = self.client.get(f"/api/accidents/{accident.pk}/")
        self.assertEqual(detail.status_code, 403)
        self.client.force_authenticate(self.admin)
        detail = self.client.get(f"/api/accidents/{accident.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["status"], "alert_sent")

    def test_duplicate_camera_event_is_not_persisted(self):
        payload = {"camera_id": "CAM-TEST", "confidence": 80}
        first = self.client.post(
            "/api/ingest/", payload, format="json", HTTP_X_API_KEY=settings.AI_SERVICE_API_KEY
        )
        second = self.client.post(
            "/api/ingest/", payload, format="json", HTTP_X_API_KEY=settings.AI_SERVICE_API_KEY
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(Accident.objects.count(), 1)


class ResponseWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="workflow-admin", email="workflow@example.com", password="AdminPassword9!"
        )
        station = PoliceStation.objects.create(
            name="Workflow Police", latitude=12.0, longitude=77.0
        )
        self.police = User.objects.create_user(
            username="workflow-police",
            password="PolicePassword9!",
            role=User.Role.POLICE,
            police_station=station,
            is_approved=True,
        )
        accident = Accident.objects.create(
            latitude=12.0,
            longitude=77.0,
            location="Workflow Road",
            confidence=0.95,
            status="alert_sent",
        )
        self.alert = Alert.objects.create(
            accident=accident, kind="police", police_station=station
        )

    def test_assigned_responder_can_accept_and_admin_can_read_persisted_status(self):
        self.client.force_authenticate(self.police)
        response = self.client.post(
            f"/api/alerts/{self.alert.pk}/respond/", {"action": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "accepted")

        self.client.force_authenticate(self.admin)
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["role"], "admin")
