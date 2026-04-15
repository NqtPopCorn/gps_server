from django.urls import path
from pois.views import (
    POIDetailView, POISearchView, POINearbyView,
    AdminPOIListCreateView, AdminPOIDetailView,
    AdminPOILocalizationView, AdminPOILocalizationDeleteView,
    # PartnerPOIListCreateView
    
)

public_urlpatterns = [
    path('nearby', POINearbyView.as_view(), name="poi-nearby"),
    path('<str:slug>', POIDetailView.as_view(), name='poi-detail'),
    path('search/', POISearchView.as_view(), name='poi-search'),
]

partner_urlpatterns = [
    # path('', PartnerPOIListCreateView.as_view(), name='partner-poi-list-create'),
]

admin_urlpatterns = [
    path('', AdminPOIListCreateView.as_view(), name='admin-poi-list-create'),
    path('<str:id>', AdminPOIDetailView.as_view(), name='admin-poi-detail'),
    path('<str:poi_id>/localizations', AdminPOILocalizationView.as_view(), name='admin-poi-localizations'),
    path(
        '<str:poi_id>/localizations/<str:lang_code>',
        AdminPOILocalizationDeleteView.as_view(),
        name='admin-poi-localization-delete',
    ),
]
