

### 1. Thêm vào file `.env`
```
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

### 2. Migrate data cũ (nếu có file trong `/media/`)
```bash
# Chỉ migrate, giữ lại file gốc
python manage.py migrate_to_cloudinary

# Migrate + xoá file gốc để giải phóng dung lượng
python manage.py migrate_to_cloudinary --delete-local
```