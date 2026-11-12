from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


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


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "phone", "role",
                  "police_station", "hospital", "password"]

    def validate_role(self, value):
        if value not in ("police", "hospital", "ambulance"):
            raise serializers.ValidationError("Choose Police, Hospital or Ambulance.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This e-mail is already registered.")
        return value

    def validate(self, attrs):
        role = attrs.get("role")
        if role == "police" and not attrs.get("police_station"):
            raise serializers.ValidationError({"police_station": "Select your police station."})
        if role == "hospital" and not attrs.get("hospital"):
            raise serializers.ValidationError({"hospital": "Select your hospital."})
        validate_password(attrs["password"])
        return attrs

    def create(self, validated):
        password = validated.pop("password")
        user = User(**validated, is_approved=False)
        user.set_password(password)
        user.save()
        return user


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

    def create(self, validated):
        password = validated.pop("password", "")
        if not password:
            raise serializers.ValidationError({"password": "A password is required."})
        validate_password(password)
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
            validate_password(password, instance)
            instance.set_password(password)
        instance.save()
        return instance
