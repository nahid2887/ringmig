from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ListenerProfileViewSet

router = DefaultRouter()
router.register(r'profiles', ListenerProfileViewSet, basename='listener-profile')

urlpatterns = [
    path('', include(router.urls)),
]
