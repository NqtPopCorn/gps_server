from datetime import timedelta
import json
import logging
import requests

logger = logging.getLogger(__name__)

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import generics, permissions, status, serializers
from rest_framework.decorators import APIView, api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from drf_spectacular import openapi

# Models & Serializers
from tours.models import UserAvailableTour
from payments.models import Invoice
from payments.serializers import (
    InvoiceSerializer,
    InvoiceCreateSerializer,
    BuyPoiCreditSerializer,
    PayForStartTourSerializer,
    BuyActivationBundleSerializer,
    ActivationCodeInfoSerializer,
    RedeemCodeSerializer,
)
from tours.models import Tour, TourActivationCode
from rest_framework.permissions import IsAuthenticated

# Helpers & Tasks
from . import paypal as paypal_helper

# Permissions
from accounts.permissions import IsAdminUser, IsPartnerUser

PRICE_PER_USE_VND = Invoice.ACTIVATION_CODE_PER_USE_PRICE  # 10_000

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


@extend_schema(
    summary="Lấy trạng thái hóa đơn",
    description="API polling để frontend kiểm tra trạng thái xử lý thanh toán.",
    responses={
        200: inline_serializer(
            name="InvoiceStatusResponse",
            fields={
                "status": serializers.CharField(),
            },
        )
    },
    tags=["payments"],
)
class InvoiceStatusView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if getattr(user, "role", None) == "admin":
            return Invoice.objects.all()

        return Invoice.objects.filter(user=user)

    def retrieve(self, request: Request, *args, **kwargs):
        invoice = self.get_object()

        return Response({
            "status": invoice.status,
        })


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
@permission_classes([IsPartnerUser, IsAdminUser])
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
# Partner: Mua Activation Bundle
# ──────────────────────────────────────────────

@extend_schema(
    summary='Partner tạo Invoice mua activation code',
    description=(
        'Partner gọi endpoint này để tạo hóa đơn mua shared activation code cho tour. '
        'Giá cố định 10,000 VND / lượt kích hoạt. '
        'Sau khi thanh toán thành công qua PayPal, 1 TourActivationCode sẽ được sinh ra '
        'với usage_limit = quantity. Partner phân phát code/QR này cho người dùng cuối. '
        'Người dùng redeem code → cộng dồn days_credit vào UserAvailableTour.'
    ),
    request=BuyActivationBundleSerializer,
    responses={201: InvoiceSerializer},
    tags=['payments'],
)
@api_view(['POST'])
@permission_classes([])
def buy_activation_code(request: Request) -> Response:
    ser = BuyActivationBundleSerializer(data=request.data)
    if not ser.is_valid():
        return Response({'error': ser.errors}, status=status.HTTP_400_BAD_REQUEST)

    vd = ser.validated_data
    tour_id     = vd['tour_id']
    quantity    = vd['quantity']
    days_credit = vd.get('days_credit', 1)
    expired = vd.get('code_expired_at', None)

    tour = get_object_or_404(Tour, id=tour_id)

    amount = quantity * PRICE_PER_USE_VND

    code = TourActivationCode.objects.create(tour=tour, usage_limit=quantity)

    invoice = Invoice.objects.create(
        user=request.user,
        invoice_type=Invoice.Type.BUY_ACTIVATION_CODE,
        reason=(
            f'Partner mua {quantity} lượt kích hoạt tour "{tour.name}" '
            f'({days_credit} ngày/lượt)'
        ),
        amount=amount,
        reference_id=code.id,
        expired_at=expired
    )

    invoice.save(update_fields=['reference_id'])

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
        payload_usd = paypal_helper.ensure_usd_payload(payload.copy())
        result = paypal_helper.paypal_request('POST', '/v2/checkout/orders', json=payload_usd)
        # result = paypal_helper.paypal_request('POST', '/v2/checkout/orders', json=payload)
    except requests.HTTPError as e:
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
        'Đặc biệt:\n'
        '- POI_CREDIT: cấp tự động credit cho user.\n'
        '- START_TOUR: upsert UserAvailableTour (7 ngày).\n'
        '- BUY_ACTIVATION_CODE: sinh 1 TourActivationCode dùng chung với usage_limit = quantity.'
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
    # Tìm invoice theo transaction_code hoặc invoiceId trong body
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

                # ── Cấp POI credit ─────────────────────────────────────────────
                if invoice.invoice_type == Invoice.Type.POI_CREDIT and invoice.user:
                    user = invoice.user
                    user.poi_credits = getattr(user, 'poi_credits', 0) + Invoice.POI_CREDIT_AMOUNT
                    user.save(update_fields=['poi_credits'])
                    print(f"[Credit] Cấp {Invoice.POI_CREDIT_AMOUNT} POI credit cho {user.email}. "
                          f"Tổng hiện tại: {user.poi_credits}")

                # ── Upsert UserAvailableTour (START_TOUR) ──────────────────────
                if invoice.invoice_type == Invoice.Type.START_TOUR and invoice.user:
                    tour_available, created = UserAvailableTour.objects.update_or_create(
                        user=invoice.user,
                        tour=get_object_or_404(Tour, id=invoice.reference_id),
                        defaults={
                            'expired_at': timezone.now() + timedelta(days=7)
                        }
                    )
                    print(f"[UserAvailableTour] {'Updated' if not created else 'Created'} {tour_available}")

                # ── Sinh shared TourActivationCode (BUY_ACTIVATION_CODE) ─────
                if invoice.invoice_type == Invoice.Type.BUY_ACTIVATION_CODE and invoice.reference_id:
                    _handle_activation_code(invoice)

            else:
                invoice.status = Invoice.Status.FAILED
                invoice.transaction_code = order_id
                invoice.save(update_fields=['status', 'transaction_code'])

    return Response(result)


# ──────────────────────────────────────────────
# Partner: Lấy thông tin code sau khi thanh toán
# ──────────────────────────────────────────────

@extend_schema(
    summary='Lấy thông tin activation code của invoice',
    description=(
        'Sau khi invoice BUY_ACTIVATION_CODE chuyển sang SUCCESS, '
        'partner dùng endpoint này để lấy shared code + QR data để phân phát cho người dùng.'
    ),
    responses={
        200: ActivationCodeInfoSerializer,
        402: inline_serializer(
            name='InvoiceNotPaidResponse',
            fields={'error': serializers.CharField()},
        ),
        404: inline_serializer(
            name='CodeNotFoundResponse',
            fields={'error': serializers.CharField()},
        ),
    },
    tags=['invoices'],
)
@api_view(['GET'])
@permission_classes([])
def invoice_activation_code(request: Request, pk: str) -> Response:
    invoice = get_object_or_404(Invoice, id=pk, user=request.user)

    if invoice.invoice_type != Invoice.Type.BUY_ACTIVATION_CODE:
        return Response(
            {'error': 'Invoice này không phải loại BUY_ACTIVATION_CODE.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if invoice.status != Invoice.Status.SUCCESS:
        return Response(
            {'error': 'Invoice chưa được thanh toán thành công.'},
            status=status.HTTP_402_PAYMENT_REQUIRED,
        )

    code = TourActivationCode.objects.filter(
        id=invoice.reference_id
    ).first()

    if not code:
        return Response(
            {'error': 'Chưa tìm thấy activation code. Vui lòng thử lại sau.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = ActivationCodeInfoSerializer({
        'code':        code.code,
        'usage_limit': code.usage_limit,
        'used_count':  code.used_count,
        'days_credit': code.days_credit,
        'expired_at':  code.expired_at,
        'remaining':   max(0, code.usage_limit - code.used_count),
    }).data
    return Response(data)

@transaction.atomic
def _handle_activation_code(invoice: Invoice) -> None:

    activation_code_id = invoice.reference_id

    activation_code = (
        TourActivationCode.objects
        .select_for_update()
        .filter(id=activation_code_id, status=TourActivationCode.Status.PENDING)
        .first()
    )

    if not activation_code:
        print(
            f"[BuyActivationCode] "
            f"Activation code {activation_code_id} not found or PAID."
        )
        return

    activation_code.status = (
        TourActivationCode.Status.PAID
    )

    activation_code.save(
        update_fields=["status", "updated_at"]
    )

    print(
        f"[BuyActivationCode] "
        f"Activation code '{activation_code.code}' marked as PAID."
    )