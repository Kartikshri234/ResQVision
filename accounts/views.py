import logging
import secrets

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import OTP, User
from .permissions import IsAdminRole
from .serializers import AdminUserSerializer, ProfileUpdateSerializer, UserSerializer

log = logging.getLogger("resqvision")


def user_json(user):
    """Plain dict for a user (shared with the emergency app)."""
    return UserSerializer(user).data


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        ident = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        user = authenticate(request, username=ident, password=password)
        if user is None and "@" in ident:
            # Only when exactly one account has this e-mail: never guess between two users who share it.
            matches = list(User.objects.filter(email__iexact=ident)[:2])
            if len(matches) == 1:
                user = authenticate(request, username=matches[0].username, password=password)
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=400)
        if not user.is_approved:
            return Response({"detail": "Your account is awaiting administrator approval."}, status=403)
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({"detail": "Logged out."})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        ser = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    def post(self, request):
        old = request.data.get("old_password") or ""
        new = request.data.get("new_password") or ""
        if not request.user.check_password(old):
            return Response({"detail": "Current password is incorrect."}, status=400)
        try:
            validate_password(new, request.user)
        except DjangoValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=400)
        request.user.set_password(new)
        request.user.save()
        update_session_auth_hash(request, request.user)
        return Response({"detail": "Password changed."})


OTP_MAX_FAILURES = 5


def _same_code(expected, given):
    """Constant-time comparison (bytes, so a non-ASCII guess cannot raise)."""
    return secrets.compare_digest(expected.encode(), given.encode())


def _otp_failed(user):
    """Count a wrong code for this ACCOUNT (the per-IP throttle alone lets a spread-out attacker keep guessing).

    After OTP_MAX_FAILURES wrong codes every outstanding code for the account is burned and a new one must
    be requested. The failure counter lives in the cache; burning the codes is stored in the database, so the
    lock-out holds even when the cache is per-process.
    """
    if user is None:
        return
    key = f"otp-fail:{user.pk}"
    cache.add(key, 0, 600)
    try:
        count = cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, 600)
        count = 1
    if count >= OTP_MAX_FAILURES:
        user.otps.filter(used=False).update(used=True)
        cache.delete(key)


def _find_user(identifier):
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    matches = list(User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier) | Q(phone=identifier)
    )[:2])
    # E-mail and phone are not unique. If the identifier matches two accounts, do not pick one at random
    # (that could send a reset code for, or reset the password of, the wrong person): use the username instead.
    return matches[0] if len(matches) == 1 else None


class ForgotPasswordView(APIView):
    """Step 1 - issue a one-time code and e-mail it to the account's address (the console backend prints it
    in development). With DEBUG=1 the code is also returned as `dev_otp`; it is never logged otherwise."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        user = _find_user(request.data.get("identifier"))
        payload = {"detail": "If the account exists, a verification code has been sent."}
        if user:
            otp = OTP.issue(user)
            if user.email:
                try:
                    send_mail(
                        "Your ResQVision verification code",
                        f"Your ResQVision password-reset code is {otp.code}. It expires in 10 minutes.\n"
                        "If you did not request it, you can ignore this message.",
                        None, [user.email],
                    )
                except Exception:
                    log.exception("Could not e-mail the password-reset code to %s", user.username)
            else:
                log.warning("Password reset requested for %s but the account has no e-mail address.", user.username)
            if settings.DEBUG:
                log.warning("[OTP] code for %s: %s", user.username, otp.code)
                payload["dev_otp"] = otp.code
        return Response(payload)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        user = _find_user(request.data.get("identifier"))
        code = (request.data.get("code") or "").strip()
        otp = user.otps.filter(used=False).order_by("-created_at").first() if user else None
        if not otp or not otp.is_valid() or not _same_code(otp.code, code):
            _otp_failed(user)
            return Response({"detail": "Invalid or expired code."}, status=400)
        return Response({"detail": "Code verified."})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        user = _find_user(request.data.get("identifier"))
        code = (request.data.get("code") or "").strip()
        new = request.data.get("new_password") or ""
        otp = user.otps.filter(used=False).order_by("-created_at").first() if user else None
        if not otp or not otp.is_valid() or not _same_code(otp.code, code):
            _otp_failed(user)
            return Response({"detail": "Invalid or expired code."}, status=400)
        try:
            validate_password(new, user)
        except DjangoValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=400)
        user.set_password(new)
        user.save()
        otp.used = True
        otp.save(update_fields=["used"])
        return Response({"detail": "Password reset. You can log in now."})


class UserAdminViewSet(viewsets.ModelViewSet):
    """The ONLY way to create, change or delete accounts (there is no public sign-up).

    - Any admin can manage police / hospital / ambulance accounts.
    - Only the super admin can create, edit or delete other admin accounts.
    - A super admin account can never be deleted or demoted through the API.
    """
    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.select_related("police_station", "hospital").order_by("-date_joined")
        if self.request.query_params.get("pending") == "1":
            qs = qs.filter(is_approved=False)
        return qs

    def _check_can_touch(self, target):
        me = self.request.user
        if target.is_superuser and not me.is_superuser:
            raise PermissionDenied("Only the super admin can change the super admin account.")
        if target.role == User.Role.ADMIN and not me.is_superuser and target.pk != me.pk:
            raise PermissionDenied("Only the super admin can change other admin accounts.")

    def perform_update(self, serializer):
        self._check_can_touch(serializer.instance)
        if serializer.instance.pk == self.request.user.pk:
            data = serializer.validated_data
            if data.get("is_active") is False or data.get("is_approved") is False:
                raise ValidationError("You cannot deactivate or block your own account.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError("You cannot delete your own account.")
        if instance.is_superuser:
            raise PermissionDenied("The super admin account cannot be deleted.")
        self._check_can_touch(instance)
        instance.delete()
