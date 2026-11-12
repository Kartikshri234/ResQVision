import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """One user model for every role. The role decides which dashboard is shown."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        POLICE = "police", "Police"
        HOSPITAL = "hospital", "Hospital"
        AMBULANCE = "ambulance", "Ambulance / Emergency Responder"

    ROLES = Role.choices

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.POLICE)
    phone = models.CharField(max_length=20, blank=True)
    police_station = models.ForeignKey(
        "emergency.PoliceStation", null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    hospital = models.ForeignKey(
        "emergency.Hospital", null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    # Self-registered accounts must be approved by an admin before they can log in.
    is_approved = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
            self.is_approved = True
        if self.role == self.Role.ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)
        self._link_organization()

    def _link_organization(self):
        """Once an account is approved, make it the login account of the organisation it chose at sign-up."""
        if not self.is_approved:
            return
        field = {"police": "police_station", "hospital": "hospital"}.get(self.role)
        if not field or not getattr(self, field + "_id"):
            return
        model = self._meta.get_field(field).related_model
        if model.objects.filter(account=self).exists():
            return
        model.objects.filter(pk=getattr(self, field + "_id"), account__isnull=True).update(account=self)

    @property
    def organization_name(self):
        if self.role == self.Role.POLICE and self.police_station:
            return self.police_station.name
        if self.role == self.Role.HOSPITAL and self.hospital:
            return self.hospital.name
        return ""


class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    @classmethod
    def issue(cls, user):
        cls.objects.filter(user=user, used=False).update(used=True)
        return cls.objects.create(user=user, code=f"{secrets.randbelow(10**6):06d}")

    def is_valid(self):
        return (not self.used) and timezone.now() - self.created_at < timedelta(minutes=10)
