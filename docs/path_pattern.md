### 1. Cấu trúc Đường dẫn (Path Patterns)

Tất cả các file được lưu trữ trong thư mục gốc `MEDIA_ROOT`. Cấu trúc phân cấp như sau:

| Loại File | Pattern Đường dẫn | Ví dụ thực tế |
|---|---|---|
| Ảnh đại diện POI | `pois/{poi_id}/image{extension}` | `media/pois/237568b5-2081-4a1e-bcff-73e01626f628/image.jpg` |
| Âm thanh (Audio) | `pois/{poi_id}/audio_{lang_code}{ext}` | `media/pois/237568b5-2081-4a1e-bcff-73e01626f628/audio_vi.mp3` |