"""
batch/tasks.py
"""
import logging
from huey import crontab
from huey.contrib.djhuey import db_task, periodic_task

from batch.jobs import JOB_REGISTRY
from batch.models import BatchJob

logger = logging.getLogger(__name__)

# Cấu hình retry 3 lần, mỗi lần cách nhau 5 phút (300 giây) nếu job bị crash
@db_task(retries=3, retry_delay=300)
def execute_job_async(job_id: str, **kwargs):
    """
    Worker sẽ chạy hàm này.
    Nó nhận ID của BatchJob, lấy ra từ DB và ném vào hàm logic thật.
    """
    try:
        job_record = BatchJob.objects.get(id=job_id)
    except BatchJob.DoesNotExist:
        logger.error(f"[Huey] Cannot find BatchJob with id {job_id}")
        return

    job_name = job_record.job_name
    if job_name in JOB_REGISTRY:
        # Gọi thẳng logic xịn bạn đã viết trong jobs.py
        JOB_REGISTRY[job_name](job_record, **kwargs)
    else:
        logger.error(f"[Huey] Job {job_name} not found in registry")

# Chạy lúc 00:05 hàng ngày UTC+7
@periodic_task(crontab(minute='05', hour='07'))
def schedule_aggregate_daily_visits():
    from batch.models import BatchJob
    from batch.jobs import aggregate_daily_visits
    from batch.queue import enqueue_job
    
    enqueue_job("aggregate_daily_visits", triggered_by="huey_scheduler")
    logger.info("Huey tự động chạy job: aggregate_daily_visits")

# Chạy lúc 00:10 hàng ngày UTC+7
@periodic_task(crontab(minute='10', hour='07'))
def schedule_aggregate_daily_revenue():
    from batch.models import BatchJob
    from batch.jobs import aggregate_daily_revenue
    from batch.queue import enqueue_job
    
    enqueue_job("aggregate_daily_revenue", triggered_by="huey_scheduler")