from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("services.urls")),
    path("api/", include("accidents.urls")),
    path("", include("web.urls")),
]

# Evidence images / videos are served by Django in development.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
