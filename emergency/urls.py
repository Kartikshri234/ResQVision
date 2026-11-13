from django.urls import path

from . import views as v
from .admin_overview import admin_overview

urlpatterns = [
    path("admin/overview/", admin_overview),
    path("dashboard/", v.dashboard),
    path("map/", v.map_data),
    path("accidents/", v.accidents),
    path("accidents/<int:pk>/", v.accident_detail),
    path("accidents/<int:pk>/confirm/", v.accident_confirm),
    path("accidents/<int:pk>/close/", v.accident_close),
    path("alerts/<int:pk>/respond/", v.alert_respond),
    path("hospitals/", v.hospitals),
    path("hospitals/<int:pk>/", v.hospital_item),
    path("police-stations/", v.police_stations),
    path("police-stations/<int:pk>/", v.police_item),
    path("hospital/me/", v.hospital_me),
    path("ambulances/", v.ambulances),
    path("ambulances/<int:pk>/", v.ambulance_item),
    path("cameras/", v.cameras),
    path("cameras/<int:pk>/", v.camera_item),
    path("notifications/", v.notifications),
    path("notifications/read/", v.notifications_read),
    path("notifications/<int:pk>/read/", v.notifications_read),
    path("analytics/", v.analytics),
    path("settings/", v.system_settings),
    path("simulate/", v.simulate),
    path("ingest/", v.ingest),  # used by the AI detection service (X-API-Key header)
]
