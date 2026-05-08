Partner                          Server                        User cuối
  │                                │                               │
  ├─ POST /buy-activation-bundle ──►│ tạo Invoice (PENDING)         │
  │   {tourId, quantity, days}     │ + TourActivationBundle        │
  │                                │                               │
  ├─ POST /paypal/create-order ───►│ tạo PayPal Order              │
  ├─ [approve trên PayPal UI]      │                               │
  ├─ POST /paypal/capture-order ──►│ Invoice → SUCCESS             │
  │                                │ sinh N TourActivationCode     │
  │                                │                               │
  ├─ GET /bundles/{id} ───────────►│ trả list code + QR data       │
  │                                │                               │
  │    [phát code/QR cho user]     │                               │
  │                                │                               │
  │                                │◄── POST /redeem {tourId, code}┤
  │                                │  validate code                │
  │                                │  mark used                    │
  │                                │  upsert UserAvailableTour     │
  │                                │  (cộng dồn days_credit)       │