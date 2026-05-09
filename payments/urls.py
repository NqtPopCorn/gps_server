from django.urls import path
from . import views

urlpatterns = [
    # Invoice CRUD
    path('invoices/', views.InvoiceListCreateView.as_view(), name='invoice-list-create'),
    path('invoices/<uuid:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),

    # Credit System
    path('buy-poi-credit/', views.buy_poi_credit, name='buy-poi-credit'),
    path('pay-to-start-tour/', views.pay_to_start_tour, name='pay-to-start-tour'),

    # Partner: mua activation bundle (pay on behalf of end-users)
    path('buy-activation-bundle/', views.buy_activation_code, name='buy-activation-bundle'),

    # # Partner: lấy code sau khi thanh toán thành công
    path('invoices/<uuid:pk>/code/', views.invoice_activation_code, name='invoice-activation-code'),

    # # End-user: redeem code để kích hoạt tour
    # path('redeem/', views.redeem_activation_code, name='redeem-activation-code'),

    # PayPal
    path('paypal/create-order/', views.paypal_create_order, name='paypal-create-order'),
    path('paypal/capture-order/<str:order_id>/', views.paypal_capture_order, name='paypal-capture-order'),
]
