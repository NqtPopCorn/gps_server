from django.db import models
from django.conf import settings
from accounts.models import User
from pois.models import Poi

class History(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    poi= models.ForeignKey(Poi, on_delete=models.CASCADE)
    tour_id = models.UUIDField(null=True)
    device_id = models.CharField(max_length=255, null=False, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "History"
        indexes = [
            models.Index(fields=["user"]),
        ]