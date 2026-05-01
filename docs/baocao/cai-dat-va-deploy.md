**User:**

vẽ sequence diagram cho role partner từ FE, BE, DB

---

**Assistant:**

Dưới đây là sequence diagram cho role **partner** theo flow **FE → BE → DB** của dashboard partner:

```mermaid
sequenceDiagram
    autonumber
    actor Partner as Partner User
    participant FE as Frontend
    participant BE as Backend API
    participant DB as Database

    Partner->>FE: Mở trang /partner/dashboard
    FE->>FE: Load PartnerDashboard component
    FE->>FE: Tạo dateParams (7d / 30d)

    par Get overview
        FE->>BE: GET /api/partner/dashboard/overview?from&to
        BE->>BE: Verify JWT role = partner
        BE->>DB: Query POIs owned by current_user.id
        BE->>DB: Aggregate totalVisits, uniqueUsers
        DB-->>BE: Result overview
        BE-->>FE: { totalVisits, uniqueUsers }
    and Get visits
        FE->>BE: GET /api/partner/dashboard/visits?from&to
        BE->>BE: Verify JWT role = partner
        BE->>DB: Query visits for owned POIs by date range
        DB-->>BE: Daily visit data
        BE-->>FE: [{ date, visits }, ...]
    and Get POI performance
        FE->>BE: GET /api/partner/dashboard/pois?from&to
        BE->>BE: Verify JWT role = partner
        BE->>DB: Query POI list owned by current_user.id
        BE->>DB: Aggregate visits per POI
        DB-->>BE: POI performance data
        BE-->>FE: [{ poiId, name, visits }, ...]
    end

    FE->>FE: Render KPI cards, chart, top POIs
```

Logic chính từ repo:

- FE gọi 3 API song song bằng `Promise.all(...)`
- Endpoint partner:
  - `GET /api/partner/dashboard/overview`
  - `GET /api/partner/dashboard/visits`
  - `GET /api/partner/dashboard/pois`
- Tất cả endpoint partner đều filter theo:
  - `Pois.owner_id = current_user.id`

Nguồn:
- `src/pages/PartnerDashboard.tsx:38-45`
- `src/services/dashboard.service.ts:47-58`
- `.agent/analystics.md:127-131, 237-271`

Nếu bạn muốn, mình có thể vẽ thêm bản **sequence diagram riêng cho luồng đăng nhập partner** hoặc **luồng tạo POI / QR code**.

---

**User:**

làm toàn bộ chức năng, chia ra các khối

---

**Assistant:**

Đây là sơ đồ **toàn bộ chức năng partner**, chia theo **các khối** FE → BE → DB:

```mermaid
sequenceDiagram
    autonumber
    actor Partner as Partner User
    participant FE as Frontend
    participant BE as Backend API
    participant DB as Database

    rect rgb(235,245,255)
    note over Partner,FE: 1) Đăng nhập / phân quyền
    Partner->>FE: Login
    FE->>BE: POST /login
    BE->>DB: Verify account + role
    DB-->>BE: User + JWT
    BE-->>FE: Token + profile
    FE->>FE: Điều hướng theo role
    alt role = partner
        FE->>FE: redirect /partner/pois hoặc /partner/dashboard
    else role != partner
        FE->>FE: redirect /forbidden
    end
    end

    rect rgb(240,255,240)
    note over Partner,FE: 2) Vào partner layout
    Partner->>FE: Mở /partner/*
    FE->>BE: Check auth (PrivateRoute)
    BE-->>FE: Cho phép nếu JWT role=partner
    FE->>FE: Render Layout + Partner sidebar
    end

    rect rgb(255,248,235)
    note over Partner,FE: 3) Dashboard partner
    Partner->>FE: Mở /partner/dashboard
    FE->>FE: PartnerDashboard mount
    FE->>FE: Tính dateParams (7d/30d)

    par Overview
        FE->>BE: GET /api/partner/dashboard/overview?from&to
        BE->>BE: Check role partner
        BE->>DB: Lọc POIs theo owner_id = current_user.id
        BE->>DB: Aggregate totalVisits + uniqueUsers
        DB-->>BE: Overview data
        BE-->>FE: { totalVisits, uniqueUsers }
    and Visits
        FE->>BE: GET /api/partner/dashboard/visits?from&to
        BE->>BE: Check role partner
        BE->>DB: Query lịch sử ghé theo POIs sở hữu
        BE->>DB: Group by date
        DB-->>BE: [{date, visits}]
        BE-->>FE: Visits chart data
    and POI performance
        FE->>BE: GET /api/partner/dashboard/pois?from&to
        BE->>BE: Check role partner
        BE->>DB: Query POIs thuộc current_user.id
        BE->>DB: Count visits theo từng POI
        DB-->>BE: [{poiId, name, visits}]
        BE-->>FE: POI performance data
    end

    FE->>FE: Render KPI cards + chart + top POIs
    end

    rect rgb(245,240,255)
    note over Partner,FE: 4) Đổi khoảng thời gian
    Partner->>FE: Chọn 7d / 30d
    FE->>FE: Cập nhật rangePreset
    FE->>FE: Gọi lại loadPartnerDashboard()
    FE->>BE: 3 API dashboard với query mới
    BE->>DB: Re-aggregate dữ liệu theo from/to
    DB-->>BE: Dữ liệu mới
    BE-->>FE: Update overview/visits/pois
    end

    rect rgb(255,240,240)
    note over Partner,FE: 5) Mua lượt tạo POI
    Partner->>FE: Mở khối "Mua lượt tạo POI"
    FE->>FE: Render PayPalScriptProvider + BuyPoiCreditComponent
    FE->>BE: Tạo payment / xác nhận thanh toán
    BE->>DB: Lưu giao dịch + cộng credit POI
    DB-->>BE: Transaction updated
    BE-->>FE: Thành công
    FE->>FE: Toast + refresh profile
    end

    rect rgb(240,250,255)
    note over Partner,FE: 6) Quản lý POI / Tours / QR Codes
    Partner->>FE: Mở /partner/pois | /partner/tours | /partner/qr-codes
    FE->>BE: Load data theo quyền partner
    BE->>DB: Lọc dữ liệu theo owner_id / role partner
    DB-->>BE: Data phù hợp
    BE-->>FE: Danh sách để quản lý
    end
```

### Chia khối chức năng partner
1. **Auth / phân quyền**
   - Login
   - JWT role check
   - Redirect theo role

2. **Partner layout**
   - Sidebar riêng cho partner
   - Ẩn search
   - Brand: `Partner Portal`

3. **Dashboard**
   - Overview
   - Visits chart
   - Top POIs
   - Load song song 3 API

4. **Filter thời gian**
   - `7d` / `30d`
   - Reload toàn bộ dashboard

5. **Mua credit tạo POI**
   - PayPal
   - Cộng lượt tạo POI
   - Refresh profile sau khi mua

6. **Quản lý POI / Tours / QR**
   - Màn hình quản lý theo quyền partner
   - Chỉ thấy dữ liệu thuộc `owner_id`

Nguồn chính:
- `src/App.tsx:34-46`
- `src/components/Layout.tsx:18-35`
- `src/pages/PartnerDashboard.tsx:38-60`
- `src/services/dashboard.service.ts:47-58`
- `src/modals/CreatePoiModal.tsx:91-99`
- `src/contexts/AuthContext.tsx:151-159`

Nếu bạn muốn, mình có thể tiếp tục **vẽ thành 2–3 sequence diagram riêng biệt**:
- **Login + redirect partner**
- **Partner dashboard**
- **Create POI / QR / Buy credit**

---

**User:**

xuất plantUML, chia làm nhiều phần cho đỡ dài

---

**Assistant:**

Dưới đây là bản **PlantUML**, mình chia thành nhiều phần cho đỡ dài.

---

### 1) Login + redirect theo role partner
```plantuml
@startuml
title Partner - Login & Redirect

actor Partner
participant FE as Frontend
participant BE as Backend
database DB as Database

Partner -> FE : Nhập email/password
FE -> BE : POST /login
BE -> DB : Verify account + role
DB --> BE : User info
BE --> FE : JWT + profile

alt role = partner
  FE -> FE : getHomePathForRole(partner)
  FE -> FE : redirect /partner/pois
else role != partner
  FE -> FE : redirect /forbidden
end

@enduml
```

---

### 2) Vào partner layout
```plantuml
@startuml
title Partner - Layout & Navigation

actor Partner
participant FE as Frontend
participant BE as Backend

Partner -> FE : Mở /partner/*
FE -> BE : PrivateRoute check JWT + role
BE --> FE : allow if role=partner

FE -> FE : Render Layout
FE -> FE : chọn partnerNavItems
FE -> FE : brandLabel = "Partner Portal"
FE -> FE : hideSearch = true

@enduml
```

---

### 3) Partner dashboard load dữ liệu
```plantuml
@startuml
title Partner - Dashboard Load Data

actor Partner
participant FE as Frontend
participant BE as Backend
database DB as Database

Partner -> FE : Mở /partner/dashboard
FE -> FE : Mount PartnerDashboard
FE -> FE : build dateParams (7d/30d)

par Overview
  FE -> BE : GET /api/partner/dashboard/overview?from&to
  BE -> BE : Check role partner
  BE -> DB : Query POIs by owner_id
  BE -> DB : Aggregate totalVisits + uniqueUsers
  DB --> BE : Overview result
  BE --> FE : { totalVisits, uniqueUsers }
and Visits
  FE -> BE : GET /api/partner/dashboard/visits?from&to
  BE -> BE : Check role partner
  BE -> DB : Query history by owned POIs
  BE -> DB : Group by date
  DB --> BE : Daily visits
  BE --> FE : [{ date, visits }]
and POI performance
  FE -> BE : GET /api/partner/dashboard/pois?from&to
  BE -> BE : Check role partner
  BE -> DB : Query owned POIs
  BE -> DB : Count visits per POI
  DB --> BE : POI performance
  BE --> FE : [{ poiId, name, visits }]
end

FE -> FE : Render KPI cards + chart + top POIs

@enduml
```

---

### 4) Đổi khoảng thời gian filter
```plantuml
@startuml
title Partner - Change Date Range

actor Partner
participant FE as Frontend
participant BE as Backend
database DB as Database

Partner -> FE : Chọn 7d / 30d
FE -> FE : setRangePreset()
FE -> FE : rebuild dateParams
FE -> FE : reload dashboard

par Reload overview
  FE -> BE : GET /api/partner/dashboard/overview?from&to
  BE -> DB : Re-aggregate data
  DB --> BE : New overview
  BE --> FE : overview
and Reload visits
  FE -> BE : GET /api/partner/dashboard/visits?from&to
  BE -> DB : Re-aggregate visits
  DB --> BE : New visits
  BE --> FE : visits
and Reload pois
  FE -> BE : GET /api/partner/dashboard/pois?from&to
  BE -> DB : Re-aggregate POI stats
  DB --> BE : New POI stats
  BE --> FE : pois
end

@enduml
```

---

### 5) Mua lượt tạo POI
```plantuml
@startuml
title Partner - Buy POI Credits

actor Partner
participant FE as Frontend
participant PayPal
participant BE as Backend
database DB as Database

Partner -> FE : Mở khối "Mua lượt tạo POI"
FE -> FE : Render PayPalScriptProvider + BuyPoiCreditComponent
Partner -> PayPal : Thanh toán

PayPal -> BE : Gửi confirmation/payment result
BE -> DB : Lưu giao dịch + cộng POI credit
DB --> BE : Updated

BE --> FE : Success
FE -> FE : refreshUserProfile()
FE -> FE : toast success

@enduml
```

---

### 6) Tạo POI
```plantuml
@startuml
title Partner - Create POI

actor Partner
participant FE as Frontend
participant BE as Backend
database DB as Database

Partner -> FE : Submit form tạo POI
FE -> BE : POST /poi (kèm data)
BE -> DB : Insert POI
DB --> BE : Created POI

alt user.role = partner
  BE --> FE : Success
  FE -> FE : refreshUserProfile()
  FE -> FE : toast success
  FE -> FE : onSaved + onClose
else lỗi / hết credit
  BE --> FE : Error
  FE -> FE : toast error
end

@enduml
```

---

### 7) Quản lý POI / Tours / QR Codes
```plantuml
@startuml
title Partner - Manage POIs / Tours / QR Codes

actor Partner
participant FE as Frontend
participant BE as Backend
database DB as Database

Partner -> FE : Mở /partner/pois | /partner/tours | /partner/qr-codes
FE -> BE : Load data theo role partner
BE -> BE : Check JWT role = partner

BE -> DB : Query dữ liệu theo owner_id
DB --> BE : Data của partner
BE --> FE : Danh sách POI/Tour/QR

FE -> FE : Hiển thị màn hình quản lý

@enduml
```

---

Nếu bạn muốn, mình có thể gộp lại thành **1 file PlantUML duy nhất** với nhiều `@startuml ... @enduml`, hoặc chỉnh style cho đẹp hơn theo format:
- **sequence**
- **activity**
- **component**