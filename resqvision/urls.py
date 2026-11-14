from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),    # auth, profile, OTP reset, user management
    path("api/", include("emergency.urls")),   # accidents, alerts, services, cameras, analytics, ingest
    path("", include("web.urls")),             # HTML / CSS / JS frontend
]

# MEDIA_ROOT is deliberately NOT served as public static files: accident evidence is delivered by
# /api/accidents/<id>/evidence/<snapshot|video>/, which checks that the user may see that accident.
# Do not expose MEDIA_ROOT through nginx/Apache either.
