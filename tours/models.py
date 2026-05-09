from datetime import datetime
import uuid
from django.db import models
from jsonschema import ValidationError
from config import settings
from pois.models import Poi
from django.utils import timezone
from accounts.models import User

STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('published', 'Published'),
]

class Tour(models.Model):
    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    image = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    partner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class TourPoint(models.Model):
    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4, editable=False)
    poi = models.ForeignKey(Poi, on_delete=models.CASCADE, related_name='tour_points')
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='tour_points')
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tour', 'position'], name='unique_tour_position')
        ]
        ordering = ['position']

    def __str__(self):
        return f"{self.tour.name} - Point {self.position} ({self.poi.slug})"

import secrets
import string
from datetime import timedelta
def generate_code(length=8):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))
class TourActivationCode(models.Model):
    class Status(models.TextChoices):
        # Có thể đổi thành ENABLE, DISABLE
        PENDING   = "pending",   "Pending"
        PAID = "paid", "Paid"

    id = models.AutoField(primary_key=True)
    code = models.CharField(
        max_length=12,
        unique=True,
        default=generate_code
    )   

    tour = models.ForeignKey(
        Tour,
        on_delete=models.CASCADE,
        related_name='activation_codes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.IntegerField(default=1, null=False)
    used_count = models.IntegerField(default=0)
    days_credit = models.IntegerField(default=7, null=False) 
    status = models.CharField(choices=Status.choices, default=Status.PENDING, max_length=20)
    
    def is_expired(self):
        if self.expired_at is None:
            return False
        return timezone.now() > self.expired_at
    
    def refresh_code(self, valid_seconds=30):
        """Hàm tiện ích để tạo mã mới và cập nhật thời gian"""
        self.code = generate_code()
        self.expired_at = timezone.now() + timedelta(seconds=valid_seconds)
        self.save(update_fields=['code', 'expired_at', 'updated_at'])

    def can_use(self):
        return (
            not self.is_expired()
            and self.used_count < self.usage_limit
            and self.status == self.Status.PAID
        )
    
    def validate_redeemable(self, now):
        if self.status == self.Status.PENDING:
            raise ValidationError("Code chưa thanh toán")

        if self.expired_at and self.expired_at < now:
            raise ValidationError("Code hết hạn")

        if (
            self.usage_limit is not None
            and self.used_count >= self.usage_limit
        ):
            raise ValidationError("Code đã dùng hết")

    def __str__(self):
        return f"{self.code} - {self.tour_id}"

    class Meta:
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["expired_at"]),
        ]

class TourActivationLog(models.Model):
    device_id = models.CharField(
        max_length=255,
        null=False,
        blank=False,
    )

    raw_code = models.CharField(
        max_length=12,
    )   

    activated_at = models.DateTimeField(auto_now_add=True)

    granted_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Thời điểm hết hạn của "
            "UserAvailableTour sau khi redeem"
        ),
    )

    class Meta:

        indexes = [
            models.Index(fields=["device_id"]),
            models.Index(fields=["raw_code"]),
            models.Index(fields=["activated_at"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["device_id", "raw_code"],
                name="unique_device_activation"
            )
        ]

        


class UserAvailableTour(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="available_tours",
        null=True,
        blank=True,
    )

    tour = models.ForeignKey(
        "tours.Tour",
        on_delete=models.CASCADE,
        related_name="available_users",
    )

    # dành cho guest user
    device_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    expired_at = models.DateTimeField()

    class Meta:
        constraints = [
            # user + tour unique
            # models.UniqueConstraint(
            #     fields=["user", "tour"],
            #     name="unique_user_tour",
            # ),

            # # device_id + tour unique
            # models.UniqueConstraint(
            #     fields=["device_id", "tour"],
            #     name="unique_device_tour",
            # ),

            # phải có ít nhất user hoặc device_id
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False) |
                    models.Q(device_id__isnull=False)
                ),
                name="require_user_or_device",
            ),
        ]

    def __str__(self):
        if self.user:
            owner = self.user
        else:
            owner = f"guest:{self.device_id}"

        return f"{owner} - {self.tour}"

    @property
    def is_expired(self) -> bool:
        return self.expired_at < timezone.now()



