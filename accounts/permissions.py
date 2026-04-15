from rest_framework.permissions import BasePermission


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
