import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        SUCCESS   = "success",   "Success"
        FAILED    = "failed",    "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class Type(models.TextChoices):
        POI_CREDIT           = "poi_credit",           "Mua lượt tạo POI"
        START_TOUR           = "start_tour",           "Thanh toán lượt tạo tour"
        BUY_ACTIVATION_CODE = "buy_activation_code", "Partner mua code activation code"
        GENERAL              = "general",              "Thanh toán khác"

    # Giá cố định cho 1 lượt tạo POI (VND)
    POI_CREDIT_PRICE  = 50_000
    START_TOUR_PRICE  = 10_000
    # Giá cố định cho 1 activation code (VND)
    ACTIVATION_CODE_PER_USE_PRICE = 10_000
    # Số credit cấp cho 1 lần mua
    POI_CREDIT_AMOUNT = 1

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="invoices",
    )
    invoice_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.GENERAL,
        help_text="Loại hóa đơn",
    )
    reference_id = models.CharField(
        max_length=100, help_text="Mã tham chiếu (ex: tourId)", null=True,
    )
    reason = models.CharField(max_length=255, help_text="Mô tả mục đích thanh toán")
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Số tiền (VND)")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_code = models.CharField(
        max_length=100, blank=True, default="",
        help_text="PayPal Order ID",
    )
    paid_at    = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering      = ["-created_at"]
        verbose_name  = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self) -> str:
        return f"Invoice {self.id} – {self.status} – {self.amount} VND"

    # ── helpers ───────────────────────────────────────────────────────────────

    @property
    def is_cancellable(self) -> bool:
        """Only PENDING invoices may be cancelled by the user."""
        return self.status == self.Status.PENDING


# class WebhookEvent(models.Model):
#     """
#     Stores every inbound PayPal webhook payload exactly once.

#     • ``paypal_event_id`` unique constraint  →  idempotency guard.
#       If PayPal re-delivers the same event the view returns 200 immediately.

#     • A Huey task advances PENDING rows to PROCESSED / FAILED.
#       If the server is killed mid-flight the row stays PENDING and the
#       next worker retry re-processes it safely (all handler logic is
#       idempotent – it checks Invoice.status before mutating state).
#     """

#     class Status(models.TextChoices):
#         PENDING    = "pending",    "Pending"
#         PROCESSING = "processing", "Processing"
#         PROCESSED  = "processed",  "Processed"
#         FAILED     = "failed",     "Failed"
#         IGNORED    = "ignored",    "Ignored"

#     paypal_event_id = models.CharField(
#         max_length=100, unique=True, db_index=True,
#         help_text="PayPal's own event UUID – used for idempotency",
#     )
#     event_type = models.CharField(
#         max_length=100,
#         help_text="e.g. PAYMENT.CAPTURE.COMPLETED",
#     )
#     payload      = models.JSONField(help_text="Raw JSON body from PayPal")
#     status       = models.CharField(
#         max_length=20, choices=Status.choices,
#         default=Status.PENDING, db_index=True,
#     )
#     error        = models.TextField(null=True, blank=True)
#     created_at   = models.DateTimeField(auto_now_add=True)
#     processed_at = models.DateTimeField(null=True, blank=True)

#     class Meta:
#         ordering = ["-created_at"]
#         indexes  = [models.Index(fields=["status", "created_at"])]

#     def __str__(self) -> str:
#         return f"{self.event_type} [{self.status}] {self.paypal_event_id}"