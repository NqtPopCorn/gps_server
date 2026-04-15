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

