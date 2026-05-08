import json
from venv import logger
import requests

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import generics, permissions, status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from drf_spectacular import openapi

# Models & Serializers
from payments.models import Invoice, UserAvailableTour, WebhookEvent
from payments.serializers import (
    InvoiceSerializer, 
    InvoiceCreateSerializer, 
    BuyPoiCreditSerializer, 
    PayForStartTourSerializer
)
from tours.models import Tour

# Helpers & Tasks
from . import paypal as paypal_helper
from .tasks import process_webhook_event

# Permissions
from accounts.permissions import IsPartnerUser


# ──────────────────────────────────────────────
# Invoice CRUD
# ──────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        summary="Lấy danh sách hóa đơn",
        description="Trả về danh sách hóa đơn của user hiện tại. Nếu role là admin sẽ trả về toàn bộ.",
        responses={200: InvoiceSerializer(many=True)},
        tags=['invoices']
    ),
    post=extend_schema(
        summary="Tạo hóa đơn mới",
        description="Tạo một hóa đơn thủ công (ví dụ: thanh toán dịch vụ chung) với trạng thái mặc định là PENDING.",
        request=InvoiceCreateSerializer,
        responses={201: InvoiceSerializer},
        tags=['invoices']
    )
)
class InvoiceListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InvoiceCreateSerializer
        return InvoiceSerializer

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'admin':
            return Invoice.objects.all()
        return Invoice.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema_view(
    get=extend_schema(
        summary="Lấy chi tiết một hóa đơn",
        description="Trả về thông tin chi tiết của một hóa đơn cụ thể dựa vào UUID do user sở hữu.",
        responses={200: InvoiceSerializer},
        tags=['invoices']
    )
)
class InvoiceDetailView(generics.RetrieveAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'admin':
            return Invoice.objects.all()
        return Invoice.objects.filter(user=user)


# ──────────────────────────────────────────────
# Credit System & Tours
# ──────────────────────────────────────────────

@extend_schema(
    summary='Tạo Invoice để mua 1 lượt tạo POI (50,000 VND)',
    description=(
        'Partner gọi endpoint này để tạo hóa đơn mua POI credit. '
        'Sau đó dùng invoiceId trả về để gọi /paypal/create-order/ → /paypal/capture-order/. '
        'Webhook sẽ tự động cộng credit khi thanh toán thành công.'
    ),
    request=BuyPoiCreditSerializer,
    responses={201: InvoiceSerializer},
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([IsPartnerUser])
def buy_poi_credit(request: Request) -> Response:
    invoice = Invoice.objects.create(
        user=request.user,
        invoice_type=Invoice.Type.POI_CREDIT,
        reason='Mua 1 lượt tạo POI',
        amount=Invoice.POI_CREDIT_PRICE,
    )
    return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary='Tạo Invoice để thanh toán lượt start tour',
    description=(
        'User gọi endpoint này để tạo hóa đơn thanh toán lượt start tour. '
        'Sau đó dùng invoiceId trả về để gọi /paypal/create-order/ → /paypal/capture-order/.'
    ),
    request=PayForStartTourSerializer,
    responses={201: InvoiceSerializer},
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def pay_to_start_tour(request: Request) -> Response:
    tour_id = request.data.get('tourId', '')
    if not tour_id:
        return Response({'error': 'tourId is required.'}, status=status.HTTP_400_BAD_REQUEST)
    
    tour = get_object_or_404(Tour, id=tour_id)

    invoice = Invoice.objects.create(
        user=request.user,
        invoice_type=Invoice.Type.START_TOUR,
        reason=f'Start Tour {tour.id}',
        amount=Invoice.START_TOUR_PRICE,
        reference_id=tour_id
    )
    return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────
# PayPal – Create & Capture Order
# ──────────────────────────────────────────────

@extend_schema(
    summary='Tạo PayPal Order cho invoice',
    request=inline_serializer(
        name='PaypalCreateOrderRequest',
        fields={'invoiceId': serializers.UUIDField()},
    ),
    responses={
        200: openapi.OpenApiTypes.OBJECT,
        400: openapi.OpenApiTypes.OBJECT
    },
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def paypal_create_order(request: Request) -> Response:
    invoice_id = request.data.get('invoiceId', '')
    if not invoice_id:
        return Response({'error': 'invoiceId is required.'}, status=status.HTTP_400_BAD_REQUEST)

    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)

    if invoice.status == Invoice.Status.SUCCESS:
        return Response({'error': 'Invoice đã được thanh toán.'}, status=status.HTTP_400_BAD_REQUEST)

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

    try:
        result = paypal_helper.paypal_request('POST', '/v2/checkout/orders', json=payload)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 422:
            payload_usd = paypal_helper.ensure_usd_payload(payload.copy())
            result = paypal_helper.paypal_request('POST', '/v2/checkout/orders', json=payload_usd)
        else:
            raise

    order_id = result.get('id', '')
    if order_id:
        invoice.transaction_code = order_id
        invoice.save(update_fields=['transaction_code'])

    return Response(result)


@extend_schema(
    summary='Capture PayPal Order sau khi user approve',
    description=(
        'Endpoint này chỉ trigger việc capture từ phía frontend. '
        'Toàn bộ logic cấp credit, cập nhật DB được xử lý bất đồng bộ thông qua Webhook.'
    ),
    responses={200: openapi.OpenApiTypes.OBJECT},
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def paypal_capture_order(request: Request, order_id: str) -> Response:
    """
    Vì hệ thống đã chuyển sang dùng Webhook & Background Tasks, 
    endpoint này chỉ đảm nhiệm việc gọi API capture. Nó không cập nhật DB.
    """
    result = paypal_helper.paypal_request('POST', f"/v2/checkout/orders/{order_id}/capture")
    return Response(result)


# ──────────────────────────────────────────────
# PayPal – Webhook 
# ──────────────────────────────────────────────

@extend_schema(
    summary='PayPal Webhook Endpoint',
    description='Nhận events từ PayPal, lưu DB an toàn và đẩy vào Huey để xử lý bất đồng bộ.',
    responses={200: openapi.OpenApiTypes.OBJECT},
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])  # Webhook luôn public, bảo mật dựa vào signature
def paypal_webhook(request: Request) -> Response:
    headers = dict(request.headers)
    raw_body = request.body

    # 1. Xác thực nguồn gốc (Chữ ký PayPal)
    is_valid = paypal_helper.verify_webhook_signature(headers, raw_body)
    if not is_valid:
        return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

    # 2. Phân tích Payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return Response({"error": "Invalid JSON body"}, status=status.HTTP_400_BAD_REQUEST)

    paypal_event_id = payload.get('id')
    event_type = payload.get('event_type')

    if not paypal_event_id or not event_type:
        return Response({"error": "Missing event data"}, status=status.HTTP_400_BAD_REQUEST)

    # 3. Store-and-Forward: Lưu event (Idempotency) và enqueue task
    event, created = WebhookEvent.objects.get_or_create(
        paypal_event_id=paypal_event_id,
        defaults={
            "event_type": event_type,
            "payload": payload,
            "status": WebhookEvent.Status.PENDING,
        }
    )

    # Nếu sự kiện là mới hoặc trước đó bị kẹt/lỗi, đẩy vào hàng đợi Huey
    if created or event.status in [WebhookEvent.Status.PENDING, WebhookEvent.Status.FAILED]:
        process_webhook_event(event.id)  # Gửi ID để task lấy record từ DB

    # Luôn trả về 200 OK ngay lập tức cho PayPal
    # logger.info("INFO: return cho paypal")
    return Response({"status": "received"}, status=status.HTTP_200_OK)
