"""
batch/jobs.py
─────────────
Pure-Python batch functions.  Each function:
  • accepts a `BatchJob` instance as its first argument
  • updates job.status / job.result / job.error itself
  • returns the final BatchJob
  • can be called from anywhere: management command, Celery task, tests, shell

Add new jobs here and register them in JOB_REGISTRY at the bottom.
"""

import logging
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import date, datetime, time, timedelta
from django.utils.timezone import make_aware

logger = logging.getLogger(__name__)

# ── lazy imports so this module can be imported without a full Django setup ──

def _models():
    from batch.models import BatchJob, DailyVisitStat, DailyRevenueStat
    return BatchJob, DailyVisitStat, DailyRevenueStat


def _history():
    from history.models import History
    return History


def _invoice():
    from payments.models import Invoice
    return Invoice


# ─── helpers ─────────────────────────────────────────────────────────────────

def _start(job):
    job.status = "running"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    return job


def _finish(job, result: dict):
    job.status = "success"
    job.result = result
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "result", "finished_at"])
    logger.info("[batch] %s SUCCESS  %s", job.job_name, result)
    return job


def _fail(job, exc: Exception):
    job.status = "failed"
    job.error = str(exc)
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at"])
    logger.error("[batch] %s FAILED  %s", job.job_name, exc, exc_info=True)
    return job


# ── Tách logic thuần ra helper, không cần BatchJob ──────────────────────────

def _do_aggregate_visits(target_date: date) -> dict:
    """Core logic: aggregate History → DailyVisitStat cho một ngày cụ thể."""
    _, DailyVisitStat, _ = _models()
    History = _history()

    # Fix: dùng aware datetime thay vì date thuần
    start = make_aware(datetime.combine(target_date, time.min))
    end   = make_aware(datetime.combine(target_date, time.max))

    rows = (
        History.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .values("poi_id")
        .annotate(visits=Count("id"))
    )

    created = updated = 0
    with transaction.atomic():
        for row in rows:
            _, was_created = DailyVisitStat.objects.update_or_create(
                date=target_date,
                poi_id=row["poi_id"],
                defaults={"visits": row["visits"]},
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return {"target_date": target_date.isoformat(), "rows_created": created, "rows_updated": updated}


def _do_aggregate_revenue(target_date: date) -> dict:
    """Core logic: aggregate Invoice → DailyRevenueStat cho một ngày cụ thể."""
    _, _, DailyRevenueStat = _models()
    Invoice = _invoice()

    # Fix: dùng aware datetime
    start = make_aware(datetime.combine(target_date, time.min))
    end   = make_aware(datetime.combine(target_date, time.max))

    total = (
        Invoice.objects
        .filter(status=Invoice.Status.SUCCESS, paid_at__gte=start, paid_at__lte=end)
        .aggregate(total=Sum("amount"))["total"]
    ) or 0

    with transaction.atomic():
        _, was_created = DailyRevenueStat.objects.update_or_create(
            date=target_date,
            defaults={"revenue": total},
        )

    return {"target_date": target_date.isoformat(), "revenue": float(total), "was_created": was_created}


# ── Job wrappers giờ chỉ gọi lại helper ──────────────────────────────────────

def aggregate_daily_visits(job, target_date: date | None = None):
    _start(job)
    try:
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        return _finish(job, _do_aggregate_visits(target_date))
    except Exception as exc:
        return _fail(job, exc)


def aggregate_daily_revenue(job, target_date: date | None = None):
    _start(job)
    try:
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        return _finish(job, _do_aggregate_revenue(target_date))
    except Exception as exc:
        return _fail(job, exc)

# ─── job: cleanup_old_history ─────────────────────────────────────────────────

def cleanup_old_history(job, retention_days: int = 180):
    """
    Hard-delete History rows older than `retention_days` days.
    Default retention: 180 days (≈ 6 months).
    """
    History = _history()

    _start(job)
    try:
        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted, _ = History.objects.filter(created_at__lt=cutoff).delete()
        return _finish(job, {
            "cutoff": cutoff.date().isoformat(),
            "retention_days": retention_days,
            "rows_deleted": deleted,
        })
    except Exception as exc:
        return _fail(job, exc)


# ─── job: sync_poi_status ─────────────────────────────────────────────────────

def sync_poi_status(job):
    """
    Business-rule example: deactivate POIs that have had zero visits in the
    last 90 days AND were created more than 90 days ago.

    Adjust the rule to match your own product requirements.
    """
    from pois.models import Poi
    History = _history()

    _start(job)
    try:
        cutoff = timezone.now() - timedelta(days=90)

        # POIs with at least one recent visit
        active_poi_ids = set(
            History.objects
            .filter(created_at__gte=cutoff)
            .values_list("poi_id", flat=True)
            .distinct()
        )

        # Old POIs with no recent activity
        candidates = Poi.objects.filter(
            status="active",
            created_at__lt=cutoff,
        ).exclude(id__in=active_poi_ids)

        count = candidates.count()
        with transaction.atomic():
            candidates.update(status="inactive")

        return _finish(job, {
            "deactivated": count,
            "cutoff_days": 90,
        })
    except Exception as exc:
        return _fail(job, exc)

# ─── registry ─────────────────────────────────────────────────────────────────
# Maps job_name string → callable(job, **kwargs)
# Register every new job here so the management command & Celery tasks can
# discover it by name.

JOB_REGISTRY: dict[str, callable] = {
    "aggregate_daily_visits":  aggregate_daily_visits,
    "aggregate_daily_revenue": aggregate_daily_revenue,
    "cleanup_old_history":     cleanup_old_history,
    "sync_poi_status":         sync_poi_status,
}
