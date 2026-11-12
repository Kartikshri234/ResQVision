import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from emergency.models import Hospital, PoliceStation

from .models import OTP, User
from .permissions import IsAdminRole
from .serializers import (AdminUserSerializer, ProfileUpdateSerializer, SignupSerializer,
                          UserSerializer)

log = logging.getLogger("resqvision")


def user_json(user):
    """Plain dict for a user (shared with the emergency app)."""
    return UserSerializer(user).data


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ident = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        user = authenticate(request, username=ident, password=password)
        if user is None and "@" in ident:
            match = User.objects.filter(email__iexact=ident).first()
            if match:
                user = authenticate(request, username=match.username, password=password)
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


class SignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = SignupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(
            {"detail": "Account created. An administrator must approve it before you can log in."},
            status=status.HTTP_201_CREATED,
        )


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


def _find_user(identifier):
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    return User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier) | Q(phone=identifier)
    ).first()


class ForgotPasswordView(APIView):
    """Step 1 - issue a one-time code. No SMS/e-mail gateway is wired in yet:
    the code is printed to the server console, and returned as `dev_otp` when DEBUG=1."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user = _find_user(request.data.get("identifier"))
        payload = {"detail": "If the account exists, a verification code has been sent."}
        if user:
            otp = OTP.issue(user)
            log.warning("[OTP] code for %s: %s", user.username, otp.code)
            print(f"\n[ResQVision OTP] {user.username}: {otp.code}\n")
            if settings.DEBUG:
                payload["dev_otp"] = otp.code
        return Response(payload)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user = _find_user(request.data.get("identifier"))
        code = (request.data.get("code") or "").strip()
        otp = user.otps.filter(used=False).order_by("-created_at").first() if user else None
        if not otp or not otp.is_valid() or otp.code != code:
            return Response({"detail": "Invalid or expired code."}, status=400)
        return Response({"detail": "Code verified."})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user = _find_user(request.data.get("identifier"))
        code = (request.data.get("code") or "").strip()
        new = request.data.get("new_password") or ""
        otp = user.otps.filter(used=False).order_by("-created_at").first() if user else None
        if not otp or not otp.is_valid() or otp.code != code:
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


class OrganizationsView(APIView):
    """Public list used by the sign-up form."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({
            "hospitals": list(Hospital.objects.order_by("name").values("id", "name")),
            "police_stations": list(PoliceStation.objects.order_by("name").values("id", "name")),
        })


class UserAdminViewSet(viewsets.ModelViewSet):
    """Admin-only user management."""
    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.select_related("police_station", "hospital").order_by("-date_joined")
        if self.request.query_params.get("pending") == "1":
            qs = qs.filter(is_approved=False)
        return qs

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("You cannot delete your own account.")
        instance.delete()
