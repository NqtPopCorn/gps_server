# PayPal Sandbox Integration
## Django Backend + TypeScript Frontend

---

## 🧠 Overview Flow

1. Frontend gọi API backend `/create-order`
2. Backend tạo order với PayPal
3. Frontend render PayPal button
4. User approve thanh toán
5. Frontend gọi `/capture-order`
6. Backend capture payment và lưu DB

---

## 1️⃣ Setup PayPal Sandbox

- Truy cập: https://developer.paypal.com
- Tạo:
  - Business Account
  - Personal Account

- Lấy thông tin:
  - `CLIENT_ID`
  - `SECRET`

- Tài khoản sandbox: nằm trong tab Testing Tools/Sandbox Accounts (Type Personal)

---

## 2️⃣ Django Backend

### 📦 Install dependencies

```bash
pip install requests python-dotenv django-cors-headers
```

### 🔑 Environment Variables
PAYPAL_CLIENT_ID=your_client_id
PAYPAL_SECRET=your_secret
PAYPAL_BASE=https://api-m.sandbox.paypal.com

### ⚙️ paypal.py (Helper)

```python
# backend/payments/paypal.py
import os
from typing import Any, Dict
import requests
from dotenv import load_dotenv

load_dotenv()

PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID', '')
PAYPAL_SECRET = os.getenv('PAYPAL_SECRET', '')
PAYPAL_BASE = os.getenv('PAYPAL_BASE', 'https://api-m.sandbox.paypal.com')
VND_TO_USD_RATE = float(os.getenv('PAYPAL_VND_TO_USD_RATE', '25000'))

def get_access_token() -> str:
    url = f"{PAYPAL_BASE}/v1/oauth2/token"
    response = requests.post(
        url,
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return str(data.get('access_token', ''))

def paypal_request(method: str, path: str, json: Dict[str, Any] | None = None) -> Dict[str, Any]:
    token = get_access_token()
    url = f"{PAYPAL_BASE}{path}"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {token}",
    }
    resp = requests.request(method, url, headers=headers, json=json, timeout=20)
    if resp.ok:
        return resp.json()
    # Log lỗi chi tiết
    try:
        err = resp.json()
        print(f"[PayPal] {resp.status_code} {resp.reason} {method} {path}")
        print(f"Body: {err}")
    except Exception:
        print(f"[PayPal] {resp.status_code} {resp.reason} {method} {path}")
        print(f"Text: {resp.text}")
    resp.raise_for_status()
    return {}

def ensure_usd_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Chuyển VND -> USD nếu cần."""
    pu = payload.get('purchase_units', [])
    if not pu:
        return payload
    amount = pu[0].get('amount', {})
    if amount.get('currency_code') == 'VND':
        try:
            vnd = float(amount.get('value', '0'))
            usd = round(vnd / VND_TO_USD_RATE, 2)
            amount['currency_code'] = 'USD'
            amount['value'] = f"{usd:.2f}"
            print(f"[PayPal] {vnd} VND -> {usd} USD")
        except Exception as e:
            print(f"[PayPal] convert fail: {e}")
    return payload
```

### 💳 Create Order API 

```python
# backend/payments/views.py
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def paypal_create_order(request):
    invoice_id = request.data.get('invoiceId', '')
    if not invoice_id:
        return Response({'error': 'invoiceId is required.'}, status=400)

    invoice = get_object_or_404(Invoice, id=invoice_id)
    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [{
            'reference_id': str(invoice.id),
            'description': invoice.reason,
            'amount': {
                'currency_code': 'VND',
                'value': str(int(invoice.amount)),
            },
        }],
    }

    # Thử VND trước, nếu 422 thì chuyển USD
    try:
        result = paypal_request('POST', '/v2/checkout/orders', json=payload)
    except requests.HTTPError as e:
        if e.response and e.response.status_code == 422:
            payload_usd = ensure_usd_payload(payload.copy())
            result = paypal_request('POST', '/v2/checkout/orders', json=payload_usd)
        else:
            raise

    order_id = result.get('id', '')
    if order_id:
        invoice.transaction_code = order_id
        invoice.save(update_fields=['transaction_code'])
    return Response(result)
```

### ✅ Capture Order API 

```python
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def paypal_capture_order(request, order_id: str):
    invoice = Invoice.objects.filter(transaction_code=order_id).first()
    if not invoice:
        invoice_id = request.data.get('invoiceId', '')
        if invoice_id:
            invoice = Invoice.objects.filter(id=invoice_id).first()

    result = paypal_request('POST', f"/v2/checkout/orders/{order_id}/capture")
    status = result.get('status', '')
    if invoice:
        if status == 'COMPLETED':
            invoice.status = Invoice.Status.SUCCESS
            invoice.paid_at = timezone.now()
            invoice.transaction_code = order_id
            invoice.save(update_fields=['status', 'paid_at', 'transaction_code'])
        else:
            invoice.status = Invoice.Status.FAILED
            invoice.transaction_code = order_id
            invoice.save(update_fields=['status', 'transaction_code'])
    return Response(result)
```

### 🔗 urls.py

```python
# backend/payments/urls.py
urlpatterns = [
    path('invoices/', views.InvoiceListCreateView.as_view()),
    path('invoices/<uuid:pk>/', views.InvoiceDetailView.as_view()),
    path('paypal/create-order/', views.paypal_create_order),
    path('paypal/capture-order/<str:order_id>/', views.paypal_capture_order),
]
```

### 🌐 CORS Config 

```python
# backend/config/settings.py
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
# Hoặc tạm thởi allow all:
# CORS_ALLOW_ALL_ORIGINS = True
```

---

## 3️⃣ Frontend (React + TypeScript)

### 📦 Install dependency

```bash
npm install @paypal/react-paypal-js
```

### 🔧 PayPal Provider 

```tsx
import { PayPalScriptProvider } from '@paypal/react-paypal-js';

export default function App() {
  const paypalClientId = import.meta.env.VITE_PAYPAL_CLIENT_ID || '';
  // Dùng USD vì sandbox thường không hỗ trợ VND
  const paypalCurrency = 'USD';

  return (
    <PayPalScriptProvider options={{ 'client-id': paypalClientId, currency: paypalCurrency }}>
      <BrowserRouter>
        {/* Routes */}
      </BrowserRouter>
    </PayPalScriptProvider>
  );
}
```

### � Checkout Component 

```tsx
import { PayPalButtons } from '@paypal/react-paypal-js';
import { paypalCreateOrder, paypalCaptureOrder, getInvoiceById } from '../services/api';

export default function InvoiceDetail() {
  // ...state

  return (
    <PayPalButtons
      style={{ layout: 'vertical', shape: 'pill', label: 'pay' }}
      createOrder={async () => {
        if (!invoice) throw new Error('Missing invoice');
        const orderId = await paypalCreateOrder(invoice.id);
        return orderId;
      }}
      onApprove={async (data: { orderID?: string }) => {
        if (!invoice) return;
        try {
          setPaying(true);
          await paypalCaptureOrder(String(data.orderID || ''), invoice.id);
          const refreshed = await getInvoiceById(invoice.id);
          setInvoice(refreshed);
        } catch (e) {
          setError(getApiErrorMessage(e));
        } finally {
          setPaying(false);
        }
      }}
      onError={(err: unknown) => {
        console.error(err);
        setError('Không thể khởi tạo PayPal. Vui lòng thử lại.');
      }}
    />
  );
}
```

### � API helpers 

```ts
export const paypalCreateOrder = async (invoiceId: string): Promise<string> => {
  const { data } = await apiClient.post<{ id: string }>(
    '/payments/paypal/create-order/',
    { invoiceId }
  );
  return data.id;
};

export const paypalCaptureOrder = async (orderId: string, invoiceId?: string): Promise<unknown> => {
  const { data } = await apiClient.post(
    `/payments/paypal/capture-order/${orderId}/`,
    invoiceId ? { invoiceId } : {}
  );
  return data;
};
```

### 🌍 Environment Variables 

```env
VITE_PAYPAL_CLIENT_ID=your_client_id
VITE_API_URL=http://localhost:8000/api
```

---

## 4️⃣ Những lỗi thường gặp

### ❌ CORS

Django:
```bash
pip install django-cors-headers
# settings.py
CORS_ALLOW_ALL_ORIGINS = True
```

### ❌ Currency không hỗ trợ

- PayPal sandbox thường không hỗ trợ VND → fallback sang USD (đã có sẵn helper `ensure_usd_payload`)

### ❌ Không capture → không nhận tiền

- PayPal chỉ giữ tiền khi chưa capture. Phải gọi `/capture-order`.

### ❌ 422 Unprocessable Entity

- Kiểm tra response body từ PayPal (backend đã log chi tiết). Thường là `CURRENCY_NOT_SUPPORTED` hoặc `INVALID_AMOUNT`.

---

## 5️⃣ Best Practices

- ✅ Luôn verify ở backend, KHÔNG tin frontend
- ✅ Lưu DB: `order_id`, `amount`, `status`, `user_id`
- ✅ Xử lý fallback VND → USD nếu sandbox không hỗ trợ
- ✅ Dùng `PayPalScriptProvider` ở root app
- ✅ Hiển thị loading/error rõ ràng trên UI
- ✅ Ghi log chi tiết lỗi từ PayPal để debug

---

## 6️⃣ Test Checklist

- [ ] Backend `.env` có `PAYPAL_CLIENT_ID` & `PAYPAL_SECRET`
- [ ] Frontend `.env` có `VITE_PAYPAL_CLIENT_ID`
- [ ] Django CORS cho phép origin frontend
- [ ] Tạo invoice PENDING trên UI
- [ ] Render PayPal button (không lỗi 404/403)
- [ ] Bấm nút → popup PayPal → approve
- [ ] Backend capture thành công → invoice status SUCCESS
- [ ] UI refresh lại trạng thái hóa đơn

---