"""Response workflow, escalation, role scoping and admin CRUD tests.

Covers the areas listed as untested in runtime-validation-report.md: hospital/ambulance dispatch,
escalation, admin CRUD, permissions across roles, notifications, analytics and system settings.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .models import (Accident, Alert, Ambulance, Camera, Hospital, Notification, PoliceStation,
                     SystemSetting, TimelineEvent)

PW = "Passw0rd!x9"


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, password=PW, role=role, is_approved=True,
                                    email=f"{username}@example.com", **extra)


class WorkflowBase(TestCase):
    """Two police stations and two hospitals (one near, one ~95 km away), each with a login account."""

    def setUp(self):
        self.client = APIClient()
        SystemSetting.get()
        self.admin = User.objects.create_superuser("wf-admin", "wf-admin@example.com", PW)

        self.police_near = PoliceStation.objects.create(name="Near Police", latitude=12.9716, longitude=77.5946)
        self.police_far = PoliceStation.objects.create(name="Far Police", latitude=13.6, longitude=78.2)
        self.hosp_near = Hospital.objects.create(name="Near Hospital", latitude=12.9720, longitude=77.5950,
                                                 total_beds=20, available_beds=10)
        self.hosp_far = Hospital.objects.create(name="Far Hospital", latitude=13.6, longitude=78.2)

        self.police_user = make_user("wf-police", "police", police_station=self.police_near)
        self.police_far_user = make_user("wf-police-far", "police", police_station=self.police_far)
        self.hosp_user = make_user("wf-hosp", "hospital", hospital=self.hosp_near)
        self.hosp_far_user = make_user("wf-hosp-far", "hospital", hospital=self.hosp_far)
        self.ambulance_user = make_user("wf-amb", "ambulance")

        # One accident with a police alert, one with a hospital alert, so statuses stay independent.
        self.accident = Accident.objects.create(
            latitude=12.9716, longitude=77.5946, location="Near Road", confidence=0.95,
            status="alert_sent", severity="high")
        self.p_alert = Alert.objects.create(accident=self.accident, kind="police",
                                            police_station=self.police_near, distance_km=0.1)
        self.h_accident = Accident.objects.create(
            latitude=12.9716, longitude=77.5946, location="Hospital Road", confidence=0.9, status="alert_sent")
        self.h_alert = Alert.objects.create(accident=self.h_accident, kind="hospital",
                                            hospital=self.hosp_near, distance_km=0.2)

    def respond(self, user, alert, **payload):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/alerts/{alert.pk}/respond/", payload, format="json")


# ---------------------------------------------------------------- police workflow & escalation
class PoliceWorkflowTests(WorkflowBase):
    def test_full_lifecycle_updates_alert_and_accident_status(self):
        self.assertEqual(self.respond(self.police_user, self.p_alert, action="accept").status_code, 200)
        self.accident.refresh_from_db()
        self.assertEqual(self.accident.status, "accepted")

        # A police dispatch needs a team name.
        self.assertEqual(self.respond(self.police_user, self.p_alert, action="dispatch").status_code, 400)
        r = self.respond(self.police_user, self.p_alert, action="dispatch", team_name="Patrol 7")
        self.assertEqual(r.status_code, 200)
        self.accident.refresh_from_db()
        self.assertEqual(self.accident.status, "team_dispatched")

        self.assertEqual(self.respond(self.police_user, self.p_alert, action="arrive").status_code, 200)
        self.accident.refresh_from_db()
        self.assertEqual(self.accident.status, "arrived")

        self.assertEqual(self.respond(self.police_user, self.p_alert, action="resolve").status_code, 200)
        self.accident.refresh_from_db()
        self.assertEqual(self.accident.status, "resolved")
        self.p_alert.refresh_from_db()
        self.assertEqual(self.p_alert.team_name, "Patrol 7")
        self.assertGreaterEqual(TimelineEvent.objects.filter(accident=self.accident).count(), 4)

    def test_actions_out_of_order_are_rejected(self):
        for action in ("dispatch", "arrive", "resolve"):
            r = self.respond(self.police_user, self.p_alert, action=action, team_name="X")
            self.assertEqual(r.status_code, 400, action)
        self.p_alert.refresh_from_db()
        self.assertEqual(self.p_alert.status, "pending")

    def test_unknown_action_is_rejected(self):
        self.assertEqual(self.respond(self.police_user, self.p_alert, action="explode").status_code, 400)

    def test_reject_requires_a_reason(self):
        self.assertEqual(self.respond(self.police_user, self.p_alert, action="reject").status_code, 400)
        self.assertEqual(self.respond(self.police_user, self.p_alert, action="reject", reason="  ").status_code, 400)
        self.p_alert.refresh_from_db()
        self.assertEqual(self.p_alert.status, "pending")

    def test_rejection_escalates_to_next_nearest_station(self):
        r = self.respond(self.police_user, self.p_alert, action="reject", reason="No officers free")
        self.assertEqual(r.status_code, 200)
        self.p_alert.refresh_from_db()
        self.assertEqual(self.p_alert.status, "rejected")
        self.assertEqual(self.p_alert.reject_reason, "No officers free")

        rerouted = Alert.objects.get(accident=self.accident, kind="police", police_station=self.police_far)
        self.assertEqual(rerouted.status, "pending")
        self.assertTrue(TimelineEvent.objects.filter(accident=self.accident, message__icontains="re-routed").exists())
        self.assertTrue(Notification.objects.filter(user=self.police_far_user, accident=self.accident).exists())
        self.accident.refresh_from_db()
        self.assertEqual(self.accident.status, "alert_sent")

    def test_rejection_with_no_other_station_alerts_admins(self):
        self.police_far.delete()
        self.respond(self.police_user, self.p_alert, action="reject", reason="Out of service")
        self.assertEqual(Alert.objects.filter(accident=self.accident, kind="police").count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.admin, title__startswith="Action needed").exists())
        self.assertTrue(TimelineEvent.objects.filter(accident=self.accident,
                                                     message__icontains="No other available police").exists())

    def test_cannot_act_on_a_closed_incident(self):
        self.accident.status = "closed"
        self.accident.save()
        r = self.respond(self.police_user, self.p_alert, action="accept")
        self.assertEqual(r.status_code, 400)
        self.assertIn("closed", r.data["error"].lower())


class AlertPermissionTests(WorkflowBase):
    def test_only_the_assigned_organisation_can_respond(self):
        for user in (self.police_far_user, self.hosp_user, self.hosp_far_user, self.ambulance_user):
            r = self.respond(user, self.p_alert, action="accept")
            self.assertEqual(r.status_code, 403, user.username)
        self.p_alert.refresh_from_db()
        self.assertEqual(self.p_alert.status, "pending")

    def test_unauthenticated_request_is_refused(self):
        self.client.force_authenticate(None)
        r = self.client.post(f"/api/alerts/{self.p_alert.pk}/respond/", {"action": "accept"}, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_admin_can_respond_on_behalf_and_it_is_recorded(self):
        r = self.respond(self.admin, self.p_alert, action="accept")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(TimelineEvent.objects.filter(accident=self.accident, message__icontains="via admin").exists())

    def test_missing_alert_returns_404(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/alerts/999999/respond/", {"action": "accept"}, format="json")
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------- hospital / ambulance dispatch
class HospitalDispatchTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        self.amb = Ambulance.objects.create(hospital=self.hosp_near, vehicle_number="KA-01-AMB-1")
        self.other_amb = Ambulance.objects.create(hospital=self.hosp_far, vehicle_number="KA-02-AMB-9")

    def test_dispatch_assigns_ambulance_and_resolve_frees_it(self):
        self.assertEqual(self.respond(self.hosp_user, self.h_alert, action="accept").status_code, 200)

        # Must pick an ambulance when one is available.
        self.assertEqual(self.respond(self.hosp_user, self.h_alert, action="dispatch").status_code, 400)
        # Cannot borrow another hospital's ambulance.
        r = self.respond(self.hosp_user, self.h_alert, action="dispatch", ambulance_id=self.other_amb.pk)
        self.assertEqual(r.status_code, 400)

        r = self.respond(self.hosp_user, self.h_alert, action="dispatch", ambulance_id=self.amb.pk)
        self.assertEqual(r.status_code, 200)
        self.amb.refresh_from_db()
        self.h_alert.refresh_from_db()
        self.assertEqual(self.amb.status, "dispatched")
        self.assertEqual(self.h_alert.ambulance_id, self.amb.pk)

        # An already-dispatched ambulance cannot be assigned a second time.
        other = Alert.objects.create(accident=self.accident, kind="hospital", hospital=self.hosp_near,
                                     status="accepted")
        r = self.respond(self.hosp_user, other, action="dispatch", ambulance_id=self.amb.pk)
        self.assertEqual(r.status_code, 400)

        self.assertEqual(self.respond(self.hosp_user, self.h_alert, action="resolve").status_code, 200)
        self.amb.refresh_from_db()
        self.assertEqual(self.amb.status, "available")
        self.h_accident.refresh_from_db()
        self.assertEqual(self.h_accident.status, "resolved")

    def test_dispatch_without_any_ambulance_sends_staff(self):
        self.amb.delete()
        self.respond(self.hosp_user, self.h_alert, action="accept")
        r = self.respond(self.hosp_user, self.h_alert, action="dispatch")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(TimelineEvent.objects.filter(accident=self.h_accident,
                                                     message__icontains="emergency staff").exists())

    def test_hospital_rejection_escalates_to_accepting_hospital_only(self):
        self.hosp_far.accepting_emergencies = False
        self.hosp_far.save()
        self.respond(self.hosp_user, self.h_alert, action="reject", reason="No beds")
        self.assertFalse(Alert.objects.filter(accident=self.h_accident, hospital=self.hosp_far).exists())
        self.assertTrue(Notification.objects.filter(user=self.admin, title__startswith="Action needed").exists())

        self.hosp_far.accepting_emergencies = True
        self.hosp_far.save()
        alert = Alert.objects.create(accident=self.accident, kind="hospital", hospital=self.hosp_near)
        self.respond(self.hosp_user, alert, action="reject", reason="No beds")
        self.assertTrue(Alert.objects.filter(accident=self.accident, hospital=self.hosp_far).exists())

    def test_ambulance_crud_is_scoped_to_own_hospital(self):
        self.client.force_authenticate(self.hosp_user)
        r = self.client.post("/api/ambulances/", {"vehicle_number": "KA-01-AMB-2", "driver_name": "Ravi"},
                             format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["hospital"], "Near Hospital")
        self.assertEqual(self.client.post("/api/ambulances/", {"vehicle_number": " "}, format="json").status_code, 400)

        listing = self.client.get("/api/ambulances/")
        self.assertEqual({a["vehicle_number"] for a in listing.data}, {"KA-01-AMB-1", "KA-01-AMB-2"})

        r = self.client.patch(f"/api/ambulances/{self.amb.pk}/", {"status": "maintenance"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "maintenance")
        r = self.client.patch(f"/api/ambulances/{self.amb.pk}/", {"status": "bogus"}, format="json")
        self.assertEqual(r.data["status"], "maintenance")  # invalid status is ignored

        # Another hospital cannot touch it.
        self.client.force_authenticate(self.hosp_far_user)
        self.assertEqual(self.client.patch(f"/api/ambulances/{self.amb.pk}/", {"status": "available"},
                                           format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/ambulances/{self.amb.pk}/").status_code, 403)

        # Police are not allowed at all.
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.get("/api/ambulances/").status_code, 403)

    def test_admin_ambulance_creation_needs_a_hospital(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/ambulances/", {"vehicle_number": "X-1"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/ambulances/", {"vehicle_number": "X-1", "hospital": self.hosp_near.pk},
                             format="json")
        self.assertEqual(r.status_code, 201)

    def test_hospital_me_validates_bed_counts(self):
        self.client.force_authenticate(self.hosp_user)
        r = self.client.patch("/api/hospital/me/", {"total_beds": 5, "available_beds": 9}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch("/api/hospital/me/", {"available_beds": "many"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch("/api/hospital/me/", {"accepting_emergencies": False, "available_beds": 4},
                              format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["accepting_emergencies"])
        self.assertEqual(r.data["available_beds"], 4)

        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.get("/api/hospital/me/").status_code, 404)


# ---------------------------------------------------------------- role scoping
class RoleScopingTests(WorkflowBase):
    def ids(self, response):
        return {row["id"] for row in response.data}

    def test_police_only_see_accidents_their_station_was_alerted_about(self):
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.ids(self.client.get("/api/accidents/")), {self.accident.pk})
        self.assertEqual(self.client.get(f"/api/accidents/{self.accident.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/accidents/{self.h_accident.pk}/").status_code, 404)

        self.client.force_authenticate(self.police_far_user)
        self.assertEqual(self.ids(self.client.get("/api/accidents/")), set())
        self.assertEqual(self.client.get(f"/api/accidents/{self.accident.pk}/").status_code, 404)

    def test_hospital_only_sees_its_own_accidents(self):
        self.client.force_authenticate(self.hosp_user)
        self.assertEqual(self.ids(self.client.get("/api/accidents/")), {self.h_accident.pk})

    def test_account_without_organisation_sees_nothing(self):
        self.client.force_authenticate(self.ambulance_user)
        self.assertEqual(self.ids(self.client.get("/api/accidents/")), set())

    def test_admin_sees_everything_and_alert_detail(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.ids(self.client.get("/api/accidents/")), {self.accident.pk, self.h_accident.pk})
        detail = self.client.get(f"/api/accidents/{self.accident.pk}/")
        self.assertIn("alerts", detail.data)
        self.client.force_authenticate(self.police_user)
        self.assertNotIn("alerts", self.client.get(f"/api/accidents/{self.accident.pk}/").data)

    def test_view_filters_for_responders(self):
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.ids(self.client.get("/api/accidents/?view=new")), {self.accident.pk})
        self.assertEqual(self.ids(self.client.get("/api/accidents/?view=active")), set())
        self.respond(self.police_user, self.p_alert, action="accept")
        self.assertEqual(self.ids(self.client.get("/api/accidents/?view=new")), set())
        self.assertEqual(self.ids(self.client.get("/api/accidents/?view=active")), {self.accident.pk})

    def test_admin_filters_search_and_severity(self):
        pending = Accident.objects.create(latitude=12.9, longitude=77.5, location="Pending Lane",
                                          confidence=0.5, status="verification_pending")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.ids(self.client.get("/api/accidents/?view=new")), {pending.pk})
        self.assertEqual(self.ids(self.client.get("/api/accidents/?severity=high")), {self.accident.pk})
        self.assertEqual(self.ids(self.client.get("/api/accidents/?q=Hospital Road")), {self.h_accident.pk})
        # An unknown severity is ignored rather than breaking the query.
        self.assertEqual(len(self.client.get("/api/accidents/?severity=nonsense").data), 3)

    def test_dashboards_are_role_specific(self):
        self.client.force_authenticate(self.police_user)
        data = self.client.get("/api/dashboard/").data
        self.assertEqual((data["role"], data["org"], data["new"]), ("police", "Near Police", 1))

        self.client.force_authenticate(self.hosp_user)
        data = self.client.get("/api/dashboard/").data
        self.assertEqual(data["role"], "hospital")
        self.assertEqual(data["hospital"]["available_beds"], 10)

        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/dashboard/").data
        self.assertEqual((data["role"], data["total"], data["active"]), ("admin", 2, 2))
        self.assertEqual(len(data["daily"]), 7)

    def test_map_hides_cameras_and_unverified_incidents_from_responders(self):
        Camera.objects.create(camera_id="CAM-M", name="Map Cam", latitude=12.9, longitude=77.5)
        Accident.objects.create(latitude=12.9, longitude=77.5, confidence=0.4, status="verification_pending")
        self.client.force_authenticate(self.police_user)
        data = self.client.get("/api/map/").data
        self.assertEqual(data["cameras"], [])
        self.assertEqual(len(data["accidents"]), 1)
        self.assertEqual(data["me"], {"kind": "police", "id": self.police_near.pk})

        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/map/").data
        self.assertEqual(len(data["cameras"]), 1)
        self.assertEqual(len(data["accidents"]), 3)

    def test_every_endpoint_requires_authentication(self):
        self.client.force_authenticate(None)
        for url in ("/api/dashboard/", "/api/map/", "/api/accidents/", "/api/hospitals/", "/api/cameras/",
                    "/api/notifications/", "/api/analytics/", "/api/settings/", "/api/users/"):
            self.assertIn(self.client.get(url).status_code, (401, 403), url)


# ---------------------------------------------------------------- admin actions
class AdminActionTests(WorkflowBase):
    def test_confirm_sends_alerts_once(self):
        pending = Accident.objects.create(latitude=12.9716, longitude=77.5946, confidence=0.5,
                                          status="verification_pending")
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.post(f"/api/accidents/{pending.pk}/confirm/").status_code, 403)

        self.client.force_authenticate(self.admin)
        r = self.client.post(f"/api/accidents/{pending.pk}/confirm/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "alert_sent")
        self.assertEqual(Alert.objects.filter(accident=pending).count(), 2)  # nearest police + hospital
        self.assertEqual(self.client.post(f"/api/accidents/{pending.pk}/confirm/").status_code, 400)

    def test_close_resolves_alerts_frees_ambulances_and_notifies(self):
        amb = Ambulance.objects.create(hospital=self.hosp_near, vehicle_number="C-1", status="dispatched")
        self.h_alert.status, self.h_alert.ambulance = "dispatched", amb
        self.h_alert.save()

        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.post(f"/api/accidents/{self.h_accident.pk}/close/").status_code, 403)

        self.client.force_authenticate(self.admin)
        r = self.client.post(f"/api/accidents/{self.h_accident.pk}/close/", {"reason": "False alarm"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "closed")
        self.h_alert.refresh_from_db()
        amb.refresh_from_db()
        self.assertEqual(self.h_alert.status, "resolved")
        self.assertEqual(amb.status, "available")
        self.assertTrue(Notification.objects.filter(user=self.hosp_user, title__icontains="closed").exists())
        self.assertTrue(TimelineEvent.objects.filter(accident=self.h_accident, message__icontains="False alarm").exists())
        self.assertEqual(self.client.post(f"/api/accidents/{self.h_accident.pk}/close/").status_code, 400)

    def test_settings_validation_and_scaling(self):
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.get("/api/settings/").status_code, 403)

        self.client.force_authenticate(self.admin)
        r = self.client.patch("/api/settings/", {"min_confidence": 80, "max_police": 3, "notify_radius_km": 0.2},
                              format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["min_confidence"], 80)
        self.assertEqual(r.data["notify_radius_km"], 1.0)  # clamped to a 1 km minimum
        self.assertEqual(SystemSetting.get().min_confidence, 0.8)

        for bad in ({"min_confidence": "abc"}, {"min_confidence": 150}, {"min_confidence": -5},
                    {"max_police": "two"}):
            self.assertEqual(self.client.patch("/api/settings/", bad, format="json").status_code, 400, bad)
        self.assertEqual(SystemSetting.get().min_confidence, 0.8)

    def test_disabling_auto_alert_routes_new_events_to_verification(self):
        self.client.force_authenticate(self.admin)
        self.client.patch("/api/settings/", {"auto_alert": False}, format="json")
        Camera.objects.create(camera_id="CAM-S", name="S", latitude=12.97, longitude=77.59)
        from django.conf import settings
        self.client.force_authenticate(None)
        r = self.client.post("/api/ingest/", {"camera_id": "CAM-S", "confidence": 99}, format="json",
                             HTTP_X_API_KEY=settings.AI_SERVICE_API_KEY)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "verification_pending")

    def test_analytics_shape_and_access(self):
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.get("/api/analytics/").status_code, 403)

        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/analytics/").data
        self.assertEqual(set(data), {"daily", "hours", "severity", "types", "status", "alerts", "ai"})
        self.assertEqual(len(data["daily"]), 14)
        self.assertEqual(len(data["hours"]), 24)
        self.assertEqual(sum(data["hours"]), 2)
        self.assertEqual(data["alerts"]["total"], 2)
        self.assertEqual(data["alerts"]["acceptance_rate"], 0)
        self.assertEqual(data["ai"]["detections"], 2)

        self.respond(self.police_user, self.p_alert, action="accept")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/analytics/").data["alerts"]["acceptance_rate"], 50)


# ---------------------------------------------------------------- organisation / camera CRUD
class OrganisationCrudTests(WorkflowBase):
    def test_only_admin_can_create_update_or_delete_hospitals(self):
        body = {"name": "New Hospital", "latitude": 12.5, "longitude": 77.5, "total_beds": 30,
                "available_beds": 12}
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.post("/api/hospitals/", body, format="json").status_code, 403)
        self.client.force_authenticate(self.hosp_user)
        self.assertEqual(self.client.patch(f"/api/hospitals/{self.hosp_near.pk}/", {"name": "x"},
                                           format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/hospitals/{self.hosp_near.pk}/").status_code, 403)

        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/hospitals/", body, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["total_beds"], 30)
        pk = r.data["id"]
        r = self.client.patch(f"/api/hospitals/{pk}/", {"name": "Renamed", "is_active": False}, format="json")
        self.assertEqual((r.data["name"], r.data["is_active"]), ("Renamed", False))
        self.assertEqual(self.client.delete(f"/api/hospitals/{pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/hospitals/{pk}/").status_code, 404)

    def test_create_validation(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post("/api/police-stations/", {"latitude": 1, "longitude": 1},
                                          format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/police-stations/", {"name": "No Coords"},
                                          format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/police-stations/",
                                          {"name": "Bad", "latitude": "north", "longitude": 1},
                                          format="json").status_code, 400)
        self.assertEqual(PoliceStation.objects.count(), 2)

    def test_inactive_organisations_are_hidden_from_non_admins(self):
        PoliceStation.objects.create(name="Closed Station", latitude=1, longitude=1, is_active=False)
        self.client.force_authenticate(self.police_user)
        names = {p["name"] for p in self.client.get("/api/police-stations/").data}
        self.assertNotIn("Closed Station", names)
        self.client.force_authenticate(self.admin)
        names = {p["name"] for p in self.client.get("/api/police-stations/").data}
        self.assertIn("Closed Station", names)

    def test_linking_an_account_checks_role_and_uniqueness(self):
        self.client.force_authenticate(self.admin)
        url = f"/api/hospitals/{self.hosp_far.pk}/"
        r = self.client.patch(url, {"account_username": self.police_user.username}, format="json")
        self.assertEqual(r.status_code, 400)  # wrong role
        r = self.client.patch(url, {"account_username": self.hosp_user.username}, format="json")
        self.assertEqual(r.status_code, 400)  # already linked to another hospital
        r = self.client.patch(url, {"account_username": ""}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["account"], "")

    def test_camera_crud_is_admin_only_and_validates(self):
        self.client.force_authenticate(self.police_user)
        self.assertEqual(self.client.get("/api/cameras/").status_code, 403)

        self.client.force_authenticate(self.admin)
        body = {"camera_id": "CAM-N1", "name": "North", "latitude": 12.1, "longitude": 77.1}
        r = self.client.post("/api/cameras/", body, format="json")
        self.assertEqual(r.status_code, 201)
        pk = r.data["id"]
        self.assertEqual(self.client.post("/api/cameras/", body, format="json").status_code, 400)  # duplicate id
        self.assertEqual(self.client.post("/api/cameras/", {"camera_id": "", "name": "x"},
                                          format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/cameras/{pk}/", {"latitude": "abc"},
                                           format="json").status_code, 400)
        r = self.client.patch(f"/api/cameras/{pk}/", {"is_active": False, "road_name": "NH-4"}, format="json")
        self.assertEqual((r.data["is_active"], r.data["road_name"]), (False, "NH-4"))
        self.assertEqual(self.client.delete(f"/api/cameras/{pk}/").status_code, 200)
        self.assertFalse(Camera.objects.filter(pk=pk).exists())


# ---------------------------------------------------------------- notifications
class NotificationTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        self.n1 = Notification.objects.create(user=self.police_user, title="One", message="m1")
        self.n2 = Notification.objects.create(user=self.police_user, title="Two", message="m2")
        self.theirs = Notification.objects.create(user=self.hosp_user, title="Other", message="m3")

    def test_list_only_returns_own_notifications(self):
        self.client.force_authenticate(self.police_user)
        data = self.client.get("/api/notifications/").data
        self.assertEqual(data["unread"], 2)
        self.assertEqual({n["title"] for n in data["items"]}, {"One", "Two"})

    def test_mark_one_then_all_read(self):
        self.client.force_authenticate(self.police_user)
        self.client.post(f"/api/notifications/{self.n1.pk}/read/")
        self.assertEqual(self.client.get("/api/notifications/").data["unread"], 1)
        self.client.post("/api/notifications/read/")
        self.assertEqual(self.client.get("/api/notifications/").data["unread"], 0)

    def test_cannot_mark_someone_elses_notification(self):
        self.client.force_authenticate(self.police_user)
        self.client.post(f"/api/notifications/{self.theirs.pk}/read/")
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_alert_dispatch_notifies_responders_and_admins(self):
        Notification.objects.all().delete()
        self.respond(self.police_user, self.p_alert, action="accept")
        self.assertTrue(Notification.objects.filter(user=self.admin, accident=self.accident).exists())
