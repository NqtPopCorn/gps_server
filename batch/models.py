import uuid
from django.db import models


class BatchJob(models.Model):
    """Tracks every batch job run – both scheduled and manual."""

    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending"
        RUNNING  = "running",  "Running"
        SUCCESS  = "success",  "Success"
        FAILED   = "failed",   "Failed"
        SKIPPED  = "skipped",  "Skipped"   # already ran today, no-op

    class JobName(models.TextChoices):
        AGGREGATE_DAILY_VISITS  = "aggregate_daily_visits",  "Aggregate Daily Visits"
        AGGREGATE_DAILY_REVENUE = "aggregate_daily_revenue", "Aggregate Daily Revenue"
        CLEANUP_OLD_HISTORY     = "cleanup_old_history",     "Cleanup Old History"
        SYNC_POI_STATUS         = "sync_poi_status",         "Sync POI Status"

    id = models.CharField(max_length=50, primary_key=True,
                          default=uuid.uuid4, editable=False)
    job_name = models.CharField(max_length=100, choices=JobName.choices)
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.PENDING)
    triggered_by = models.CharField(
        max_length=50, default="scheduler",
        help_text="'scheduler', 'celery', or a user id / username"
    )

    # timing
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # outcome
    result = models.JSONField(null=True, blank=True,
                                   help_text="Arbitrary dict with job-specific metrics")
    error  = models.TextField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "batch_job"
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["job_name", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.job_name} [{self.status}] @ {self.created_at:%Y-%m-%d %H:%M}"


class DailyVisitStat(models.Model):
    """Pre-aggregated daily visit counts per POI (populated by batch job)."""

    date    = models.DateField()
    poi     = models.ForeignKey(
        "pois.Poi", on_delete=models.CASCADE, related_name="daily_visit_stats"
    )
    visits  = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "batch_daily_visit_stat"
        unique_together = [("date", "poi")]
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.date} | {self.poi_id} → {self.visits}"


class DailyRevenueStat(models.Model):
    """Pre-aggregated daily revenue (populated by batch job)."""

    date    = models.DateField(unique=True)
    revenue = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "batch_daily_revenue_stat"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} → {self.revenue}"
