from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    UserRegistrationView,
    UserLoginView,
    UserLogoutView,
    UserProfileView,
    ChangePasswordView,
    OTPVerificationView
)
from .dashboard_views import (
    SuperAdminDashboardView,
    DashboardUserStatsView,
    DashboardRevenueStatsView
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
    
    # SuperAdmin Dashboard
    path('dashboard/', SuperAdminDashboardView.as_view(), name='dashboard'),
    path('dashboard/users/', DashboardUserStatsView.as_view(), name='dashboard-users'),
    path('dashboard/revenue/', DashboardRevenueStatsView.as_view(), name='dashboard-revenue'),
]
