from rest_framework import serializers
from .models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id',
            'user',
            'user_email',
            'invoice_type',
            'reason',
            'amount',
            'status',
            'transaction_code',
            'paid_at',
            'created_at',
            'updated_at',
            'reference_id',
        ]
        read_only_fields = [
            'id',
            'user',
            'user_email',
            'status',
            'transaction_code',
            'paid_at',
            'created_at',
            'updated_at',
            'reference_id',
        ]

    def get_user_email(self, obj: Invoice) -> str | None:
        return obj.user.email if obj.user else None


class InvoiceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['invoice_type', 'reason', 'amount']


class BuyPoiCreditSerializer(serializers.Serializer):
    """Serializer dùng cho endpoint mua 1 lượt tạo POI.
    Frontend chỉ cần POST không cần body – amount và reason tự động điền.
    """
    pass


class PayForStartTourSerializer(serializers.Serializer):
    """Serializer dùng cho endpoint trả tiền để bắt đầu tour."""
    tourId = serializers.CharField(required=True)


# ── Partner: mua activation bundle ────────────────────────────────────────────

class BuyActivationBundleSerializer(serializers.Serializer):
    """
    Partner POST để tạo Invoice mua activation code.

    Giá cố định: 10,000 VND / lượt kích hoạt.
    amount = quantity * 10,000
    """
    tour_id     = serializers.CharField(required=True, help_text="ID của tour")
    quantity    = serializers.IntegerField(
        min_value=1, required=True,
        help_text="Số lượt kích hoạt (usage_limit của code)",
    )
    days_credit = serializers.IntegerField(
        min_value=1, default=1,
        help_text="Số ngày cộng thêm mỗi lần người dùng kích hoạt",
    )
    code_expired_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None,
        help_text="Ngày hết hạn của code (null = không giới hạn)",
    )


# ── Activation code detail (trả về sau khi thanh toán thành công) ─────────────

class ActivationCodeInfoSerializer(serializers.Serializer):
    """Thông tin shared activation code gắn với invoice."""
    code         = serializers.CharField()
    usage_limit  = serializers.IntegerField()
    used_count   = serializers.IntegerField()
    days_credit  = serializers.IntegerField()
    expired_at   = serializers.DateTimeField(allow_null=True)
    remaining    = serializers.IntegerField(help_text="Số lượt còn lại")


# ── End-user: redeem code ──────────────────────────────────────────────────────

class RedeemCodeSerializer(serializers.Serializer):
    """End-user POST code để kích hoạt tour."""
    code = serializers.CharField(required=True, max_length=12, help_text="Mã kích hoạt")

