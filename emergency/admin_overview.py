"""Admin-only overview: account statistics plus what the police / hospital users are doing.

Counts are computed with one grouped query per organisation type (instead of joining every organisation to
its alerts and aggregating three times), and the latest alert per organisation comes from a single ordered scan.
"""
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Alert, Hospital, PoliceStation, TimelineEvent
from .views import admin_only

User = get_user_model()
LIVE = ("pending", "accepted", "dispatched", "arrived")
ROLES = ("admin", "police", "hospital", "ambulance")


def _iso(dt):
    return dt.isoformat() if dt else None


def _status_counts(fk_name):
    """{organisation_id: {"live": n, "resolved": n, "rejected": n}} from one grouped query."""
    rows = (Alert.objects.filter(**{f"{fk_name}__isnull": False})
            .values(fk_name, "status").annotate(n=Count("id")))
    out = defaultdict(lambda: {"live": 0, "resolved": 0, "rejected": 0})
    for r in rows:
        bucket = out[r[fk_name]]
        if r["status"] in LIVE:
            bucket["live"] += r["n"]
        elif r["status"] == "resolved":
            bucket["resolved"] += r["n"]
        elif r["status"] == "rejected":
            bucket["rejected"] += r["n"]
    return out


def _latest_alerts(fk_name, org_ids):
    """{organisation_id: most recently updated Alert}."""
    wanted = set(org_ids)
    latest = {}
    if not wanted:
        return latest
    qs = (Alert.objects.filter(**{f"{fk_name}__in": wanted})
          .select_related("accident").order_by("-updated_at", "-id"))
    for al in qs.iterator():
        key = getattr(al, f"{fk_name}_id")
        if key not in latest:
            latest[key] = al
            if len(latest) == len(wanted):
                break
    return latest


def _org_rows(queryset, kind, fk_name):
    orgs = list(queryset.select_related("account").order_by("name"))
    counts = _status_counts(fk_name)
    latest = _latest_alerts(fk_name, [o.id for o in orgs])
    rows = []
    for o in orgs:
        c = counts.get(o.id) or {"live": 0, "resolved": 0, "rejected": 0}
        last = latest.get(o.id)
        rows.append({
            "id": o.id, "kind": kind, "name": o.name, "is_active": o.is_active,
            "account": o.account.username if o.account_id else "",
            "last_login": _iso(o.account.last_login) if o.account_id else None,
            "live": c["live"], "resolved": c["resolved"], "rejected": c["rejected"],
            "last_alert": {
                "accident": last.accident.accident_id,
                "accident_pk": last.accident_id,
                "status": last.status, "at": _iso(last.updated_at),
            } if last else None,
        })
    return rows


@api_view(["GET"])
@admin_only
def admin_overview(request):
    users = User.objects.all()
    by_role = {r: 0 for r in ROLES}
    for row in users.values("role").annotate(n=Count("id")):
        by_role[row["role"]] = row["n"]
    accounts = {
        "total": users.count(),
        "by_role": by_role,
        "inactive": users.filter(is_active=False).count(),
        "blocked": users.filter(is_approved=False).count(),
        "never_logged_in": users.filter(last_login__isnull=True).exclude(pk=request.user.pk).count(),
    }
    recent_logins = []
    recent = (users.filter(last_login__isnull=False)
              .select_related("police_station", "hospital").order_by("-last_login")[:8])
    for u in recent:
        recent_logins.append({
            "name": u.get_full_name() or u.username, "username": u.username, "role": u.role,
            "org": u.organization_name, "at": _iso(u.last_login),
        })
    activity = [{
        "message": t.message, "actor": t.actor, "at": _iso(t.created_at),
        "accident_pk": t.accident_id, "accident": t.accident.accident_id,
    } for t in TimelineEvent.objects.select_related("accident").order_by("-created_at", "-id")[:20]]
    return Response({
        "accounts": accounts,
        "police": _org_rows(PoliceStation.objects.all(), "police", "police_station"),
        "hospitals": _org_rows(Hospital.objects.all(), "hospital", "hospital"),
        "recent_logins": recent_logins,
        "activity": activity,
    })
