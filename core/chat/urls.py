from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConversationViewSet,
    UserNotificationListView,
    NotificationUnreadCountView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationDeleteView,
    PrivacyPolicyView,
    TermsAndConditionsView,
)
from .call_views import (
    UniversalCallPackageViewSet,
    CallPackageViewSet,
    CallSessionViewSet,
    CallRejectionViewSet,
    ListenerPayoutViewSet
)
# from .agora_views import AgoraCallViewSet  # Agora system commented out

router = DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'call-packages/universal', UniversalCallPackageViewSet, basename='universal-call-package')
router.register(r'call-packages', CallPackageViewSet, basename='call-package')
router.register(r'call-sessions', CallSessionViewSet, basename='call-session')
router.register(r'call-rejections', CallRejectionViewSet, basename='call-rejection')
router.register(r'payouts', ListenerPayoutViewSet, basename='listener-payout')
# router.register(r'agora-calls', AgoraCallViewSet, basename='agora-call')  # Agora system commented out

urlpatterns = [
    path('privacy-policy/', PrivacyPolicyView.as_view(), name='privacy-policy'),
    path('terms-and-conditions/', TermsAndConditionsView.as_view(), name='terms-and-conditions'),
    path('notifications/', UserNotificationListView.as_view(), name='user-notifications'),
    path('notifications/unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('notifications/mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
    path('notifications/<int:notification_id>/mark-read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('notifications/<int:notification_id>/', NotificationDeleteView.as_view(), name='notification-delete'),
    path('', include(router.urls)),
]
