"""REST API for ResQVision. Every endpoint is role-aware: admins see everything,
police and hospital users only see accidents their organisation was alerted about."""
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.views import user_json

from . import services
from .models import (Accident, Alert, Ambulance, Camera, Hospital, Notification, PoliceStation,
                     SystemSetting)

User = get_user_model()
ACTIVE = ["confirmed", "alert_sent", "accepted", "team_dispatched", "arrived"]
DONE = ["resolved", "closed"]


# ---------------------------------------------------------------- helpers
def err(msg, code=400):
    return Response({"error": msg}, status=code)


def admin_only(fn):
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if request.user.role != "admin":
            return err("Admin access required.", 403)
        return fn(request, *args, **kwargs)
    return wrapper


def my_org(user):
    if user.role == "police":
        return getattr(user, "police_profile", None)
    if user.role == "hospital":
        return getattr(user, "hospital_profile", None)
    return None


def base_qs():
    return Accident.objects.select_related("camera").prefetch_related(
        "alerts__police_station", "alerts__hospital", "alerts__ambulance", "timeline")


def scoped(user):
    qs = base_qs()
    if user.role == "admin":
        return qs
    org = my_org(user)
    if not org:
        return qs.none()
    field = "alerts__police_station" if user.role == "police" else "alerts__hospital"
    return qs.filter(**{field: org})


def kind_status(alerts, kind):
    sts = [a.status for a in alerts if a.kind == kind]
    if not sts:
        return "none"
    live = [s for s in sts if s != "rejected"]
    if not live:
        return "rejected"
    return max(live, key=lambda s: services.RANK[s])


def alert_json(al):
    return {
        "id": al.id, "kind": al.kind, "org": al.org_name, "distance_km": al.distance_km,
        "status": al.status, "reject_reason": al.reject_reason, "team_name": al.team_name,
        "ambulance": al.ambulance.vehicle_number if al.ambulance_id else "",
        "updated_at": al.updated_at.isoformat(),
    }


def accident_json(a, user, detail=False):
    alerts = list(a.alerts.all())
    org = my_org(user)
    mine = None
    for al in alerts:
        if org and ((user.role == "police" and al.police_station_id == org.id) or
                    (user.role == "hospital" and al.hospital_id == org.id)):
            mine = alert_json(al)
    d = {
        "id": a.id, "accident_id": a.accident_id, "detected_at": a.detected_at.isoformat(),
        "latitude": a.latitude, "longitude": a.longitude, "location": a.location,
        "camera": a.camera.camera_id if a.camera else "", "camera_name": a.camera.name if a.camera else "",
        "accident_type": a.accident_type, "confidence": round(a.confidence * 100),
        "severity": a.severity, "vehicles": a.vehicles, "people_count": a.people_count,
        "snapshot": a.snapshot.url if a.snapshot else "", "video": a.video.url if a.video else "",
        "status": a.status, "status_label": a.get_status_display(), "is_simulated": a.is_simulated,
        "police_status": kind_status(alerts, "police"), "hospital_status": kind_status(alerts, "hospital"),
        "my_alert": mine,
    }
    if detail:
        d["timeline"] = [{"message": t.message, "actor": t.actor, "at": t.created_at.isoformat()}
                         for t in a.timeline.all()]
        if user.role == "admin":
            d["alerts"] = [alert_json(x) for x in alerts]
    return d


def detail(pk, user):
    return accident_json(get_object_or_404(base_qs(), pk=pk), user, True)


def org_json(o, kind):
    d = {"id": o.id, "kind": kind, "name": o.name, "address": o.address, "latitude": o.latitude,
         "longitude": o.longitude, "phone": o.phone, "is_active": o.is_active,
         "account": o.account.username if o.account_id else ""}
    if kind == "hospital":
        d.update(accepting_emergencies=o.accepting_emergencies, total_beds=o.total_beds,
                 available_beds=o.available_beds, ambulances=o.ambulances.count(),
                 ambulances_available=o.ambulances.filter(status="available").count())
    return d


def camera_json(c):
    return {"id": c.id, "camera_id": c.camera_id, "name": c.name, "latitude": c.latitude,
            "longitude": c.longitude, "road_name": c.road_name, "stream_url": c.stream_url,
            "is_active": c.is_active}


# ---------------------------------------------------------------- dashboard / map
@api_view(["GET"])
def dashboard(request):
    u = request.user
    qs = scoped(u).distinct()
    if u.role == "admin":
        now = timezone.localtime()
        daily = [{"date": (now - timedelta(days=i)).strftime("%d %b"),
                  "count": Accident.objects.filter(detected_at__date=(now - timedelta(days=i)).date()).count()}
                 for i in range(6, -1, -1)]
        return Response({
            "role": "admin",
            "total": Accident.objects.count(),
            "active": Accident.objects.filter(status__in=ACTIVE).count(),
            "pending_responses": Alert.objects.filter(status="pending").exclude(accident__status="closed").count(),
            "resolved": Accident.objects.filter(status__in=DONE).count(),
            "verification_pending": Accident.objects.filter(status="verification_pending").count(),
            "hospitals": Hospital.objects.filter(is_active=True).count(),
            "police": PoliceStation.objects.filter(is_active=True).count(),
            "cameras": Camera.objects.filter(is_active=True).count(),
            "daily": daily,
            "recent": [accident_json(a, u) for a in qs[:6]],
        })
    org = my_org(u)
    alerts = Alert.objects.none()
    if org:
        alerts = Alert.objects.filter(**{"police_station" if u.role == "police" else "hospital": org})
    data = {
        "role": u.role, "org": org.name if org else "",
        "new": alerts.filter(status="pending").exclude(accident__status="closed").count(),
        "active": alerts.filter(status__in=["accepted", "dispatched", "arrived"]).count(),
        "resolved": alerts.filter(status="resolved").count(),
        "rejected": alerts.filter(status="rejected").count(),
        "recent": [accident_json(a, u) for a in qs[:6]],
    }
    if u.role == "hospital" and org:
        data["hospital"] = org_json(org, "hospital")
    return Response(data)


@api_view(["GET"])
def map_data(request):
    u = request.user
    wanted = ACTIVE + (["verification_pending"] if u.role == "admin" else [])
    accs = scoped(u).filter(status__in=wanted).distinct()
    org = my_org(u)
    out = {
        "accidents": [{"id": a.id, "accident_id": a.accident_id, "latitude": a.latitude,
                       "longitude": a.longitude, "severity": a.severity, "status": a.status,
                       "status_label": a.get_status_display(), "location": a.location} for a in accs],
        "hospitals": [org_json(h, "hospital") for h in Hospital.objects.filter(is_active=True)],
        "police": [org_json(p, "police") for p in PoliceStation.objects.filter(is_active=True)],
        "cameras": [camera_json(c) for c in Camera.objects.filter(is_active=True)] if u.role == "admin" else [],
        "me": {"kind": u.role, "id": org.id} if org else None,
    }
    return Response(out)


# ---------------------------------------------------------------- accidents
@api_view(["GET"])
def accidents(request):
    u = request.user
    qs = scoped(u)
    view = request.query_params.get("view", "all")
    if u.role == "admin":
        if view == "new":
            qs = qs.filter(status="verification_pending")
        elif view == "active":
            qs = qs.filter(status__in=ACTIVE)
        elif view == "history":
            qs = qs.filter(status__in=DONE)
    elif view in ("new", "active", "history"):
        org = my_org(u)
        field = "alerts__police_station" if u.role == "police" else "alerts__hospital"
        sts = {"new": ["pending"], "active": ["accepted", "dispatched", "arrived"],
               "history": ["resolved", "rejected"]}[view]
        qs = qs.filter(**{field: org, "alerts__status__in": sts})
        if view == "new":
            qs = qs.exclude(status="closed")
    q = request.query_params.get("q", "").strip()
    if q:
        qs = qs.filter(Q(accident_id__icontains=q) | Q(location__icontains=q) | Q(accident_type__icontains=q))
    sev = request.query_params.get("severity")
    if sev in ("low", "medium", "high"):
        qs = qs.filter(severity=sev)
    return Response([accident_json(a, u) for a in qs.distinct()[:200]])


@api_view(["GET"])
def accident_detail(request, pk):
    a = get_object_or_404(scoped(request.user).distinct(), pk=pk)
    return Response(accident_json(a, request.user, True))


@api_view(["POST"])
@admin_only
def accident_confirm(request, pk):
    a = get_object_or_404(Accident, pk=pk)
    if a.status not in ("verification_pending", "detected"):
        return err("This accident is already confirmed.")
    services.confirm_accident(a, actor=request.user.get_full_name() or request.user.username)
    return Response(detail(pk, request.user))


@api_view(["POST"])
@admin_only
def accident_close(request, pk):
    a = get_object_or_404(Accident, pk=pk)
    if a.status == "closed":
        return err("This incident is already closed.")
    reason = (request.data.get("reason") or "").strip()
    actor = request.user.get_full_name() or request.user.username
    open_alerts = list(a.alerts.exclude(status__in=["resolved", "rejected"]))
    a.status = "closed"
    a.save(update_fields=["status"])
    for al in open_alerts:
        al.status = "resolved"
        al.save()
        if al.ambulance_id:
            Ambulance.objects.filter(pk=al.ambulance_id).update(status="available")
        if al.org:
            services.notify(al.org.account, f"{a.accident_id} closed", reason or "Closed by admin", a)
    services.add_event(a, "Incident closed" + (f": {reason}" if reason else ""), actor)
    return Response(detail(pk, request.user))


@api_view(["POST"])
def alert_respond(request, pk):
    al = get_object_or_404(Alert.objects.select_related("accident", "police_station", "hospital", "ambulance"), pk=pk)
    u, org, acc = request.user, al.org, al.accident
    if not (u.role == "admin" or (org and org.account_id == u.id)):
        return err("This alert is not assigned to you.", 403)
    if acc.status == "closed":
        return err("This incident is closed.")
    d = request.data
    action, s = d.get("action"), al.status
    who = (org.name if org else "Admin") + (" (via admin)" if u.role == "admin" else "")
    if action == "accept" and s == "pending":
        al.status = "accepted"
        msg = f"{who} accepted the incident"
    elif action == "reject" and s == "pending":
        reason = (d.get("reason") or "").strip()
        if not reason:
            return err("Please give a reason for rejecting.")
        al.status, al.reject_reason = "rejected", reason[:255]
        msg = f"{who} rejected the incident: {reason}"
    elif action == "dispatch" and s == "accepted":
        if al.kind == "police":
            team = (d.get("team_name") or "").strip()
            if not team:
                return err("Enter the response team name.")
            al.team_name = team[:100]
            msg = f"{who} dispatched {team} to the location"
        else:
            avail = Ambulance.objects.filter(hospital=al.hospital, status="available")
            amb = None
            if d.get("ambulance_id"):
                amb = avail.filter(pk=d["ambulance_id"]).first()
                if not amb:
                    return err("That ambulance is not available.")
            elif avail.exists():
                return err("Select an ambulance to assign.")
            if amb:
                amb.status = "dispatched"
                amb.save()
                al.ambulance = amb
            msg = (f"{who} dispatched ambulance {amb.vehicle_number}" if amb
                   else f"{who} dispatched emergency staff")
        al.status = "dispatched"
    elif action == "arrive" and s == "dispatched":
        al.status = "arrived"
        msg = f"{who}: responders arrived at the scene"
    elif action == "resolve" and s in ("dispatched", "arrived"):
        al.status = "resolved"
        msg = f"{who} marked the response as completed"
        if al.ambulance_id:
            Ambulance.objects.filter(pk=al.ambulance_id).update(status="available")
    else:
        return err("That action isn't available for the current status.")
    al.save()
    services.add_event(acc, msg, who)
    if action == "reject":
        services.escalate(acc, al.kind)
    services.sync_status(acc)
    services.notify_admins(f"{acc.accident_id}: {al.kind} update", msg, acc)
    return Response(detail(acc.pk, u))


# ---------------------------------------------------------------- hospitals / police stations
def _apply_org(o, kind, d):
    for f in ("name", "address", "phone"):
        if f in d:
            setattr(o, f, str(d[f] or "").strip())
    for f in ("latitude", "longitude"):
        if f in d:
            setattr(o, f, float(d[f]))
    if "is_active" in d:
        o.is_active = bool(d["is_active"])
    if kind == "hospital":
        for f in ("total_beds", "available_beds"):
            if f in d:
                setattr(o, f, max(0, int(d[f])))
        if "accepting_emergencies" in d:
            o.accepting_emergencies = bool(d["accepting_emergencies"])
    if "account_username" in d:
        name = (d["account_username"] or "").strip()
        if not name:
            o.account = None
        else:
            user = User.objects.filter(username__iexact=name, role=kind).first()
            if not user:
                raise ValueError(f"No {kind} user named '{name}'.")
            if type(o).objects.filter(account=user).exclude(pk=o.pk).exists():
                raise ValueError("That user is already linked to another organisation.")
            o.account = user


def _org_list(request, Model, kind):
    if request.method == "POST":
        if request.user.role != "admin":
            return err("Admin access required.", 403)
        d = request.data
        if not str(d.get("name", "")).strip():
            return err("Name is required.")
        if d.get("latitude") in (None, "") or d.get("longitude") in (None, ""):
            return err("Latitude and longitude are required.")
        o = Model(latitude=0, longitude=0)
        try:
            _apply_org(o, kind, d)
        except (ValueError, TypeError) as e:
            return err(str(e) or "Invalid value.")
        o.save()
        return Response(org_json(o, kind), status=201)
    qs = Model.objects.all() if request.user.role == "admin" else Model.objects.filter(is_active=True)
    return Response([org_json(o, kind) for o in qs.order_by("name")])


def _org_item(request, pk, Model, kind):
    o = get_object_or_404(Model, pk=pk)
    if request.method == "GET":
        return Response(org_json(o, kind))
    if request.user.role != "admin":
        return err("Admin access required.", 403)
    if request.method == "DELETE":
        o.delete()
        return Response({"ok": True})
    try:
        _apply_org(o, kind, request.data)
    except (ValueError, TypeError) as e:
        return err(str(e) or "Invalid value.")
    o.save()
    return Response(org_json(o, kind))


@api_view(["GET", "POST"])
def hospitals(request):
    return _org_list(request, Hospital, "hospital")


@api_view(["GET", "PATCH", "DELETE"])
def hospital_item(request, pk):
    return _org_item(request, pk, Hospital, "hospital")


@api_view(["GET", "POST"])
def police_stations(request):
    return _org_list(request, PoliceStation, "police")


@api_view(["GET", "PATCH", "DELETE"])
def police_item(request, pk):
    return _org_item(request, pk, PoliceStation, "police")


@api_view(["GET", "PATCH"])
def hospital_me(request):
    h = my_org(request.user) if request.user.role == "hospital" else None
    if not h:
        return err("No hospital is linked to this account.", 404)
    if request.method == "PATCH":
        d = request.data
        try:
            if "accepting_emergencies" in d:
                h.accepting_emergencies = bool(d["accepting_emergencies"])
            if "total_beds" in d:
                h.total_beds = max(0, int(d["total_beds"]))
            if "available_beds" in d:
                h.available_beds = max(0, int(d["available_beds"]))
        except (TypeError, ValueError):
            return err("Bed counts must be whole numbers.")
        if h.available_beds > h.total_beds:
            return err("Available beds cannot exceed total beds.")
        h.save()
    return Response(org_json(h, "hospital"))


# ---------------------------------------------------------------- ambulances
def _amb_json(a):
    return {"id": a.id, "hospital": a.hospital.name, "vehicle_number": a.vehicle_number,
            "driver_name": a.driver_name, "driver_phone": a.driver_phone, "status": a.status}


def _hospital_for(request):
    if request.user.role == "hospital":
        return my_org(request.user)
    if request.user.role == "admin":
        hid = request.data.get("hospital") or request.query_params.get("hospital")
        return Hospital.objects.filter(pk=hid).first() if hid else None
    return None


@api_view(["GET", "POST"])
def ambulances(request):
    if request.user.role not in ("hospital", "admin"):
        return err("Not allowed.", 403)
    h = _hospital_for(request)
    if request.method == "POST":
        if not h:
            return err("No hospital is linked to this account.")
        vehicle = (request.data.get("vehicle_number") or "").strip()
        if not vehicle:
            return err("Vehicle number is required.")
        a = Ambulance.objects.create(hospital=h, vehicle_number=vehicle[:30],
                                     driver_name=request.data.get("driver_name", "")[:100],
                                     driver_phone=request.data.get("driver_phone", "")[:20])
        return Response(_amb_json(a), status=201)
    qs = Ambulance.objects.select_related("hospital")
    qs = qs.filter(hospital=h) if h else (qs if request.user.role == "admin" else qs.none())
    return Response([_amb_json(a) for a in qs.order_by("vehicle_number")])


@api_view(["PATCH", "DELETE"])
def ambulance_item(request, pk):
    a = get_object_or_404(Ambulance.objects.select_related("hospital"), pk=pk)
    if not (request.user.role == "admin" or a.hospital.account_id == request.user.id):
        return err("Not allowed.", 403)
    if request.method == "DELETE":
        a.delete()
        return Response({"ok": True})
    d = request.data
    if d.get("status") in ("available", "dispatched", "maintenance"):
        a.status = d["status"]
    for f, n in (("vehicle_number", 30), ("driver_name", 100), ("driver_phone", 20)):
        if f in d:
            setattr(a, f, str(d[f])[:n])
    a.save()
    return Response(_amb_json(a))


# ---------------------------------------------------------------- cameras
def _apply_camera(c, d):
    for f in ("camera_id", "name", "road_name", "stream_url"):
        if f in d:
            setattr(c, f, str(d[f] or "").strip())
    for f in ("latitude", "longitude"):
        if f in d:
            setattr(c, f, float(d[f]))
    if "is_active" in d:
        c.is_active = bool(d["is_active"])


@api_view(["GET", "POST"])
@admin_only
def cameras(request):
    if request.method == "POST":
        d = request.data
        if not str(d.get("camera_id", "")).strip() or not str(d.get("name", "")).strip():
            return err("Camera ID and name are required.")
        if Camera.objects.filter(camera_id=str(d["camera_id"]).strip()).exists():
            return err("A camera with that ID already exists.")
        c = Camera(latitude=0, longitude=0)
        try:
            _apply_camera(c, d)
        except (ValueError, TypeError):
            return err("Latitude and longitude must be numbers.")
        c.save()
        return Response(camera_json(c), status=201)
    return Response([camera_json(c) for c in Camera.objects.all().order_by("camera_id")])


@api_view(["PATCH", "DELETE"])
@admin_only
def camera_item(request, pk):
    c = get_object_or_404(Camera, pk=pk)
    if request.method == "DELETE":
        c.delete()
        return Response({"ok": True})
    try:
        _apply_camera(c, request.data)
    except (ValueError, TypeError):
        return err("Latitude and longitude must be numbers.")
    c.save()
    return Response(camera_json(c))


# ---------------------------------------------------------------- users
@api_view(["GET", "POST"])
@admin_only
def users(request):
    if request.method == "POST":
        d = request.data
        username, pw, role = (d.get("username") or "").strip(), d.get("password") or "", d.get("role")
        if role not in dict(User.ROLES):
            return err("Choose a valid role.")
        if not username or len(pw) < 8:
            return err("A username and a password of at least 8 characters are required.")
        if User.objects.filter(username__iexact=username).exists():
            return err("That username is already taken.")
        u = User.objects.create_user(username=username, email=d.get("email", ""), password=pw, role=role,
                                     first_name=d.get("first_name", ""), phone=d.get("phone", ""))
        return Response(user_json(u), status=201)
    qs = User.objects.all().order_by("-date_joined")
    q = request.query_params.get("q", "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
    role = request.query_params.get("role")
    if role in dict(User.ROLES):
        qs = qs.filter(role=role)
    return Response([user_json(u) for u in qs[:300]])


@api_view(["PATCH", "DELETE"])
@admin_only
def user_item(request, pk):
    u = get_object_or_404(User, pk=pk)
    me = request.user
    if request.method == "DELETE":
        if u.id == me.id:
            return err("You cannot delete your own account.")
        u.delete()
        return Response({"ok": True})
    d = request.data
    if u.id == me.id and (d.get("is_active") is False or d.get("role", "admin") != "admin"):
        return err("You cannot deactivate or demote your own account.")
    for f in ("first_name", "last_name", "email", "phone"):
        if f in d:
            setattr(u, f, d[f])
    if d.get("role") in dict(User.ROLES):
        u.role = d["role"]
    if "is_active" in d:
        u.is_active = bool(d["is_active"])
    if d.get("password"):
        if len(d["password"]) < 8:
            return err("Password must be at least 8 characters.")
        u.set_password(d["password"])
    u.save()
    return Response(user_json(u))


# ---------------------------------------------------------------- notifications
def _notif_json(n):
    return {"id": n.id, "title": n.title, "message": n.message, "accident_id": n.accident_id,
            "is_read": n.is_read, "created_at": n.created_at.isoformat()}


@api_view(["GET"])
def notifications(request):
    qs = Notification.objects.filter(user=request.user)
    return Response({"items": [_notif_json(n) for n in qs[:100]], "unread": qs.filter(is_read=False).count()})


@api_view(["POST"])
def notifications_read(request, pk=None):
    qs = Notification.objects.filter(user=request.user)
    if pk:
        qs = qs.filter(pk=pk)
    qs.update(is_read=True)
    return Response({"ok": True})


# ---------------------------------------------------------------- analytics & settings (admin)
@api_view(["GET"])
@admin_only
def analytics(request):
    qs = Accident.objects.all()
    now = timezone.localtime()
    daily = [{"date": (now - timedelta(days=i)).strftime("%d %b"),
              "count": qs.filter(detected_at__date=(now - timedelta(days=i)).date()).count()}
             for i in range(13, -1, -1)]
    hours = [0] * 24
    for dt in qs.values_list("detected_at", flat=True):
        hours[timezone.localtime(dt).hour] += 1
    alerts = Alert.objects.all()
    total_alerts = alerts.count()
    responded = alerts.exclude(status__in=["pending", "rejected"]).count()
    return Response({
        "daily": daily,
        "hours": hours,
        "severity": {r["severity"]: r["n"] for r in qs.values("severity").annotate(n=Count("id"))},
        "types": list(qs.exclude(accident_type="").values("accident_type").annotate(n=Count("id")).order_by("-n")),
        "status": {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))},
        "alerts": {"total": total_alerts, "responded": responded,
                   "rejected": alerts.filter(status="rejected").count(),
                   "acceptance_rate": round(responded * 100 / total_alerts) if total_alerts else 0},
        "ai": {"detections": qs.count(),
               "avg_confidence": round((qs.aggregate(a=Avg("confidence"))["a"] or 0) * 100, 1),
               "auto_verified": qs.exclude(status__in=["verification_pending", "detected"]).count(),
               "pending_verification": qs.filter(status="verification_pending").count(),
               "simulated": qs.filter(is_simulated=True).count(),
               "cameras": Camera.objects.filter(is_active=True).count()},
    })


@api_view(["GET", "PATCH"])
@admin_only
def system_settings(request):
    s = SystemSetting.get()
    if request.method == "PATCH":
        d = request.data
        try:
            if "notify_radius_km" in d:
                s.notify_radius_km = max(1.0, float(d["notify_radius_km"]))
            if "max_police" in d:
                s.max_police = max(1, int(d["max_police"]))
            if "max_hospitals" in d:
                s.max_hospitals = max(1, int(d["max_hospitals"]))
            if "min_confidence" in d:
                c = float(d["min_confidence"])
                s.min_confidence = c / 100 if c > 1 else c
            if "auto_alert" in d:
                s.auto_alert = bool(d["auto_alert"])
        except (TypeError, ValueError):
            return err("Please enter valid numbers.")
        if not 0 <= s.min_confidence <= 1:
            return err("Confidence threshold must be between 0 and 100%.")
        s.save()
    return Response({"notify_radius_km": s.notify_radius_km, "max_police": s.max_police,
                     "max_hospitals": s.max_hospitals, "min_confidence": round(s.min_confidence * 100),
                     "auto_alert": s.auto_alert})


@api_view(["POST"])
@admin_only
def simulate(request):
    cam = Camera.objects.filter(pk=request.data.get("camera_id")).first() if request.data.get("camera_id") else None
    try:
        a = services.simulate_accident(camera=cam, low_confidence=bool(request.data.get("low_confidence")))
    except ValueError as e:
        return err(str(e))
    return Response(detail(a.pk, request.user), status=201)


# ---------------------------------------------------------------- AI service ingest
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def ingest(request):
    """Verified accident events from the Python AI service (multipart or JSON, X-API-Key header)."""
    if request.headers.get("X-API-Key") != settings.AI_SERVICE_API_KEY:
        return err("Invalid API key.", 401)
    d = request.data
    cam = Camera.objects.filter(camera_id=d.get("camera_id")).first()
    try:
        lat = float(d.get("latitude") or (cam.latitude if cam else "x"))
        lng = float(d.get("longitude") or (cam.longitude if cam else "x"))
        conf = float(d.get("confidence", 0))
        people = int(d.get("people_count") or 0)
    except (TypeError, ValueError):
        return err("Unknown camera_id and no valid latitude/longitude; confidence must be a number.")
    conf = min(max(conf / 100 if conf > 1 else conf, 0.0), 1.0)
    when = parse_datetime(d.get("detected_at") or "") or timezone.now()
    if cam:  # suppress duplicate reports of the same crash from one camera
        dup = Accident.objects.filter(camera=cam, detected_at__gte=when - timedelta(minutes=2)).exclude(
            status="closed").first()
        if dup:
            return Response({"duplicate": True, "accident_id": dup.accident_id})
    sev = d.get("severity") if d.get("severity") in ("low", "medium", "high") else "medium"
    a = Accident.objects.create(
        camera=cam, latitude=lat, longitude=lng, detected_at=when, confidence=conf, severity=sev,
        location=d.get("location") or (cam.road_name or cam.name if cam else ""),
        accident_type=d.get("accident_type", "")[:60], vehicles=d.get("vehicles", "")[:200], people_count=people,
        snapshot=request.FILES.get("snapshot"), video=request.FILES.get("video"))
    services.process_accident(a)
    return Response({"accident_id": a.accident_id, "status": a.status}, status=201)
