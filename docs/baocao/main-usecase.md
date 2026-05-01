Edited erd.md
Viewed views.py:1-478

Dưới đây là các biểu đồ thiết kế (Use Case, Activity, Sequence) dựa hoàn toàn vào hệ thống mã nguồn hiện tại của các controllers (views), services (celery/batch tasks), và entities (models).

## 3. Use Case Diagram

Sơ đồ Use Case thể hiện tương tác của các tác nhân (Actor) đối với hệ thống, chia theo vai trò cấu hình trong model hiện tại (`admin`, `partner`, `tourist` và hệ thống xử lý ngầm `Batch System`).

```plantuml
@startuml
left to right direction

actor "Tourist" as tourist
actor "Admin" as admin
actor "Partner" as partner
actor "Batch System" as batch

package "GPS Server API" {
  usecase "Đăng ký / Đăng nhập / Hồ sơ" as UC_Auth
  usecase "Tìm kiếm & Khám phá POI lân cận" as UC_ExplorePOI
  usecase "Xem danh sách Tour & Chi tiết" as UC_TourList
  usecase "Kích hoạt tham gia Tour" as UC_TourActivate
  
  usecase "Quản lý dữ liệu POI" as UC_ManagePOI
  usecase "Quản lý bản địa hóa & âm thanh POI" as UC_LocPOI
  usecase "Quản lý Tuyến tham quan (Tour)" as UC_ManageTour
  usecase "Quản lý Điểm thuộc Tour (Tour Point)" as UC_ManageTourPoint
  usecase "Xem thống kê (Overview, Visits, Revenue)" as UC_Analytics
  usecase "Quản lý & duyệt Hóa đơn" as UC_Invoice
  
  usecase "Lưu và dọn dẹp Lịch sử hoạt động" as UC_History
  usecase "Chạy Job tổng hợp lượt truy cập ngày" as UC_BatchVisit
  usecase "Chạy Job tổng hợp doanh thu ngày" as UC_BatchRevenue
}

tourist --> UC_Auth
tourist --> UC_ExplorePOI
tourist --> UC_TourList
tourist --> UC_TourActivate

admin --> UC_ManagePOI
admin --> UC_LocPOI
admin --> UC_ManageTour
admin --> UC_ManageTourPoint
admin --> UC_Invoice
admin --> UC_Analytics

partner --> UC_ManagePOI
partner --> UC_ManageTour
partner --> UC_ManageTourPoint
partner --> UC_Analytics

batch --> UC_BatchVisit
batch --> UC_BatchRevenue
batch --> UC_History
@enduml
```


## 4. Activity Diagram

Một số luồng chính đáng chú ý nhất dựa trên logic code tại `views.py`.

### Luồng 1: Người dùng Kích hoạt Tour (Dựa theo `TourActivateView.get`)

```plantuml
@startuml
start
:Người dùng gửi GET /tours/{tour_id}/activate?code=...;

if (Hệ thống tìm thấy Tour(id)?) then (Có)
  if (Tour.status == 'published'?) then (Đúng)
    if (Yêu cầu có tham số 'code'?) then (Có)
      :Tìm TourActivationCode theo 'code' truyền vào;
      if (Mã kích hoạt tồn tại?) then (Có)
        if (Mã kích hoạt chưa hết hạn (is_expired == false)?) then (Đúng)
          if (Mã kích hoạt thuộc về (tour_id) hiện tại?) then (Đúng)
            :Tính toán số giây còn lại (remaining_seconds);
            :Trả về HTTP 200 (tour_id, code, expires_in, expired_at);
            stop
          else (Sai)
          endif
        else (Sai - Đã hết hạn)
        endif
      else (Không)
      endif
    else (Không)
    endif
  else (Sai)
  endif
else (Không)
endif

:Trả về HTTP 400 (Bad Request) / HTTP 404 (Not Found) kèm nguyên nhân lỗi;
stop
@enduml
```

### Luồng 2: Admin/Partner tạo Tour mới (Dựa theo `AdminTourListCreateView.post`)

```plantuml
@startuml
start
:Admin/Partner gửi yêu cầu POST tạo Tour kèm Dữ liệu + Ảnh;
:Kiểm tra CreateTourSerializer;

if (Dữ liệu hợp lệ?) then (Có)
  :Tạo bản ghi Tour trong Model (Database);
  
  if (Request có đính kèm file ảnh?) then (Có)
    :Upload hình ảnh qua module (cloudinary_helper);\nNhận URL trả về;
    :Cập nhật URL ảnh và lưu lại bản ghi Tour;
  else (Không)
  endif
  
  if (Người yêu cầu có role == 'partner'?) then (Đúng)
    :Gán thuộc tính partner_id bằng tài khoản Partner đang yêu cầu;
  else (Sai)
  endif
  
  :Trả về lời gọi HTTP 201 kèm dữ liệu Tour mới tạo;
  stop
else (Không)
  :Trả về lỗi HTTP 400 kèm các chi tiết lỗi dữ liệu;
  stop
endif
@enduml
```


## 5. Sequence Diagram

Chức năng "Kích hoạt Tour" với tính logic xử lý quan trọng liên quan đến Code và thời gian (Expiration).

```plantuml
@startuml
autonumber
actor "Tourist" as User
participant "TourActivateView" as View
database "Tour" as TourDB
database "TourActivationCode" as CodeDB

User -> View : GET /tours/{tour_id}/activate?code=ABC
activate View

View -> TourDB : Lệnh get_object_or_404(Tour, id=tour_id)
activate TourDB
TourDB --> View : Trả về đối tượng Tour (hoặc trả 404 nếu không tìm thấy)
deactivate TourDB

alt Trạng thái Tour không phải 'published'
    View --> User : HTTP 400 {"error": "Tour is not active"}
else Lượt query bỏ trống tham số code
    View --> User : HTTP 400 {"error": "Code is required"}
else Các bước kiểm tra sơ khởi hợp lệ
    View -> CodeDB : filter(code=code).first()
    activate CodeDB
    CodeDB --> View : Trả về đối tượng activation_code (hoặc None)
    deactivate CodeDB

    alt Không tìm thấy activation_code
        View --> User : HTTP 400 {"error": "Code is not valid"}
    else Code đã bị quá thời gian tồn tại
        View -> CodeDB : is_expired() -> True
        View --> User : HTTP 400 {"error": "Code is expired"}
    else Thuộc tính tour_id của Code không bảo vệ khóa gốc tour_id yêu cầu
        View --> User : HTTP 400 {"error": "Code is not valid"}
    else Thành công vượt qua các logic kiểm tra
        View -> View : Tính max(0, expired_at - current_timezone.now())
        View --> User : HTTP 200 {"tour_id": ..., "code": ..., "expires_in": ..., "expired_at": ...}
    end
end

deactivate View
@enduml
```