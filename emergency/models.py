from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class PoliceStation(models.Model):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    account = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="police_profile")

    def __str__(self):
        return self.name


class Hospital(models.Model):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    accepting_emergencies = models.BooleanField(default=True)
    total_beds = models.PositiveIntegerField(default=0)
    available_beds = models.PositiveIntegerField(default=0)
    account = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="hospital_profile")

    def __str__(self):
        return self.name


class Ambulance(models.Model):
    STATUS = [("available", "Available"), ("dispatched", "Dispatched"), ("maintenance", "Maintenance")]
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="ambulances")
    vehicle_number = models.CharField(max_length=30)
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="available")

    def __str__(self):
        return self.vehicle_number


class Camera(models.Model):
    camera_id = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    latitude = models.FloatField()
    longitude = models.FloatField()
    road_name = models.CharField(max_length=150, blank=True)
    stream_url = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.camera_id} - {self.name}"


class SystemSetting(models.Model):
    notify_radius_km = models.FloatField(default=25)
    max_police = models.PositiveIntegerField(default=2)
    max_hospitals = models.PositiveIntegerField(default=3)
    min_confidence = models.FloatField(default=0.7)  # below this, an admin must verify before alerts go out
    auto_alert = models.BooleanField(default=True)

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Accident(models.Model):
    SEVERITY = [("low", "Low"), ("medium", "Medium"), ("high", "High")]
    STATUS = [
        ("detected", "Detected"), ("verification_pending", "Verification Pending"), ("confirmed", "Confirmed"),
        ("alert_sent", "Alert Sent"), ("accepted", "Accepted"), ("team_dispatched", "Team Dispatched"),
        ("arrived", "Responders Arrived"), ("resolved", "Resolved"), ("closed", "Closed"),
    ]
    accident_id = models.CharField(max_length=20, unique=True, blank=True)
    detected_at = models.DateTimeField(default=timezone.now)
    camera = models.ForeignKey(Camera, null=True, blank=True, on_delete=models.SET_NULL)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location = models.CharField(max_length=255, blank=True)
    accident_type = models.CharField(max_length=60, blank=True)
    confidence = models.FloatField(default=0)  # 0..1
    severity = models.CharField(max_length=8, choices=SEVERITY, default="medium")  # AI estimate only
    vehicles = models.CharField(max_length=200, blank=True)
    people_count = models.PositiveIntegerField(default=0)
    snapshot = models.ImageField(upload_to="accidents/snapshots/", null=True, blank=True)
    video = models.FileField(upload_to="accidents/videos/", null=True, blank=True)
    status = models.CharField(max_length=24, choices=STATUS, default="detected")
    is_simulated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-detected_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.accident_id:
            self.accident_id = f"SC-{1000 + self.pk}"
            super().save(update_fields=["accident_id"])

    def __str__(self):
        return self.accident_id


class Alert(models.Model):
    """One alert per notified organisation, so police and hospital responses are tracked separately."""
    STATUS = [("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected"),
              ("dispatched", "Dispatched"), ("arrived", "Arrived"), ("resolved", "Resolved")]
    accident = models.ForeignKey(Accident, on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=10)  # police | hospital
    police_station = models.ForeignKey(PoliceStation, null=True, blank=True, on_delete=models.CASCADE)
    hospital = models.ForeignKey(Hospital, null=True, blank=True, on_delete=models.CASCADE)
    distance_km = models.FloatField(default=0)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    reject_reason = models.CharField(max_length=255, blank=True)
    team_name = models.CharField(max_length=100, blank=True)
    ambulance = models.ForeignKey(Ambulance, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def org(self):
        return self.police_station or self.hospital

    @property
    def org_name(self):
        return self.org.name if self.org else ""


class TimelineEvent(models.Model):
    accident = models.ForeignKey(Accident, on_delete=models.CASCADE, related_name="timeline")
    message = models.CharField(max_length=255)
    actor = models.CharField(max_length=100, default="System")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    message = models.CharField(max_length=255)
    accident = models.ForeignKey(Accident, null=True, blank=True, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
