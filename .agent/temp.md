NEW ENDPOINTs

ENDPOINT: /api/payments/buy-activation-bundle/
- desc: Partner gọi endpoint này để tạo hóa đơn mua shared activation code cho tour. Giá cố định 10,000 VND / lượt kích hoạt. Sau khi thanh toán thành công qua PayPal, 1 TourActivationCode sẽ được sinh ra với usage_limit = quantity. Partner phân phát code/QR này cho người dùng cuối. Người dùng redeem code → cộng dồn days_credit vào UserAvailableTour.
- request body Schema: {
  "tour_id": "string",
  "quantity": 1,
  "days_credit": 1,
  "code_expired_at": "2026-05-09T02:54:26.424Z"
}
- Response Schema: {
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "user": "string",
  "user_email": "string",
  "invoice_type": "poi_credit",
  "reason": "string",
  "amount": "-96.44",
  "status": "pending",
  "transaction_code": "string",
  "paid_at": "2026-05-09T02:55:18.512Z",
  "created_at": "2026-05-09T02:55:18.512Z",
  "updated_at": "2026-05-09T02:55:18.512Z",
  "reference_id": "string"
}

ENDPOINT: /api/payments/invoices/{id}/code/
- desc: Sau khi invoice BUY_ACTIVATION_CODE chuyển sang SUCCESS, partner dùng endpoint này để lấy shared code + QR data để phân phát cho người dùng.
- Response Schema: {
  "code": "string",
  "usage_limit": 0,
  "used_count": 0,
  "days_credit": 0,
  "expired_at": "2026-05-09T02:59:04.269Z",
  "remaining": 0
}

