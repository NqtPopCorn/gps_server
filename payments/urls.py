from django.urls import path
from . import views

urlpatterns = [
    # Invoice CRUD
    path('invoices/', views.InvoiceListCreateView.as_view(), name='invoice-list-create'),
    path('invoices/<uuid:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),

    # Credit System
    path('buy-poi-credit/', views.buy_poi_credit, name='buy-poi-credit'),

    # PayPal
    path('paypal/create-order/', views.paypal_create_order, name='paypal-create-order'),
    path('paypal/capture-order/<str:order_id>/', views.paypal_capture_order, name='paypal-capture-order'),
]

