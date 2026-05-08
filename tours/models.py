from datetime import datetime
import uuid
from django.db import models
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
    days_credit = models.IntegerField(default=1, null=False) # 1d
    
    
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
        )

    def __str__(self):
        return f"{self.code} - {self.tour_id}"

    class Meta:
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["expired_at"]),
        ]

class TourActivationRedemption(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    activation_code = models.ForeignKey(
        TourActivationCode,
        on_delete=models.CASCADE
    )

    activated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["activation_code"]),
        ]

