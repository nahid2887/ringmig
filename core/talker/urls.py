from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TalkerProfileViewSet

router = DefaultRouter()
router.register(r'profiles', TalkerProfileViewSet, basename='talker-profile')

# Custom URL patterns
urlpatterns = [
    # GET /api/talker/profiles/all_listeners/
    # GET /api/talker/profiles/available_listeners/
    # GET /api/talker/profiles/all_listeners/<listener_id>/
    # GET /api/talker/profiles/available_listeners/<listener_id>/
    path('profiles/all_listeners/<int:listener_id>/', TalkerProfileViewSet.as_view({'get': 'listener_detail_by_id'}), name='listener-detail-all'),
    path('profiles/available_listeners/<int:listener_id>/', TalkerProfileViewSet.as_view({'get': 'available_listener_detail'}), name='listener-detail-available'),
    path('', include(router.urls)),
]
