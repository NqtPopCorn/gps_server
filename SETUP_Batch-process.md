Dưới đây là tài liệu hướng dẫn nhanh (Quick Start Guide) để xây dựng hệ thống Batch Processing bất đồng bộ trong Django sử dụng **Huey** và **Redis**.

Kiến trúc này tập trung vào việc **tách biệt hoàn toàn** giữa logic nghiệp vụ (business logic) và hệ thống hàng đợi (queue system), giúp code dễ test, dễ bảo trì và không bị phụ thuộc cứng vào bất kỳ thư viện background worker nào.

---

### 1. Yêu cầu hệ thống & Kiến trúc
* **Message Broker:** Redis.
* **Thư viện:** `huey` (thay thế cho Celery/RQ vì tính gọn nhẹ và tích hợp Django tốt).
* **Kiến trúc luồng dữ liệu:**
    `API/Command` ➔ `queue.py` (Enqueuer) ➔ `Redis` ➔ `tasks.py` (Huey Worker) ➔ `jobs.py` (Logic) ➔ `Database`.

### 2. Cài đặt và Cấu hình

**Cài đặt thư viện:**
```bash
pip install huey redis
```

**Cấu hình trong `settings.py`:**
Khai báo app và thiết lập kết nối đến Redis.

```python
INSTALLED_APPS = [
    # ...
    "huey.contrib.djhuey",
    "batch", # Tên app chứa logic batch của bạn
]

# Cấu hình Huey sử dụng Redis
HUEY = {
    'huey_class': 'huey.RedisHuey',
    'name': 'my_django_project',
    'connection': {
        'host': 'localhost', # Hoặc tên container redis nếu dùng Docker
        'port': 6379,
        'db': 0,
    },
    'immediate': False, # Set True nếu muốn chạy đồng bộ (sync) khi debug/test
}
```

### 3. Phân tách Logic: `jobs.py` vs `tasks.py`

Nguyên tắc cốt lõi: Worker của Huey chỉ làm nhiệm vụ **nhận lệnh và bóp cò**, còn toàn bộ chất xám tính toán phải nằm ở file nghiệp vụ riêng.

**A. File nghiệp vụ (`batch/jobs.py`)**
Chứa logic thuần túy, có thể gọi trực tiếp từ command line, API hoặc Worker mà không sinh lỗi.

```python
import logging
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

def process_daily_revenue(job_record, target_date=None):
    """
    Logic gom cụm doanh thu.
    job_record là một instance của model BatchJob để theo dõi trạng thái.
    """
    job_record.status = "running"
    job_record.save()
    
    try:
        # ... logic query Database và tính toán ...
        
        job_record.status = "success"
        job_record.save()
        logger.info(f"Job success for {target_date}")
    except Exception as exc:
        job_record.status = "failed"
        job_record.error = str(exc)
        job_record.save()
        logger.error(f"Job failed: {exc}")
```

**B. File định nghĩa Worker & Lịch trình (`batch/tasks.py`)**
Nơi Huey đăng ký các hàm để chạy ngầm hoặc chạy định kỳ. Bắt buộc dùng decorator `@db_task` để quản lý an toàn các kết nối Database.

```python
import logging
from huey import crontab
from huey.contrib.djhuey import db_task, periodic_task
from batch.jobs import process_daily_revenue

logger = logging.getLogger(__name__)

# 1. TASK CHẠY BẤT ĐỒNG BỘ (Khi có API/Command gọi)
@db_task(retries=3, retry_delay=300) # Thử lại 3 lần, cách nhau 5 phút nếu lỗi
def execute_job_async(job_record_id: str, target_date=None):
    from batch.models import BatchJob
    
    try:
        job = BatchJob.objects.get(id=job_record_id)
        process_daily_revenue(job, target_date)
    except BatchJob.DoesNotExist:
        logger.error("Job record not found.")


# 2. TASK CHẠY ĐỊNH KỲ (Thay thế Cron OS)
@periodic_task(crontab(minute='10', hour='0')) # Chạy lúc 00:10 mỗi ngày
def scheduled_daily_revenue():
    from batch.models import BatchJob
    
    # Tạo record để lưu vết trước khi chạy
    job = BatchJob.objects.create(
        job_name="daily_revenue", 
        triggered_by="huey_scheduler"
    )
    process_daily_revenue(job)
```

### 4. Gửi Job vào hàng đợi (Enqueuing)

Để kích hoạt job từ một Django View hoặc Management Command mà không block luồng chính, bạn tạo một helper để ném job cho Huey.

**File `batch/queue.py`:**
```python
from batch.models import BatchJob
from batch.tasks import execute_job_async

def enqueue_revenue_job(triggered_by="api", target_date=None):
    # 1. Tạo record lưu trạng thái
    job = BatchJob.objects.create(
        job_name="daily_revenue",
        triggered_by=triggered_by
    )
    
    # 2. Đẩy ID vào Redis cho Huey xử lý ngầm
    execute_job_async(job.id, target_date)
    
    return job
```

### 5. Vận hành Worker

Huey cần một process riêng biệt chạy song song với web server để liên tục lắng nghe hàng đợi và canh giờ.

**Chạy ở môi trường Development (Local):**
Mở một terminal riêng và giữ cho lệnh này luôn chạy:
```bash
python manage.py run_huey
```

**Chạy ở môi trường Production (Docker Compose):**
Tạo một service riêng biệt tái sử dụng source code của web app.
```yaml
services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    depends_on:
      - redis
      
  # Khởi chạy Worker
  huey_worker:
    build: .
    command: python manage.py run_huey
    restart: unless-stopped
    depends_on:
      - redis
      
  redis:
    image: redis:7-alpine
    restart: unless-stopped
```

### 6. Những điểm mù cần lưu ý (Gotchas)

* **Timezone (Múi giờ):** Huey sử dụng giờ hệ thống theo cấu hình `TIME_ZONE` của Django (nếu `USE_TZ = True`). Khi deploy bằng Docker, container mặc định chạy múi giờ UTC. Cần mount file `/etc/localtime` hoặc set biến môi trường `TZ` trong `docker-compose.yml` để lịch trình (`crontab`) chạy chính xác giờ địa phương.
* **Truyền tham số cho Task:** Hạn chế truyền các Object Model nguyên bản (ví dụ: `User` object) vào trong hàm của Huey. Hãy truyền `ID` (chuỗi hoặc số) và để Huey tự query lại từ Database. Việc truyền nguyên object qua Redis có thể gây lỗi serialize hoặc làm dữ liệu bị cũ (stale data) khi task bị kẹt lại lâu trong hàng đợi.

### Docker / docker-compose

Thêm service cron vào `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    ...

  rqworker:
    build: .
    command: python manage.py rqworker batch
    depends_on: [redis]
    restart: unless-stopped

  cron:
    build: .
    command: crond -f   # dùng image có crond, ví dụ python:3.12-alpine
    volumes:
      - ./crontab:/etc/crontabs/root:ro  # mount file crontab ở trên
    depends_on: [api]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped
```

---

## 7. Chạy thủ công

```bash
# Xem danh sách jobs
python manage.py run_batch --list

# Chạy sync (blocking, có log ngay)
python manage.py run_batch aggregate_daily_visits
python manage.py run_batch aggregate_daily_visits --date 2025-03-01
python manage.py run_batch --all

# Đẩy vào RQ queue (non-blocking, worker xử lý)
python manage.py run_batch aggregate_daily_visits --async
python manage.py run_batch --all --async
```
