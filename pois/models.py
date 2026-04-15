import uuid
from django.db import models
from accounts.models import User

class Poi(models.Model):
    TYPE_CHOICES = (
        ('food', 'Food'),
        ('drink', 'Drink'),
        ('museum', 'Museum'),
        ('park', 'Park'),
        ('historical', 'Historical'),
        ('shopping', 'Shopping'),
        ('other', 'Other'),
    )

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )

    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4, editable=False)
    default_lang = models.CharField(max_length=10, default='vi')
    image = models.URLField(max_length=500, null=True, blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    radius = models.IntegerField(default=50) # In meters
    latitude = models.FloatField()
    longitude = models.FloatField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    slug = models.SlugField(unique=True, max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, default=None)

    class Meta:
        indexes = [
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.slug} - {self.type}"

class LocalizedData(models.Model):
    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4, editable=False)
    poi = models.ForeignKey(Poi, on_delete=models.CASCADE, related_name='localized_data')
    lang_code = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    audio = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['poi', 'lang_code'], name='unique_poi_lang')
        ]

    def __str__(self):
        return f"{self.poi.slug} - {self.lang_code}"


class AudioPermission(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    poi_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "AudioPermission"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "poi_id"],
                name="unique_user_poi_permission"
            )
        ]
        indexes = [
            models.Index(fields=["user", "poi_id"]),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.poi_id}"