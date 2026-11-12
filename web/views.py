from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def index(request):
    """Serves the single-page HTML/CSS/JS application (and sets the CSRF cookie the API calls need)."""
    return render(request, "web/index.html", {"demo": settings.DEBUG})
