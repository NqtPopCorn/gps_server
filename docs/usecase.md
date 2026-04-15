# Tài liệu kỹ thuật — App thuyết minh đa ngôn ngữ (Client)

## Tổng quan

Ứng dụng cho phép du khách khám phá các điểm tham quan (POI) theo vị trí địa lý, nghe thuyết minh âm thanh đa ngôn ngữ, và trải nghiệm các tour có hướng dẫn. Tài liệu này mô tả kiến trúc client, các use case, và kế hoạch triển khai theo sprint.

---

## Kiến trúc dữ liệu tham chiếu

| Bảng               | Vai trò                                                            |
| ------------------ | ------------------------------------------------------------------ |
| `Pois`             | Thông tin địa lý, loại, trạng thái của điểm tham quan              |
| `LocalizedData`    | Nội dung đa ngôn ngữ (tên, mô tả, audio) theo `poi_id + lang_code` |
| `Tours`            | Danh sách tour                                                     |
| `tour_points`      | Liên kết tour ↔ POI kèm thứ tự (`position`)                        |
| `Users`            | Tài khoản người dùng                                               |
| `Subscription`     | Gói đăng ký của người dùng                                         |
| `SubscriptionPlan` | Định nghĩa các gói (giá, tiêu đề)                                  |

---

## Sprint 1 — Khám phá & Phát nội dung (Use case 1–6)

### UC-01 · Xem POI gần

**Mục tiêu:** Hiển thị danh sách các điểm tham quan gần vị trí hiện tại của người dùng.

**Luồng:**

1. Client yêu cầu vị trí GPS từ thiết bị.
2. Gửi `latitude`, `longitude`, `radius` lên API.
3. API trả về danh sách `Pois` đang `active` trong bán kính.
4. Client render danh sách kèm tên (từ `LocalizedData` theo ngôn ngữ hiện tại) và khoảng cách tính toán phía client.
5. Người dùng có thể chuyển đổi giữa chế độ danh sách và bản đồ.

**Dữ liệu cần:** `Pois` (lat, lng, type, status), `LocalizedData` (name, lang_code)

**Lưu ý kỹ thuật:**

- Ngôn ngữ ưu tiên: lấy từ cài đặt app → fallback về `Pois.default_lang`.
- Tính khoảng cách bằng công thức Haversine tại client để tránh phụ thuộc API.
- Cần xử lý trường hợp người dùng từ chối cấp quyền vị trí (hiển thị danh sách mặc định hoặc yêu cầu nhập địa điểm thủ công).

---

### UC-02 · Xem chi tiết POI

**Mục tiêu:** Hiển thị đầy đủ thông tin của một điểm tham quan.

**Luồng:**

1. Người dùng chọn một POI từ danh sách (UC-01) hoặc bản đồ.
2. Client gọi API lấy chi tiết `Pois` theo `id` hoặc `slug`.
3. Đồng thời lấy `LocalizedData` tương ứng với ngôn ngữ hiện tại.
4. Render: ảnh, tên, mô tả, loại (`type`), nút nghe audio.

**Dữ liệu cần:** `Pois` (image, type, lat, lng), `LocalizedData` (name, description, audio)

**Lưu ý kỹ thuật:**

- Sử dụng `slug` trên URL để hỗ trợ deep link và SEO (nếu là web).
- Nếu `LocalizedData` không tồn tại cho ngôn ngữ yêu cầu, fallback về `Pois.default_lang`.
- Ảnh nên được lazy-load và hỗ trợ skeleton placeholder.

---

### UC-03 · Nghe audio

**Mục tiêu:** Phát file âm thanh thuyết minh của POI theo ngôn ngữ đang chọn.

**Luồng:**

1. Từ màn hình chi tiết POI, người dùng nhấn nút phát.
2. Client lấy URL audio từ `LocalizedData.audio`.
3. Hiển thị thanh player với: play/pause, thanh tiến trình, thời lượng.
4. Cho phép người dùng đổi ngôn ngữ audio ngay trong player → tải lại file mới.

**Dữ liệu cần:** `LocalizedData` (audio, lang_code)

**Lưu ý kỹ thuật:**

- Player nên tiếp tục phát khi người dùng điều hướng sang màn hình khác (background audio / mini player).
- Cache URL audio đã tải để tránh gọi API lại khi đổi qua lại ngôn ngữ.
- Xử lý lỗi khi `LocalizedData.audio` là null: ẩn nút phát, hiện thông báo "Chưa có audio cho ngôn ngữ này".

---

### UC-04 · Xem danh sách tour

**Mục tiêu:** Hiển thị các tour có sẵn để người dùng lựa chọn.

**Luồng:**

1. Client gọi API lấy danh sách `Tours`.
2. Render danh sách với: tên tour, mô tả (nếu có), số lượng điểm dừng.
3. Người dùng chọn một tour để xem chi tiết (UC-05).

**Dữ liệu cần:** `Tours` (id, name, description), số lượng `tour_points` liên quan

**Lưu ý kỹ thuật:**

- `Tours` hiện chưa có trường ngôn ngữ — tên và mô tả tour được xem là ngôn ngữ gốc. Cân nhắc mở rộng schema nếu cần đa ngôn ngữ cho tour trong tương lai.
- Số điểm dừng nên được API trả kèm hoặc tính từ `tour_points` (tránh N+1 query tại client).

---

### UC-05 · Xem chi tiết tour

**Mục tiêu:** Hiển thị danh sách các POI trong một tour theo thứ tự đã định.

**Luồng:**

1. Người dùng chọn một tour từ UC-04.
2. Client gọi API lấy `tour_points` theo `tour_id`, sắp xếp theo `position`.
3. Với mỗi `tour_point`, lấy thông tin `Pois` và `LocalizedData` tương ứng.
4. Render danh sách POI theo thứ tự, kèm tên, ảnh thumbnail, mô tả ngắn.
5. Hiển thị bản đồ với các điểm được đánh số theo `position`.

**Dữ liệu cần:** `tour_points` (position), `Pois` (image, lat, lng), `LocalizedData` (name, description)

**Lưu ý kỹ thuật:**

- Nên join dữ liệu tại API (một request) thay vì client gọi nhiều request riêng lẻ.
- Cho phép nhấn vào từng POI trong tour để xem chi tiết (UC-02) và phát audio (UC-03).

---

### UC-06 · Auto play

**Mục tiêu:** Tự động phát thuyết minh khi người dùng tiến đến gần một POI.

**Luồng:**

1. Client theo dõi vị trí GPS liên tục (background geolocation).
2. Tính khoảng cách từ vị trí hiện tại đến các POI trong vùng.
3. Khi khoảng cách < ngưỡng (ví dụ 50m), trigger phát audio của POI đó.
4. Hiển thị mini-card thông báo POI vừa được kích hoạt kèm nút xem chi tiết.
5. Không phát lại POI đã được auto-play trong cùng phiên (tránh lặp lại).

**Dữ liệu cần:** `Pois` (lat, lng, id), `LocalizedData` (audio, lang_code)

**Lưu ý kỹ thuật:**

- Ngưỡng khoảng cách nên có thể cấu hình (mặc định 50m).
- Chỉ auto-play khi người dùng đã bật tính năng (toggle trong settings — opt-in).
- Cần xin quyền `background location` trên iOS (Always Allow) và xử lý các trường hợp bị từ chối.
- Hàng đợi audio: nếu người dùng đang nghe POI A và đi vào vùng POI B, enqueue POI B hoặc hiện thông báo chờ.

---

## Sprint 2 — Auth & Subscription (Use case 7–10)

### UC-07 · Auth

**Mục tiêu:** Đăng ký, đăng nhập, quản lý phiên đăng nhập người dùng.

**Luồng:**

1. Người dùng chọn đăng ký (email + password) hoặc đăng nhập.
2. API xác thực và trả về access token + refresh token.
3. Client lưu token an toàn (Keychain trên iOS / Keystore trên Android / httpOnly cookie trên web).
4. Mọi request sau đó đính kèm `Authorization: Bearer <token>`.
5. Khi token hết hạn, dùng refresh token để lấy token mới tự động.

**Dữ liệu cần:** `Users` (email, password, role)

**Lưu ý kỹ thuật:**

- `Users.role` có hai giá trị: `admin` và `tourist`. Client chỉ xử lý role `tourist`; admin dùng giao diện riêng.
- Tuyệt đối không lưu password phía client.
- Hiển thị lỗi rõ ràng: sai mật khẩu, email chưa đăng ký, tài khoản bị khóa.
- Hỗ trợ "Quên mật khẩu" qua email (API gửi reset link).

---

### UC-08 · Subscribe

**Mục tiêu:** Cho phép người dùng mua gói đăng ký để mở khóa nội dung.

**Luồng:**

1. Người dùng vào màn hình Subscription, xem các `SubscriptionPlan` (tên, giá).
2. Chọn gói và phương thức thanh toán (`payment_method`).
3. Sau khi thanh toán thành công, API tạo bản ghi `Subscription` với `status = active` và `expired_at`.
4. Client cập nhật trạng thái quyền và cho phép truy cập nội dung premium.

**Dữ liệu cần:** `SubscriptionPlan` (title, price), `Subscription` (created_at, expired_at, status, amount)

**Lưu ý kỹ thuật:**

- Tích hợp payment gateway (MoMo, ZaloPay, Stripe...) — xử lý callback/webhook để xác nhận thanh toán trước khi activate.
- Không activate subscription chỉ dựa vào client-side callback; phải chờ server xác nhận.
- Hiển thị rõ ngày hết hạn và tự động nhắc gia hạn khi còn 7 ngày.

---

### UC-09 · Check quyền

**Mục tiêu:** Kiểm tra người dùng có subscription hợp lệ trước khi cho phép truy cập nội dung giới hạn.

**Luồng:**

1. Khi người dùng cố truy cập nội dung premium (ví dụ: audio của một POI giới hạn), client gọi API kiểm tra quyền.
2. API kiểm tra `Subscription` của `user_id`: `status = active` và `expired_at > now()`.
3. Nếu hợp lệ: cho phép truy cập.
4. Nếu không hợp lệ: hiện paywall / màn hình mời đăng ký.

**Dữ liệu cần:** `Subscription` (status, expired_at)

**Lưu ý kỹ thuật:**

- Cache kết quả kiểm tra quyền trong phiên (tránh gọi API mỗi lần phát audio).
- Invalidate cache ngay khi người dùng vừa subscribe (UC-08) hoặc logout.
- Không kiểm tra quyền hoàn toàn phía client — luôn validate tại server.

---

### UC-10 · History

**Mục tiêu:** Hiển thị lịch sử đăng ký của người dùng.

**Luồng:**

1. Người dùng vào mục "Lịch sử đăng ký" trong profile.
2. Client gọi API lấy danh sách `Subscription` của `user_id`, sắp xếp theo `created_at` giảm dần.
3. Mỗi bản ghi hiển thị: tên gói (join `SubscriptionPlan`), ngày mua, ngày hết hạn, số tiền, trạng thái.

**Dữ liệu cần:** `Subscription` (tất cả các trường), `SubscriptionPlan` (title)

**Lưu ý kỹ thuật:**

- Phân trang (pagination) nếu lịch sử dài.
- Trạng thái `Subscription.status` nên được hiển thị bằng nhãn trực quan: active (xanh), expired (xám), cancelled (đỏ).

---

## Quy ước chung

### Xử lý đa ngôn ngữ

- Ngôn ngữ hiện tại lưu trong app state (Redux / Zustand / Provider).
- Thứ tự ưu tiên khi lấy nội dung: **ngôn ngữ người dùng chọn** → `Pois.default_lang` → ngôn ngữ đầu tiên có trong `LocalizedData`.
- Cho phép người dùng đổi ngôn ngữ bất kỳ lúc nào mà không cần reload app.

### Xử lý lỗi & offline

- Mọi màn hình phải có trạng thái: loading, success, error, empty.
- Cache dữ liệu POI đã xem gần đây để hỗ trợ offline cơ bản.
- Hiển thị thông báo kết nối khi mất mạng; tự động retry khi có kết nối trở lại.

### Bảo mật

- Token không lưu trong `localStorage` (web) — dùng httpOnly cookie hoặc memory store.
- Không log thông tin nhạy cảm (token, email, password) ra console.
- Tất cả request gọi qua HTTPS.
