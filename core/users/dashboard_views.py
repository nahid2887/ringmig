from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .dashboard_serializers import SuperAdminDashboardSerializer

User = get_user_model()


class IsSuperAdmin(IsAuthenticated):
    """Permission class to check if user is superadmin."""
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.user_type == 'superadmin' or request.user.is_staff


class SuperAdminDashboardView(APIView):
    """Dashboard for superadmin with statistics and charts."""
    permission_classes = [IsSuperAdmin]
    
    @swagger_auto_schema(
        operation_description="Get superadmin dashboard with statistics",
        responses={200: openapi.Response('Dashboard data')},
        tags=['SuperAdmin Dashboard']
    )
    def get(self, request):
        """Get complete dashboard data for superadmin.
        
        Returns:
        - Statistics: total users, talkers, listeners, revenue, commission
        - Earnings Chart: monthly earnings data
        - Subscription Split: ratio of talkers vs listeners
        """
        
        # Get statistics
        stats = self.get_statistics()
        
        # Get earnings chart data
        earnings_chart = self.get_earnings_chart()
        
        # Get subscription split
        subscription_split = self.get_subscription_split()
        
        dashboard_data = {
            'stats': stats,
            'earnings_chart': earnings_chart,
            'subscription_split': subscription_split
        }
        
        serializer = SuperAdminDashboardSerializer(dashboard_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def get_statistics(self):
        """Get dashboard statistics."""
        total_users = User.objects.filter(is_active=True).count()
        total_talkers = User.objects.filter(user_type='talker', is_active=True).count()
        total_listeners = User.objects.filter(user_type='listener', is_active=True).count()
        
        # Get revenue from call packages (completed calls)
        try:
            from chat.call_models import CallPackage
            
            # Get completed call packages
            completed_packages = CallPackage.objects.filter(status__in=['completed', 'confirmed'])
            
            # Sum revenue from calls
            call_revenue = completed_packages.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            call_app_fee = completed_packages.aggregate(Sum('app_fee'))['app_fee__sum'] or Decimal('0.00')
            call_listener_earnings = completed_packages.aggregate(Sum('listener_amount'))['listener_amount__sum'] or Decimal('0.00')
            
        except (ImportError, Exception):
            call_revenue = Decimal('0.00')
            call_app_fee = Decimal('0.00')
            call_listener_earnings = Decimal('0.00')
        
        # Get revenue from payment transactions
        try:
            from payment.models import Payment
            
            total_payment_revenue = Payment.objects.filter(status='completed').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            commission_percentage = Decimal('0.20')  # 20% commission
            payment_platform_commission = total_payment_revenue * commission_percentage
            payment_listener_earnings = total_payment_revenue - payment_platform_commission
            
        except (ImportError, Exception):
            total_payment_revenue = Decimal('0.00')
            payment_platform_commission = Decimal('0.00')
            payment_listener_earnings = Decimal('0.00')
        
        # Combine both sources
        total_revenue = call_revenue + total_payment_revenue
        platform_commission = call_app_fee + payment_platform_commission
        listener_earnings = call_listener_earnings + payment_listener_earnings
        
        return {
            'total_users': total_users,
            'total_talkers': total_talkers,
            'total_listeners': total_listeners,
            'total_revenue': str(total_revenue),
            'platform_commission': str(platform_commission),
            'listener_earnings': str(listener_earnings),
            'call_revenue': str(call_revenue),
            'payment_revenue': str(total_payment_revenue),
            'total_completed_calls': CallPackage.objects.filter(status__in=['completed', 'confirmed']).count()
        }
    
    def get_earnings_chart(self):
        """Get monthly earnings data for the past 12 months."""
        data = []
        
        try:
            from chat.call_models import CallPackage
            from payment.models import Payment
            
            # Get last 12 months of data
            for i in range(11, -1, -1):
                date = timezone.now() - timedelta(days=30*i)
                month_start = date.replace(day=1)
                
                # Get next month's start
                if date.month == 12:
                    month_end = month_start.replace(year=month_start.year + 1, month=1)
                else:
                    month_end = month_start.replace(month=month_start.month + 1)
                
                # Get call package revenue for this month
                month_calls = CallPackage.objects.filter(
                    status__in=['completed', 'confirmed'],
                    purchased_at__gte=month_start,
                    purchased_at__lt=month_end
                ).aggregate(
                    total=Sum('total_amount'),
                    commission=Sum('app_fee')
                )
                
                call_revenue = month_calls['total'] or Decimal('0.00')
                call_commission = month_calls['commission'] or Decimal('0.00')
                
                # Get payment revenue for this month
                month_payments = Payment.objects.filter(
                    status='completed',
                    created_at__gte=month_start,
                    created_at__lt=month_end
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                
                commission_percentage = Decimal('0.20')
                payment_commission = month_payments * commission_percentage
                
                # Combine call and payment revenue
                total_month_revenue = call_revenue + month_payments
                total_commission = call_commission + payment_commission
                listener_earnings = total_month_revenue - total_commission
                
                data.append({
                    'month': month_start.strftime('%b'),
                    'total_earned': str(total_month_revenue),
                    'listener_earnings': str(listener_earnings)
                })
        
        except (ImportError, Exception):
            # If apps don't exist, return empty data
            for i in range(11, -1, -1):
                date = timezone.now() - timedelta(days=30*i)
                data.append({
                    'month': date.strftime('%b'),
                    'total_earned': '0.00',
                    'listener_earnings': '0.00'
                })
        
        return {
            'data': data,
            'currency': 'USD'
        }
    
    def get_subscription_split(self):
        """Get subscription split between talkers and listeners."""
        talker_count = User.objects.filter(user_type='talker', is_active=True).count()
        listener_count = User.objects.filter(user_type='listener', is_active=True).count()
        
        total = talker_count + listener_count
        
        if total > 0:
            talker_percentage = (talker_count / total) * 100
            listener_percentage = (listener_count / total) * 100
        else:
            talker_percentage = 0.0
            listener_percentage = 0.0
        
        return {
            'talker_count': talker_count,
            'listener_count': listener_count,
            'talker_percentage': round(talker_percentage, 2),
            'listener_percentage': round(listener_percentage, 2)
        }


class DashboardUserStatsView(APIView):
    """Detailed user statistics for superadmin."""
    permission_classes = [IsSuperAdmin]
    
    @swagger_auto_schema(
        operation_description="Get detailed user statistics",
        responses={200: openapi.Response('User statistics')},
        tags=['SuperAdmin Dashboard']
    )
    def get(self, request):
        """Get detailed statistics about users."""
        
        stats = {
            'active_users': User.objects.filter(is_active=True).count(),
            'inactive_users': User.objects.filter(is_active=False).count(),
            'verified_users': User.objects.filter(is_verified=True).count(),
            'unverified_users': User.objects.filter(is_verified=False).count(),
            'total_users': User.objects.count(),
            'users_by_type': {
                'talker': User.objects.filter(user_type='talker').count(),
                'listener': User.objects.filter(user_type='listener').count(),
                'superadmin': User.objects.filter(user_type='superadmin').count(),
            },
            'users_by_language': {
                'en': User.objects.filter(language='en').count(),
                'sv': User.objects.filter(language='sv').count(),
            }
        }
        
        return Response(stats, status=status.HTTP_200_OK)


class DashboardRevenueStatsView(APIView):
    """Revenue statistics for superadmin."""
    permission_classes = [IsSuperAdmin]
    
    @swagger_auto_schema(
        operation_description="Get revenue statistics",
        manual_parameters=[
            openapi.Parameter('period', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                            description='Period: day, week, month, year (default: month)'),
        ],
        responses={200: openapi.Response('Revenue statistics')},
        tags=['SuperAdmin Dashboard']
    )
    def get(self, request):
        """Get revenue statistics for a specific period."""
        
        period = request.query_params.get('period', 'month')
        
        try:
            from payment.models import Payment
            from chat.call_models import CallPackage
            
            now = timezone.now()
            
            if period == 'day':
                start_date = now - timedelta(days=1)
            elif period == 'week':
                start_date = now - timedelta(weeks=1)
            elif period == 'year':
                start_date = now - timedelta(days=365)
            else:  # month
                start_date = now - timedelta(days=30)
            
            # Get payment revenue
            payments = Payment.objects.filter(
                status='completed',
                created_at__gte=start_date
            )
            total_payment_revenue = payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
            
            # Get call package revenue
            call_packages = CallPackage.objects.filter(
                status__in=['completed', 'confirmed'],
                purchased_at__gte=start_date
            )
            total_call_revenue = call_packages.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            total_call_commission = call_packages.aggregate(Sum('app_fee'))['app_fee__sum'] or Decimal('0.00')
            total_call_listener_earnings = call_packages.aggregate(Sum('listener_amount'))['listener_amount__sum'] or Decimal('0.00')
            
            # Combine revenues
            total_revenue = total_payment_revenue + total_call_revenue
            
            # Calculate commission
            commission_percentage = Decimal('0.20')
            payment_commission = total_payment_revenue * commission_percentage
            platform_commission = total_call_commission + payment_commission
            listener_earnings = total_call_listener_earnings + (total_payment_revenue - payment_commission)
            
            total_transactions = payments.count() + call_packages.count()
            
            stats = {
                'period': period,
                'total_revenue': str(total_revenue),
                'platform_commission': str(platform_commission),
                'listener_earnings': str(listener_earnings),
                'total_transactions': total_transactions,
                'average_transaction': str(total_revenue / total_transactions) if total_transactions > 0 else '0.00',
                'call_revenue': str(total_call_revenue),
                'payment_revenue': str(total_payment_revenue),
                'total_calls': call_packages.count(),
                'total_payments': payments.count()
            }
        
        except (ImportError, Exception):
            stats = {
                'period': period,
                'total_revenue': '0.00',
                'platform_commission': '0.00',
                'listener_earnings': '0.00',
                'total_transactions': 0,
                'average_transaction': '0.00',
                'call_revenue': '0.00',
                'payment_revenue': '0.00',
                'total_calls': 0,
                'total_payments': 0
            }
        
        return Response(stats, status=status.HTTP_200_OK)
