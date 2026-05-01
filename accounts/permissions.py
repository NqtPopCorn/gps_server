from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
import uuid


class IsPartnerUser(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role == 'partner'


class IsAdminUser(BasePermission):
    """Allows access only to users with role='admin'."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role == 'admin'

class HasDeviceId(BasePermission):
    def has_permission(self, request, view):
        device_id = request.headers.get("X-Device-Id", None)

        if not device_id:
            raise PermissionDenied("Missing X-Device-Id header")

        # validate UUID
        try:
            uuid.UUID(device_id)
        except ValueError:
            raise PermissionDenied("Invalid device id format")

        request.device_id = device_id
        return True
