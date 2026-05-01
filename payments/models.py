import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class Type(models.TextChoices):
        POI_CREDIT = 'poi_credit', 'Mua lượt tạo POI'
        START_TOUR = 'start_tour', 'Thanh toán lượt tạo tour'
        GENERAL = 'general', 'Thanh toán khác'

    # Giá cố định cho 1 lượt tạo POI (VND)
    POI_CREDIT_PRICE = 50_000
    START_TOUR_PRICE = 10_000
    # Số credit cấp cho 1 lần mua
    POI_CREDIT_AMOUNT = 1

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
    )
    invoice_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.GENERAL,
        help_text='Loại hóa đơn',
    )
    reference_id = models.CharField(max_length=100, help_text='Mã tham chiếu (tourId)', null=True)
    reason = models.CharField(max_length=255, help_text='Mô tả mục đích thanh toán')
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text='Số tiền (VND)')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    transaction_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='PayPal Order ID',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'

    def __str__(self) -> str:
        return f'Invoice {self.id} – {self.status} – {self.amount} VND'

class UserAvailableTour(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='available_tours')
    tour = models.ForeignKey('tours.Tour', on_delete=models.CASCADE, related_name='available_users')
    expired_at = models.DateTimeField()

    class Meta:
        unique_together = ('user', 'tour')
    
    def __str__(self) -> str:
        return f'{self.user} - {self.tour}'
    
    @property
    def is_expired(self) -> bool:
        return self.expired_at < timezone.now()

