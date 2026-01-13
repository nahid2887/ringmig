from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TalkerProfileViewSet

router = DefaultRouter()
router.register(r'profiles', TalkerProfileViewSet, basename='talker-profile')

urlpatterns = [
    path('', include(router.urls)),
]
