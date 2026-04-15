"""
batch/queue.py
──────────────
Enqueue batch jobs vào Redis thông qua Huey.
"""

from batch.jobs import JOB_REGISTRY
from batch.models import BatchJob
from batch.tasks import execute_job_async


def enqueue_job(job_name: str, triggered_by: str = "api", **kwargs):
    """
    Tạo BatchJob record rồi đẩy vào Huey.
    Trả về (job_record, huey_result) để caller có thể track.
    """
    if job_name not in JOB_REGISTRY:
        raise ValueError(f"Unknown job: {job_name}. Available: {list(JOB_REGISTRY.keys())}")

    # Tạo record để lưu lịch sử (trạng thái đang là pending)
    job_record = BatchJob.objects.create(
        job_name=job_name,
        triggered_by=triggered_by,
    )

    # Đẩy tác vụ vào Huey queue
    # Hàm task của Huey khi gọi sẽ trả về một Result object
    huey_result = execute_job_async(job_record.id, **kwargs)

    return job_record, huey_result