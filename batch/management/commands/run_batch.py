"""
batch/management/commands/run_batch.py

Chạy thủ công (sync) – dùng cho cron và debug:
  python manage.py run_batch aggregate_daily_visits
  python manage.py run_batch aggregate_daily_visits --date 2025-03-01
  python manage.py run_batch cleanup_old_history --retention-days 90
  python manage.py run_batch --all
  python manage.py run_batch --list

Đẩy vào RQ queue (async) – dùng khi không muốn block:
  python manage.py run_batch aggregate_daily_visits --async
  python manage.py run_batch --all --async
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from batch.jobs import JOB_REGISTRY


class Command(BaseCommand):
    help = "Trigger một hoặc tất cả batch jobs (sync hoặc async qua RQ)."

    def add_arguments(self, parser):
        parser.add_argument(
            "job_name",
            nargs="?",
            choices=list(JOB_REGISTRY.keys()),
            help="Tên job cần chạy.",
        )
        parser.add_argument("--all",  action="store_true", help="Chạy tất cả jobs.")
        parser.add_argument("--list", action="store_true", help="Liệt kê jobs và thoát.")
        parser.add_argument("--async", action="store_true", dest="use_async",
                            help="Enqueue vào RQ thay vì chạy trực tiếp.")
        parser.add_argument("--date", type=date.fromisoformat, dest="target_date",
                            metavar="YYYY-MM-DD", help="Override ngày cho date-aware jobs.")
        parser.add_argument("--retention-days", type=int, default=180, dest="retention_days",
                            help="Số ngày giữ lại history (default 180).")

    def handle(self, *args, **options):
        if options["list"]:
            self.stdout.write(self.style.SUCCESS("Available batch jobs:"))
            for name in JOB_REGISTRY:
                self.stdout.write(f"  • {name}")
            return

        if not options["all"] and not options["job_name"]:
            raise CommandError("Cần chỉ định job_name, hoặc dùng --all / --list.")

        jobs_to_run = list(JOB_REGISTRY.keys()) if options["all"] else [options["job_name"]]

        def _kwargs(name):
            kw = {}
            if name in ("aggregate_daily_visits", "aggregate_daily_revenue"):
                kw["target_date"] = options.get("target_date")
            if name == "cleanup_old_history":
                kw["retention_days"] = options["retention_days"]
            return kw

        # ── async path ───────────────────────────────────────────────────────
        if options["use_async"]:
            from batch.queue import enqueue_job
            for name in jobs_to_run:
                job_record, rq_job = enqueue_job(
                    name, triggered_by="management_command", **_kwargs(name)
                )
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Enqueued {name}  [rq_id={rq_job.id}]")
                )
            return

        # ── sync path (default, dùng cho cron) ───────────────────────────────
        from batch.models import BatchJob

        failed = []
        for name in jobs_to_run:
            self.stdout.write(f"\n▶  {name} …")
            job = BatchJob.objects.create(job_name=name, triggered_by="management_command")
            JOB_REGISTRY[name](job, **_kwargs(name))
            job.refresh_from_db()

            if job.status == "success":
                self.stdout.write(self.style.SUCCESS(f"   ✓ SUCCESS  {job.result}"))
            elif job.status == "skipped":
                self.stdout.write(self.style.WARNING("   ⏭  SKIPPED"))
            else:
                self.stdout.write(self.style.ERROR(f"   ✗ FAILED   {job.error}"))
                failed.append(name)

        if failed:
            raise CommandError(f"Jobs thất bại: {', '.join(failed)}")
