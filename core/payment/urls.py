from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BookingPackageViewSet,
    BookingViewSet,
    PaymentViewSet,
    StripeWebhookView,
    StripePublishableKeyView,
    ListenerConnectAccountView,
    ListenerConnectRefreshView,
    ListenerConnectReturnView,
)

router = DefaultRouter()
router.register(r'packages', BookingPackageViewSet, basename='booking-package')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
    path('stripe/webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('stripe/config/', StripePublishableKeyView.as_view(), name='stripe-config'),
    
    # Listener Connect (for receiving payouts)
    path('listener/connect/', ListenerConnectAccountView.as_view(), name='listener-connect'),
    path('listener/connect/refresh/', ListenerConnectRefreshView.as_view(), name='listener-connect-refresh'),
    path('listener/connect/return/', ListenerConnectReturnView.as_view(), name='listener-connect-return'),
]
