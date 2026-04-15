"""batch/apps.py"""
from django.apps import AppConfig


class BatchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "batch"
    verbose_name = "Batch Processing"
