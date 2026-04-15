from tours.views import TourActivationCodeView
from django.urls import path
from tours.views import (
    TourListView, TourDetailView, TourActivateView,
    AdminTourListCreateView, AdminTourDetailView,
    AdminTourPointListCreateView, AdminTourPointDeleteView, AdminTourPointUpdateView
)

public_urlpatterns = [
    path('', TourListView.as_view(), name='tour-list'),
    path('<str:id>', TourDetailView.as_view(), name='tour-detail'),
    # path('<str:tour_id>/activate', TourActivateView.as_view(), name='tour-activate'),
    path('<str:tour_id>/qr-data', TourActivationCodeView.as_view(), name='tour-qr-data'),
    path('<str:tour_id>/activate/', TourActivateView.as_view(), name='tour-activate'),
]

admin_urlpatterns = [
    path('', AdminTourListCreateView.as_view(), name='admin-tour-list-create'),
    path('<str:id>', AdminTourDetailView.as_view(), name='admin-tour-detail'),
    path('<str:tour_id>/points', AdminTourPointListCreateView.as_view(), name='admin-tour-points'),
    path('<str:tour_id>/points/<str:point_id>', AdminTourPointDeleteView.as_view(), name='admin-tour-point-delete'),
    path('<str:tour_id>/points-position', AdminTourPointUpdateView.as_view(), name='admin-tour-point-position'),
]
