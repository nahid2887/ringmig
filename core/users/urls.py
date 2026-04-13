from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    UserRegistrationView,
    UserLoginView,
    UserLogoutView,
    UserProfileView,
    ChangePasswordView,
    OTPVerificationView,
    OAuth2TokenProxyView,
    ForgotPasswordRequestView,
    VerifyPasswordResetOTPView,
    ChangePasswordAfterResetView
)
from .dashboard_views import (
    SuperAdminDashboardView,
    DashboardUserStatsView,
    DashboardRevenueStatsView,
    DashboardSessionsView,
    DashboardTransactionsView,
)

urlpatterns = [
    # OTP-based Registration Flow
    path('register/', UserRegistrationView.as_view(), name='register'),  # Sends OTP
    path('verify-otp/', OTPVerificationView.as_view(), name='verify-otp'),  # Verifies OTP and creates user
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Password Reset Flow
    path('forgot-password/', ForgotPasswordRequestView.as_view(), name='forgot-password'),  # Sends OTP to reset password
    path('verify-password-reset-otp/', VerifyPasswordResetOTPView.as_view(), name='verify-password-reset-otp'),  # Verifies OTP
    path('change-password-after-reset/', ChangePasswordAfterResetView.as_view(), name='change-password-after-reset'),  # Changes password
    
    # OAuth2 Proxy Endpoint - Multi-user OAuth2 token with user identification
    path('oauth2/token/', OAuth2TokenProxyView.as_view(), name='oauth2-token-proxy'),
    
    # SuperAdmin Dashboard
    path('dashboard/', SuperAdminDashboardView.as_view(), name='dashboard'),
    path('dashboard/users/', DashboardUserStatsView.as_view(), name='dashboard-users'),
    path('dashboard/users/<int:user_id>/', DashboardUserStatsView.as_view(), name='dashboard-user-detail'),
    path('dashboard/sessions/', DashboardSessionsView.as_view(), name='dashboard-sessions'),
    path('dashboard/transactions/', DashboardTransactionsView.as_view(), name='dashboard-transactions'),
    #path('dashboard/revenue/', DashboardRevenueStatsView.as_view(), name='dashboard-revenue'),
]
