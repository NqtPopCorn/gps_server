from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

import accounts.urls as auth_urls
import pois.urls as poi_urls
# import config.routing as monitor_routing

import tours.urls as tour_urls
import history.urls as history_urls
import analystics.urls as analytics_urls
import monitor.urls as monitor_urls

urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # API schema & Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Auth endpoints: /api/auth/register, /api/auth/login
    path('api/auth/', include(auth_urls)),

    # Public POI endpoints: /api/pois/nearby, /api/pois/<id>
    path('api/pois/', include(poi_urls.public_urlpatterns)),

    # Public Tour endpoints: /api/tours/, /api/tours/<id>
    path('api/tours/', include(tour_urls.public_urlpatterns)),
 
    # Public History endpoints: /api/history/create, /api/history/list
    path('api/history/', include(history_urls)),

    # Admin POI endpoints: /api/admin/pois/...
    path('api/admin/pois/', include(poi_urls.admin_urlpatterns)),

    # Admin Tour endpoints: /api/admin/tours/...
    path('api/admin/tours/', include(tour_urls.admin_urlpatterns)),

    # NLS endpoints
    path('api/admin/nls/', include('nls.urls')),

    # Partner POI endpoints: /api/partner/pois/...
    # path('api/partner/pois/', include(poi_urls.partner_urlpatterns)),

    # Payments & PayPal endpoints: /api/payments/...
    path('api/payments/', include('payments.urls')),

    # Admin dashboard analytics: /api/admin/dashboard/...
    path('api/admin/dashboard/', include(analytics_urls.admin_urlpatterns)),

    # Partner dashboard analytics: /api/partner/dashboard/...
    path('api/partner/dashboard/', include(analytics_urls.partner_urlpatterns)),

    path('api/monitor/', include(monitor_urls)),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
