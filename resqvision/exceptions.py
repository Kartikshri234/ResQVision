"""DRF exception handler: unexpected errors are logged and returned as JSON.

Without this an unhandled exception becomes Django's HTML 500 page, which the frontend cannot parse and
can only show as "Request failed (500)". Now the traceback goes to the server log and the UI gets a message
(with the exception type and text while DJANGO_DEBUG is on).
"""
import logging

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

log = logging.getLogger("resqvision")


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    request = context.get("request")
    http_request = getattr(request, "_request", request)
    log.error(
        "Unhandled error in %s %s",
        getattr(http_request, "method", "?"),
        getattr(http_request, "path", "?"),
        exc_info=exc,
    )
    message = "Something went wrong on the server. Please try again."
    if settings.DEBUG:
        message = f"Server error: {type(exc).__name__}: {exc}"
    return Response({"error": message}, status=500)
