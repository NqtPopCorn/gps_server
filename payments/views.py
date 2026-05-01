from payments.serializers import PayForStartTourSerializer
from payments.models import UserAvailableTour
from tours.models import Tour
import requests
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from drf_spectacular import openapi

from .models import Invoice
from .serializers import InvoiceSerializer, InvoiceCreateSerializer, BuyPoiCreditSerializer
from . import paypal as paypal_helper
from rest_framework import serializers

# Đảm bảo bạn đã import IsPartnerUser từ module tương ứng trong project
from accounts.permissions import IsPartnerUser



# ──────────────────────────────────────────────
# Invoice CRUD
# ──────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        summary="Lấy danh sách hóa đơn",
        description="Trả về danh sách hóa đơn của user hiện tại. Nếu role là admin sẽ trả về toàn bộ hóa đơn trên hệ thống.",
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
# Credit System – Mua lượt tạo POI
# ──────────────────────────────────────────────

@extend_schema(
    summary='Tạo Invoice để mua 1 lượt tạo POI (50,000 VND)',
    description=(
        'Partner gọi endpoint này để tạo hóa đơn mua POI credit. '
        'Sau đó dùng invoiceId trả về để gọi /paypal/create-order/ → /paypal/capture-order/. '
        'Khi capture thanh toán PayPal thành công, poi_credits của user sẽ tự động +1.'
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
        'Sau đó dùng invoiceId trả về để gọi /paypal/create-order/ → /paypal/capture-order/. '
        'Khi capture thanh toán PayPal thành công, upsert UserAvailableTour.'
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
# PayPal – Create Order
# ──────────────────────────────────────────────

@extend_schema(
    summary='Tạo PayPal Order cho invoice',
    description=(
        'Tạo Order trên PayPal API'
    ),
    request=inline_serializer(
        name='PaypalCreateOrderRequest111',
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

    # Thử VND trước; nếu PayPal trả 422 thì fallback sang USD (hữu ích trên môi trường Sandbox)
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


# ──────────────────────────────────────────────
# PayPal – Capture Order
# ──────────────────────────────────────────────

@extend_schema(
    summary='Capture PayPal Order sau khi user approve',
    description=(
        'Capture payment từ PayPal thông qua order_id. Cập nhật trạng thái invoice thành SUCCESS/FAILED. '
        'Đặc biệt, nếu hóa đơn thuộc loại POI_CREDIT, cấp tự động credit cho user tương ứng.'
    ),
    request=inline_serializer(
        name='PaypalCaptureOrderRequest',
        fields={'invoiceId': serializers.UUIDField()},
    ),
    responses={200: openapi.OpenApiTypes.OBJECT},
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def paypal_capture_order(request: Request, order_id: str) -> Response:
    # Tìm invoice theo transaction_code (đã lưu ở bước create_order) hoặc invoiceId trong body gửi lên
    invoice = Invoice.objects.filter(transaction_code=order_id).first()
    if not invoice:
        invoice_id = request.data.get('invoiceId', '')
        if invoice_id:
            invoice = Invoice.objects.filter(id=invoice_id, user=request.user).first()

    result = paypal_helper.paypal_request('POST', f"/v2/checkout/orders/{order_id}/capture")
    pay_status = result.get('status', '')

    if invoice:
        with transaction.atomic():
            if pay_status == 'COMPLETED':
                invoice.status = Invoice.Status.SUCCESS
                invoice.paid_at = timezone.now()
                invoice.transaction_code = order_id
                invoice.save(update_fields=['status', 'paid_at', 'transaction_code'])

                # ── Cấp POI credit nếu đây là hóa đơn mua lượt ──
                if invoice.invoice_type == Invoice.Type.POI_CREDIT and invoice.user:
                    user = invoice.user
                    # Tránh gán sai type, nên dùng toán tử cộng dồn
                    user.poi_credits = getattr(user, 'poi_credits', 0) + Invoice.POI_CREDIT_AMOUNT
                    user.save(update_fields=['poi_credits'])
                    print(f"[Credit] Cấp {Invoice.POI_CREDIT_AMOUNT} POI credit cho {user.email}. "
                          f"Tổng hiện tại: {user.poi_credits}")

                # Xử lý lưu avalable tour
                if invoice.invoice_type == Invoice.Type.START_TOUR and invoice.user:
                    tour_available, created = UserAvailableTour.objects.update_or_create(
                        user=invoice.user,
                        tour=get_object_or_404(Tour, id=invoice.reference_id),
                        defaults={
                            'expired_at': timezone.now() + timezone.timedelta(days=7)
                        }
                    )
                    print(f"[UserAvailableTour] {'Updated' if not created else 'Created'} {tour_available}")

            else:
                invoice.status = Invoice.Status.FAILED
                invoice.transaction_code = order_id
                invoice.save(update_fields=['status', 'transaction_code'])

    return Response(result)