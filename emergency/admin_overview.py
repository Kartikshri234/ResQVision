"""Admin-only overview: account statistics plus what the police / hospital users are doing."""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework.decorators import api_view

from .models import Alert, Hospital, PoliceStation, TimelineEvent
from .views import admin_only

User = get_user_model()
LIVE = ["pending", "accepted", "dispatched", "arrived"]


def _iso(dt):
    return dt.isoformat() if dt else None


def _org_rows(queryset, kind, fk):
    rows = []
    stats = queryset.select_related("account").annotate(
        live=Count("alert", filter=Q(alert__status__in=LIVE)),
        resolved=Count("alert", filter=Q(alert__status="resolved")),
        rejected=Count("alert", filter=Q(alert__status="rejected")),
    ).order_by("name")
    for o in stats:
        last = (Alert.objects.filter(**{fk: o}).select_related("accident").order_by("-updated_at").first())
        rows.append({
            "id": o.id, "kind": kind, "name": o.name, "is_active": o.is_active,
            "account": o.account.username if o.account_id else "",
            "last_login": _iso(o.account.last_login) if o.account_id else None,
            "live": o.live, "resolved": o.resolved, "rejected": o.rejected,
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
    by_role = {r: users.filter(role=r).count() for r in ("admin", "police", "hospital", "ambulance")}
    accounts = {
        "total": users.count(),
        "by_role": by_role,
        "inactive": users.filter(is_active=False).count(),
        "blocked": users.filter(is_approved=False).count(),
        "never_logged_in": users.filter(last_login__isnull=True).exclude(pk=request.user.pk).count(),
    }
    recent_logins = []
    for u in users.filter(last_login__isnull=False).select_related("police_station", "hospital").order_by("-last_login")[:8]:
        recent_logins.append({
            "name": u.get_full_name() or u.username, "username": u.username, "role": u.role,
            "org": u.organization_name, "at": _iso(u.last_login),
        })
    activity = [{
        "message": t.message, "actor": t.actor, "at": _iso(t.created_at),
        "accident_pk": t.accident_id, "accident": t.accident.accident_id,
    } for t in TimelineEvent.objects.select_related("accident").order_by("-created_at")[:20]]
    return Response({
        "accounts": accounts,
        "police": _org_rows(PoliceStation.objects.all(), "police", "police_station"),
        "hospitals": _org_rows(Hospital.objects.all(), "hospital", "hospital"),
        "recent_logins": recent_logins,
        "activity": activity,
    })
