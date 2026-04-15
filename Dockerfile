# 1. Sử dụng base image Python phiên bản nhẹ (slim) để giảm dung lượng
FROM python:3.12-slim

# 2. Thiết lập các biến môi trường cần thiết
# Ngăn Python tạo ra các file .pyc (.pyc files can cause weird cache issues)
ENV PYTHONDONTWRITEBYTECODE=1
# Đảm bảo log của Python (như print statement) được đẩy thẳng ra console (stdout/stderr)
ENV PYTHONUNBUFFERED=1

# 3. Cài đặt các thư viện hệ thống cần thiết
# (Ví dụ: gcc và libpq-dev rất cần thiết nếu bạn dùng PostgreSQL với thư viện psycopg2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. Thiết lập thư mục làm việc mặc định trong container
WORKDIR /app

# 5. Copy file requirements trước để tận dụng Docker cache
COPY requirements.txt /app/

# 6. Cài đặt các thư viện Python
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install gunicorn

# 7. Copy toàn bộ mã nguồn còn lại vào container
COPY . /app/

# 8. Khai báo port mà container sẽ lắng nghe
EXPOSE 8000

# 9. Lệnh khởi chạy ứng dụng bằng Gunicorn
# LƯU Ý QUAN TRỌNG: Hãy thay 'myproject' bằng tên thư mục chứa file wsgi.py của bạn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]