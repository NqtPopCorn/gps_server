"""batch/admin.py – read-only admin panels for monitoring batch runs."""

from django.contrib import admin
from batch.models import BatchJob, DailyVisitStat, DailyRevenueStat


@admin.register(BatchJob)
class BatchJobAdmin(admin.ModelAdmin):
    list_display  = ("job_name", "status", "triggered_by", "started_at",
                     "finished_at", "created_at")
    list_filter   = ("job_name", "status", "triggered_by")
    search_fields = ("job_name", "error")
    readonly_fields = ("id", "job_name", "status", "triggered_by",
                       "started_at", "finished_at", "result", "error", "created_at")
    ordering      = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DailyVisitStat)
class DailyVisitStatAdmin(admin.ModelAdmin):
    list_display = ("date", "poi_id", "visits", "updated_at")
    list_filter  = ("date",)
    ordering     = ("-date",)
    readonly_fields = ("date", "poi", "visits", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DailyRevenueStat)
class DailyRevenueStatAdmin(admin.ModelAdmin):
    list_display = ("date", "revenue", "updated_at")
    ordering     = ("-date",)
    readonly_fields = ("date", "revenue", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
