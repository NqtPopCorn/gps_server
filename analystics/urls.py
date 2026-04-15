from django.urls import path
from analystics.views import (
    AdminOverviewView,
    AdminVisitsView,
    AdminRevenueView,
    AdminTopPoisView,
    AdminTopToursView,
    AdminActiveUsersView,
    PartnerOverviewView,
    PartnerVisitsView,
    PartnerPoisPerformanceView,
)

# Admin dashboard endpoints  →  /api/admin/dashboard/...
admin_urlpatterns = [
    path("overview", AdminOverviewView.as_view(), name="admin-dashboard-overview"),
    path("visits", AdminVisitsView.as_view(), name="admin-dashboard-visits"),
    path("revenue", AdminRevenueView.as_view(), name="admin-dashboard-revenue"),
    path("top-pois", AdminTopPoisView.as_view(), name="admin-dashboard-top-pois"),
    path("top-tours", AdminTopToursView.as_view(), name="admin-dashboard-top-tours"),
    path("users-active", AdminActiveUsersView.as_view(), name="admin-dashboard-users-active"),
]

# Partner dashboard endpoints  →  /api/partner/dashboard/...
partner_urlpatterns = [
    path("overview", PartnerOverviewView.as_view(), name="partner-dashboard-overview"),
    path("visits", PartnerVisitsView.as_view(), name="partner-dashboard-visits"),
    path("pois", PartnerPoisPerformanceView.as_view(), name="partner-dashboard-pois"),
]
