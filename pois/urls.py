from django.urls import path
from pois.views import (
    POIDetailView, POISearchView,
    POIByH3CellsView,                          # ← new
    AdminPOIListCreateView, AdminPOIDetailView,
    AdminPOILocalizationView, AdminPOILocalizationDeleteView,
    # PartnerPOIListCreateView
)

public_urlpatterns = [
    path('search/',     POISearchView.as_view(),        name='poi-search'),
    path('h3-batch/',   POIByH3CellsView.as_view(),    name='poi-h3-batch'),  # ← new
    path('<str:slug>',  POIDetailView.as_view(),        name='poi-detail'),   # keep last – catch-all
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