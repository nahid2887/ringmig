"""
URL configuration for core project.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Swagger/OpenAPI Schema
schema_view = get_schema_view(
    openapi.Info(
        title="Ring Mig API",
        default_version='v1',
        description="Ring Mig API - Connect as a Talker or Listener",
        terms_of_service="https://www.ringmig.com/terms/",
        contact=openapi.Contact(email="support@ringmig.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Root redirect
    path('', RedirectView.as_view(url='swagger/', permanent=False)),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # API Endpoints
    path('api/auth/', include('users.urls')),
    path('api/listener/', include('listener.urls')),
    path('api/talker/', include('talker.urls')),
    path('api/chat/', include('chat.urls')),
    path('api/payment/', include('payment.urls')),
    
    # Swagger UI
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('swagger.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger.yaml', schema_view.without_ui(cache_timeout=0), name='schema-yaml'),
    
    # ReDoc Alternative UI
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

