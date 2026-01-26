from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet
from .call_views import (
    UniversalCallPackageViewSet,
    CallPackageViewSet,
    CallSessionViewSet,
    CallRejectionViewSet,
    ListenerPayoutViewSet
)
from .agora_views import AgoraCallViewSet

router = DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'call-packages/universal', UniversalCallPackageViewSet, basename='universal-call-package')
router.register(r'call-packages', CallPackageViewSet, basename='call-package')
router.register(r'call-sessions', CallSessionViewSet, basename='call-session')
router.register(r'call-rejections', CallRejectionViewSet, basename='call-rejection')
router.register(r'payouts', ListenerPayoutViewSet, basename='listener-payout')
router.register(r'agora-calls', AgoraCallViewSet, basename='agora-call')

urlpatterns = [
    path('', include(router.urls)),
]
