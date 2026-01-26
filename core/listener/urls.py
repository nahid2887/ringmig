from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ListenerProfileViewSet, ListenerBalanceViewSet

router = DefaultRouter()
router.register(r'profiles', ListenerProfileViewSet, basename='listener-profile')
router.register(r'balance', ListenerBalanceViewSet, basename='listener-balance')

urlpatterns = [
    path('', include(router.urls)),
]
