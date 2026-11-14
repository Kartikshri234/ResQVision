"""Extra security headers (Content-Security-Policy and Permissions-Policy)."""
from django.conf import settings

# The portal loads Leaflet from unpkg.com and map tiles from OpenStreetMap; everything else is same-origin.
# 'unsafe-inline' is needed because the single-page app builds markup with inline style attributes and the
# page carries one small inline config script. Framing, <base> hijacking, plugins and cross-origin form posts
# are blocked, and scripts / requests can only go to the listed hosts.
DEFAULT_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",
    "img-src 'self' data: blob: https://unpkg.com https://tile.openstreetmap.org https://*.tile.openstreetmap.org",
    "media-src 'self' blob:",
    "connect-src 'self'",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(settings, "CSP_ENABLED", True) and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = getattr(settings, "CONTENT_SECURITY_POLICY", DEFAULT_CSP)
        if "Permissions-Policy" not in response:
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        return response
