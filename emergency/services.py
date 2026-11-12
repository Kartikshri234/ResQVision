"""Core business logic: accident pipeline, nearby-service selection, alerts and status tracking."""
import io
import math
import random

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import (Accident, Alert, Camera, Hospital, Notification, PoliceStation,
                     SystemSetting, TimelineEvent)

User = get_user_model()

# Higher = further along. Used to merge several alerts into one status.
RANK = {"rejected": 0, "pending": 1, "accepted": 2, "dispatched": 3, "arrived": 4, "resolved": 5}

SCENARIOS = [  # (accident type, vehicles, AI severity estimate)
    ("Car collision", "Car, Car", "medium"),
    ("Motorcycle accident", "Motorcycle, Car", "high"),
    ("Multiple vehicle collision", "Car, Truck, Car", "high"),
    ("Vehicle overturning", "Truck", "high"),
    ("Vehicle and pedestrian collision", "Car, Pedestrian", "high"),
    ("Car collision", "Car, Auto-rickshaw", "low"),
]


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------- timeline / notifications ----------
def add_event(accident, message, actor="System", when=None):
    TimelineEvent.objects.create(accident=accident, message=message[:255], actor=actor[:100],
                                 created_at=when or timezone.now())


def notify(user, title, message, accident=None):
    if user:
        Notification.objects.create(user=user, title=title[:150], message=message[:255], accident=accident)


def notify_admins(title, message, accident=None):
    for u in User.objects.filter(role="admin", is_active=True):
        notify(u, title, message, accident)


# ---------- service selection ----------
def nearby(model, lat, lng, limit, radius, only_accepting=False, exclude_ids=()):
    qs = model.objects.filter(is_active=True).exclude(pk__in=exclude_ids)
    if only_accepting:
        qs = qs.filter(accepting_emergencies=True)
    rows = sorted(((haversine(lat, lng, o.latitude, o.longitude), o) for o in qs), key=lambda r: r[0])
    within = [r for r in rows if r[0] <= radius][:limit]
    if not within and rows:  # never leave an accident un-notified: fall back to the single nearest service
        within = rows[:1]
    return within


def dispatch_alerts(accident):
    cfg = SystemSetting.get()
    created = []
    for d, ps in nearby(PoliceStation, accident.latitude, accident.longitude, cfg.max_police, cfg.notify_radius_km):
        created.append(Alert.objects.create(accident=accident, kind="police", police_station=ps,
                                            distance_km=round(d, 1)))
    for d, h in nearby(Hospital, accident.latitude, accident.longitude, cfg.max_hospitals,
                       cfg.notify_radius_km, only_accepting=True):
        created.append(Alert.objects.create(accident=accident, kind="hospital", hospital=h,
                                            distance_km=round(d, 1)))
    accident.status = "alert_sent"
    accident.save(update_fields=["status"])
    for al in created:
        notify(al.org.account, f"🚨 New accident {accident.accident_id}",
               f"{accident.get_severity_display()} severity · {accident.location or 'Unknown location'} · "
               f"{al.distance_km} km away", accident)
    names = ", ".join(f"{al.org_name} ({al.kind})" for al in created) or "no registered services found"
    add_event(accident, f"Emergency alerts sent to: {names}")
    notify_admins(f"Alerts sent for {accident.accident_id}", f"{len(created)} service(s) notified.", accident)
    return created


def escalate(accident, kind):
    """If every service of one kind rejected, route the request to the next nearest one."""
    alerts = accident.alerts.filter(kind=kind)
    if alerts.exclude(status="rejected").exists():
        return None
    model = PoliceStation if kind == "police" else Hospital
    used = [(a.police_station_id if kind == "police" else a.hospital_id) for a in alerts]
    rows = nearby(model, accident.latitude, accident.longitude, 1, 10 ** 6,
                  only_accepting=(kind == "hospital"), exclude_ids=used)
    if not rows:
        add_event(accident, f"No other available {kind} service could be found.")
        notify_admins(f"Action needed: {accident.accident_id}", f"All {kind} services rejected or unavailable.", accident)
        return None
    d, org = rows[0]
    al = Alert.objects.create(accident=accident, kind=kind, distance_km=round(d, 1),
                              **{"police_station" if kind == "police" else "hospital": org})
    add_event(accident, f"Request re-routed to {org.name} ({d:.1f} km)")
    notify(org.account, f"🚨 New accident {accident.accident_id}",
           f"{accident.get_severity_display()} severity · {accident.location or 'Unknown location'} · {al.distance_km} km away",
           accident)
    return al


# ---------- pipeline ----------
def process_accident(accident):
    """Called for every accident the AI service reports."""
    cfg = SystemSetting.get()
    cam = accident.camera.camera_id if accident.camera else "manual report"
    add_event(accident, f"Accident detected by {cam} (confidence {round(accident.confidence * 100)}%)", "AI Service",
              accident.detected_at)
    if accident.confidence < cfg.min_confidence or not cfg.auto_alert:
        accident.status = "verification_pending"
        accident.save(update_fields=["status"])
        add_event(accident, "Confidence below the auto-alert threshold: waiting for admin verification")
        notify_admins(f"Verify {accident.accident_id}", "Detection needs manual verification before alerts are sent.",
                      accident)
    else:
        accident.status = "confirmed"
        accident.save(update_fields=["status"])
        add_event(accident, "Accident verified automatically")
        dispatch_alerts(accident)
    return accident


def confirm_accident(accident, actor="Admin"):
    accident.status = "confirmed"
    accident.save(update_fields=["status"])
    add_event(accident, "Accident confirmed manually", actor)
    return dispatch_alerts(accident)


def sync_status(accident):
    if accident.status in ("closed", "verification_pending", "detected"):
        return
    live = list(accident.alerts.exclude(status="rejected").values_list("status", flat=True))
    if not live:
        new = "alert_sent"
    elif all(s == "resolved" for s in live):
        new = "resolved"
    else:
        new = {1: "alert_sent", 2: "accepted", 3: "team_dispatched", 4: "arrived", 5: "arrived"}[
            max(RANK[s] for s in live)]
    if new != accident.status:
        accident.status = new
        accident.save(update_fields=["status"])
        if new == "resolved":
            add_event(accident, "All responding services have resolved the incident")


# ---------- demo helpers ----------
def make_demo_snapshot(accident, kind=""):
    """Draw a simple placeholder 'CCTV frame' so simulated incidents have visible evidence."""
    from PIL import Image, ImageDraw
    w, h = 640, 360
    img = Image.new("RGB", (w, h), (74, 85, 104))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 110, w, 270], fill=(45, 50, 60))
    for x in range(0, w, 70):
        d.rectangle([x, 188, x + 36, 192], fill=(235, 235, 235))
    cx, cy = random.randint(260, 380), 190
    d.rectangle([cx - 86, cy - 16, cx - 8, cy + 18], fill=(37, 99, 235))
    d.rectangle([cx - 64, cy - 10, cx - 30, cy + 8], fill=(147, 197, 253))
    d.polygon([(cx + 4, cy - 36), (cx + 80, cy - 12), (cx + 70, cy + 30), (cx - 4, cy + 8)], fill=(220, 38, 38))
    pts = []
    for i in range(16):
        ang = math.pi * 2 * i / 16
        rad = 38 if i % 2 == 0 else 16
        pts.append((cx + rad * math.cos(ang), cy - 6 + rad * math.sin(ang)))
    d.polygon(pts, fill=(251, 146, 60), outline=(254, 240, 138))
    d.rectangle([0, 0, w, 22], fill=(0, 0, 0))
    cam = accident.camera.camera_id if accident.camera else "CAM"
    stamp = timezone.localtime(accident.detected_at).strftime("%d-%m-%Y %H:%M:%S")
    d.text((8, 6), f"{cam}   {stamp}   SIMULATED FRAME", fill=(255, 255, 255))
    d.rectangle([0, h - 22, w, h], fill=(0, 0, 0))
    d.text((8, h - 17), f"{accident.accident_id}  {kind}", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return ContentFile(buf.getvalue())


def simulate_accident(camera=None, low_confidence=False):
    if camera is None:
        cams = list(Camera.objects.filter(is_active=True))
        if not cams:
            raise ValueError("Add at least one active camera before simulating an accident.")
        camera = random.choice(cams)
    kind, vehicles, sev = random.choice(SCENARIOS)
    conf = round(random.uniform(0.45, 0.62), 2) if low_confidence else round(random.uniform(0.80, 0.97), 2)
    a = Accident.objects.create(
        camera=camera, latitude=camera.latitude, longitude=camera.longitude,
        location=camera.road_name or camera.name, accident_type=kind, confidence=conf, severity=sev,
        vehicles=vehicles, people_count=random.randint(1, 5), is_simulated=True)
    a.snapshot.save(f"{a.accident_id}.png", make_demo_snapshot(a, kind), save=True)
    process_accident(a)
    return a
