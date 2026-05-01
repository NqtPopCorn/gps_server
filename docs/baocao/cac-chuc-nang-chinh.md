Listed directory gps_server
Searched for "class "
Searched for "class "
Searched for "class "

Dựa trên mã nguồn hiện có của các file models và views thuộc từng app, đây là danh sách các module và các chức năng chính trong hệ thống của bạn:

**1. Module: Accounts / Auth (Xác thực và Người dùng)**
   - Chức năng: Đăng nhập (Login)
     + Cho phép người dùng xác thực và nhận token truy cập từ hệ thống.
   - Chức năng: Đăng ký (Register)
     + Cho phép người dùng mới tạo tài khoản trên hệ thống.
   - Chức năng: Quản lý hồ sơ (Profile)
     + Cho phép người dùng xem và cập nhật thông tin cá nhân của mình.

**2. Module: POIs (Điểm yêu thích / Địa điểm)**
   - Chức năng: Quản lý POI dành cho Admin
     + Admin có quyền thêm mới, cập nhật, xóa và lấy danh sách toàn bộ các địa điểm (POI).
   - Chức năng: Quản lý dữ liệu đa ngôn ngữ / Âm thanh (Localization)
     + Admin có thể thêm, cập nhật hoặc xóa thông tin dịch thuật và cấp quyền/âm thanh nội dung bản địa hóa cho một POI cụ thể.
   - Chức năng: Khám phá POI dành cho người dùng 
     + Cung cấp tính năng tìm kiếm tên POI, tìm các POI ở gần vị trí hiện tại và xem thông tin chi tiết của một POI.

**3. Module: Tours (Hành trình / Tuyến tham quan)**
   - Chức năng: Quản lý Tour dành cho Admin
     + Admin có thể tạo mới, cập nhật, xóa và lấy danh sách chi tiết các hành trình (Tour).
   - Chức năng: Quản lý Điểm thuộc Tour (Tour Point)
     + Admin có thể thêm các điểm POI vào một Tour, cập nhật thông tin và xóa các điểm khỏi Tour.
   - Chức năng: Tương tác Tour dành cho người dùng
     + Cho phép người dùng xem danh sách Tour, xem chi tiết Tour và kích hoạt Tour bằng mã kích hoạt (Activation Code).

**4. Module: Analytics & Batch (Thống kê và Xử lý ngầm)**
   - Chức năng: Dashboard thống kê cho Admin
     + Cung cấp số liệu tổng quan hệ thống, lượt truy cập (Visits), tổng doanh thu (Revenue), các POI/Tour phổ biến nhất và theo dõi số lượng User đang hoạt động.
   - Chức năng: Dashboard thống kê cho Partner
     + Cung cấp các số liệu riêng được phân quyền cho Partner (tổng quan, lượt truy cập và hiệu suất các POI của đối tác).
   - Chức năng: Xử lý số liệu lưu trữ nền (Batch Processing)
     + Hệ thống tạo các Job ẩn để tự động tổng hợp/lọc số liệu theo chu kỳ nhằm lưu trữ thông tin lượt truy cập và doanh thu theo ngày (`DailyVisitStat`, `DailyRevenueStat`).

**5. Module: Payments (Thanh toán / Hóa đơn)**
   - Chức năng: Quản lý hóa đơn (Invoice)
     + Hỗ trợ khởi tạo hóa đơn, truy xuất danh sách và xem chi tiết một phiên giao dịch/hóa đơn trong hệ thống.

**6. Module: History (Lịch sử hoạt động)**
   - Chức năng: Lưu vết hoạt động và sự kiện
     + Cung cấp cơ chế lưu trữ nội dung log, thao tác người dùng (lịch sử) và truy xuất thông tin lịch sử của hệ thống.

**7. Module: NLS (Natural Language Service - Dịch thuật & Trí tuệ tự nhiên)**
   - Chức năng: Dịch thuật (Translate)
     + Cung cấp API (chủ yếu dùng cho Admin) để tự động dịch các đoạn chữ bằng trí tuệ nhân tạo.
   - Chức năng: Text-to-Speech (TTS)
     + API tạo yêu cầu chuyển đổi văn bản sang âm thanh giọng nói phục vụ cho tính năng thuyết minh đa ngôn ngữ.