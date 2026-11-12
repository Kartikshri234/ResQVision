from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import OTP, User


@admin.register(User)
class SmartCrashUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_approved", "is_active")
    list_filter = ("role", "is_approved", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("SmartCrash", {"fields": ("role", "phone", "police_station", "hospital", "is_approved")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("SmartCrash", {"fields": ("role", "phone", "police_station", "hospital", "is_approved")}),
    )


admin.site.register(OTP)
