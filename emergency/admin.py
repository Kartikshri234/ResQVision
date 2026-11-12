from django.contrib import admin

from .models import (Accident, Alert, Ambulance, Camera, Hospital, Notification, PoliceStation,
                     SystemSetting, TimelineEvent)


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 0


class TimelineInline(admin.TabularInline):
    model = TimelineEvent
    extra = 0


@admin.register(Accident)
class AccidentAdmin(admin.ModelAdmin):
    list_display = ("accident_id", "detected_at", "location", "severity", "confidence", "status", "is_simulated")
    list_filter = ("status", "severity", "is_simulated")
    search_fields = ("accident_id", "location")
    inlines = [AlertInline, TimelineInline]


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "accepting_emergencies", "available_beds", "total_beds", "is_active")


@admin.register(PoliceStation)
class PoliceStationAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_active")


admin.site.register(Ambulance)
admin.site.register(Camera)
admin.site.register(SystemSetting)
admin.site.register(Alert)
admin.site.register(Notification)
