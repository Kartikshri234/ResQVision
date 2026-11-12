"""python manage.py seed_demo  ->  demo users, hospitals, police stations, cameras and sample accidents."""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from emergency import services
from emergency.models import Accident, Ambulance, Camera, Hospital, PoliceStation, SystemSetting

User = get_user_model()

CAMERAS = [
    ("CAM-001", "ITO Junction", 28.6304, 77.2410, "Vikas Marg, ITO"),
    ("CAM-002", "AIIMS Flyover", 28.5672, 77.2100, "Ring Road, AIIMS"),
    ("CAM-003", "Dhaula Kuan", 28.5920, 77.1620, "NH-48, Dhaula Kuan"),
    ("CAM-004", "Kashmere Gate", 28.6676, 77.2288, "Ring Road, Kashmere Gate"),
    ("CAM-005", "Nehru Place", 28.5494, 77.2519, "Outer Ring Road, Nehru Place"),
]
HOSPITALS = [  # name, lat, lng, phone, beds, username
    ("AIIMS Trauma Centre", 28.5672, 77.2100, "011-26588500", 60, "hosp_aiims"),
    ("Safdarjung Hospital", 28.5686, 77.2064, "011-26707444", 45, "hosp_safdarjung"),
    ("LNJP Hospital", 28.6403, 77.2380, "011-23232400", 40, "hosp_lnjp"),
    ("RML Hospital", 28.6256, 77.2000, "011-23404040", 35, ""),
    ("Max Super Speciality, Saket", 28.5275, 77.2120, "011-26515050", 30, ""),
]
POLICE = [  # name, lat, lng, phone, username
    ("Connaught Place Police Station", 28.6328, 77.2197, "011-23412345", "police_cp"),
    ("Tilak Marg Police Station", 28.6195, 77.2358, "011-23383838", "police_tilakmarg"),
    ("Sarojini Nagar Police Station", 28.5752, 77.1989, "011-24671234", "police_sarojini"),
    ("Kashmere Gate Police Station", 28.6672, 77.2290, "011-23866666", ""),
    ("Hauz Khas Police Station", 28.5494, 77.2001, "011-26852222", ""),
]


def user(username, password, role, first_name, email=None):
    u = User.objects.filter(username=username).first()
    if u:
        return u
    return User.objects.create_user(username=username, password=password, role=role, first_name=first_name,
                                    email=email or f"{username}@smartcrash.ai", phone="9000000000", is_approved=True)


class Command(BaseCommand):
    help = "Create demo accounts, services, cameras and sample accidents."

    def add_arguments(self, parser):
        parser.add_argument("--no-accidents", action="store_true", help="Skip sample accident records.")

    def handle(self, *args, **opts):
        SystemSetting.get()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@smartcrash.ai", "Admin@123", first_name="System Admin")

        for cid, name, lat, lng, road in CAMERAS:
            Camera.objects.get_or_create(camera_id=cid, defaults=dict(name=name, latitude=lat, longitude=lng,
                                                                     road_name=road))
        for name, lat, lng, phone, beds, uname in HOSPITALS:
            acct = user(uname, "Hospital@123", "hospital", name) if uname else None
            h, _ = Hospital.objects.get_or_create(name=name, defaults=dict(
                latitude=lat, longitude=lng, phone=phone, total_beds=beds, available_beds=beds // 2, account=acct))
            if not h.ambulances.exists():
                for i in range(1, 4):
                    Ambulance.objects.create(hospital=h, vehicle_number=f"DL-01-AMB-{h.id}0{i}",
                                             driver_name=f"Driver {i}", driver_phone="9000000001")
        for name, lat, lng, phone, uname in POLICE:
            acct = user(uname, "Police@123", "police", name) if uname else None
            PoliceStation.objects.get_or_create(name=name, defaults=dict(latitude=lat, longitude=lng, phone=phone,
                                                                         account=acct))

        if not opts["no_accidents"] and Accident.objects.count() == 0:
            for i in range(9):
                a = services.simulate_accident(low_confidence=(i == 8))
                if a.status == "verification_pending" or i < 2:
                    continue  # leave the first two as live "new" alerts
                to = "accepted" if i == 2 else "dispatched" if i == 3 else "resolved"
                for al in a.alerts.all():
                    al.status = to
                    if al.kind == "police" and to != "accepted":
                        al.team_name = "Patrol Team Alpha"
                    al.save()
                    services.add_event(a, f"{al.org_name} marked as {to} (demo data)", al.org_name)
                services.sync_status(a)
                if to == "resolved":
                    a.detected_at = timezone.now() - timedelta(days=(i - 3), hours=random.randint(1, 9))
                    a.save(update_fields=["detected_at"])

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("Logins:  admin / Admin@123   |   police_cp / Police@123   |   hosp_aiims / Hospital@123")
