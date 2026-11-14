from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


def check_password_strength(password, user=None):
    """Run Django's password validators, reporting failures as an API validation error (HTTP 400)."""
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)})


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    police_station_name = serializers.SerializerMethodField()
    hospital_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "full_name", "phone", "role",
            "police_station", "police_station_name", "hospital", "hospital_name",
            "is_active", "is_approved", "date_joined",
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_police_station_name(self, obj):
        return obj.police_station.name if obj.police_station_id else None

    def get_hospital_name(self, obj):
        return obj.hospital.name if obj.hospital_id else None


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone"]


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    full_name = serializers.SerializerMethodField()
    police_station_name = serializers.SerializerMethodField()
    hospital_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "full_name", "phone", "role",
            "police_station", "police_station_name", "hospital", "hospital_name",
            "is_active", "is_approved", "password", "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    get_full_name = UserSerializer.get_full_name
    get_police_station_name = UserSerializer.get_police_station_name
    get_hospital_name = UserSerializer.get_hospital_name

    def validate_role(self, value):
        """Only the super admin may give out (or take away) the admin role."""
        request = self.context.get("request")
        if request and request.user.is_superuser:
            return value
        current = self.instance.role if self.instance else None
        if value != current and User.Role.ADMIN in (value, current):
            raise serializers.ValidationError("Only the super admin can create or change admin accounts.")
        return value

    def create(self, validated):
        password = validated.pop("password", "")
        if not password:
            raise serializers.ValidationError({"password": "A password is required."})
        check_password_strength(password)
        validated.setdefault("is_approved", True)
        user = User(**validated)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated):
        password = validated.pop("password", "")
        for k, v in validated.items():
            setattr(instance, k, v)
        if password:
            check_password_strength(password, instance)
            instance.set_password(password)
        instance.save()
        return instance
