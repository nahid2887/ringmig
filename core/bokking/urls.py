from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    ListenerAvailabilityViewSet,
    UniversalBookingPackageViewSet,
    SessionBookingViewSet,
)

router = SimpleRouter()
router.register(r'availability', ListenerAvailabilityViewSet, basename='availability')
router.register(r'booking-packages/universal', UniversalBookingPackageViewSet, basename='universal-booking-package')
router.register(r'session-bookings', SessionBookingViewSet, basename='session-booking')

urlpatterns = [
    path('', include(router.urls)),
]
