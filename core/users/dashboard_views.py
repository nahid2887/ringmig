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

# Import models
from payment.models import RevenueTracking

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
    """User management for superadmin (list/detail/status/delete)."""
    permission_classes = [IsSuperAdmin]
    
    @swagger_auto_schema(
        operation_description="Get full users list or one specific user details",
        manual_parameters=[
            openapi.Parameter('user_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Optional user ID for specific user view'),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search by email/full_name/phone'),
            openapi.Parameter('user_type', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by user type: talker/listener/superadmin'),
            openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by admin status: active/suspended/blocked'),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page size, default 50'),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Pagination offset, default 0'),
        ],
        responses={200: openapi.Response('Users list/details')},
        tags=['SuperAdmin Dashboard']
    )
    def get(self, request, user_id=None):
        """Get users list with dashboard cards or a specific user details."""
        target_user_id = user_id or request.query_params.get('user_id')
        if target_user_id:
            return self._get_user_detail(target_user_id)

        search = (request.query_params.get('search') or '').strip()
        user_type_filter = (request.query_params.get('user_type') or '').strip()
        status_filter = (request.query_params.get('status') or '').strip()
        limit = int(request.query_params.get('limit', 50) or 50)
        offset = int(request.query_params.get('offset', 0) or 0)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        users_qs = User.objects.all().order_by('-created_at')

        if search:
            users_qs = users_qs.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search)
            )

        if user_type_filter:
            users_qs = users_qs.filter(user_type=user_type_filter)

        if status_filter:
            users_qs = users_qs.filter(admin_status=status_filter)

        total_count = users_qs.count()
        users_slice = list(users_qs[offset:offset + limit])

        return Response({
            'summary': self._build_user_summary(),
            'count': total_count,
            'limit': limit,
            'offset': offset,
            'results': [self._serialize_user_dashboard_row(u) for u in users_slice],
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Update a specific user's admin status (active/suspended/blocked)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['user_id', 'status'],
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'status': openapi.Schema(type=openapi.TYPE_STRING, enum=['active', 'suspended', 'blocked']),
            }
        ),
        responses={200: openapi.Response('User status updated')},
        tags=['SuperAdmin Dashboard']
    )
    def patch(self, request, user_id=None):
        target_user_id = user_id or request.data.get('user_id')
        new_status = request.data.get('status')

        if not target_user_id or not new_status:
            return Response(
                {'error': 'user_id and status are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_status not in ['active', 'suspended', 'blocked']:
            return Response(
                {'error': 'status must be one of: active, suspended, blocked'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.id == request.user.id:
            return Response({'error': 'You cannot change your own status'}, status=status.HTTP_400_BAD_REQUEST)

        target_user.admin_status = new_status
        target_user.is_active = (new_status == 'active')
        target_user.save(update_fields=['admin_status', 'is_active', 'updated_at'])

        return Response(
            {
                'message': 'User status updated successfully',
                'user': self._serialize_user_dashboard_row(target_user),
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_description="Delete a specific user by user_id",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['user_id'],
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            }
        ),
        responses={200: openapi.Response('User deleted')},
        tags=['SuperAdmin Dashboard']
    )
    def delete(self, request, user_id=None):
        target_user_id = user_id or request.data.get('user_id')
        if not target_user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.id == request.user.id:
            return Response({'error': 'You cannot delete your own account'}, status=status.HTTP_400_BAD_REQUEST)

        deleted_user_payload = {
            'id': target_user.id,
            'email': target_user.email,
            'full_name': target_user.full_name,
            'user_type': target_user.user_type,
        }
        target_user.delete()

        return Response(
            {
                'message': 'User deleted successfully',
                'deleted_user': deleted_user_payload,
            },
            status=status.HTTP_200_OK,
        )

    def _get_user_detail(self, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                'user': self._serialize_user_dashboard_row(user),
            },
            status=status.HTTP_200_OK,
        )

    def _build_user_summary(self):
        return {
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
            'users_by_status': {
                'active': User.objects.filter(admin_status='active').count(),
                'suspended': User.objects.filter(admin_status='suspended').count(),
                'blocked': User.objects.filter(admin_status='blocked').count(),
            },
        }

    def _serialize_user_dashboard_row(self, user):
        from listener.models import ListenerProfile, ListenerBalance
        from talker.models import TalkerBalance
        from chat.call_models import CallSession

        sessions_count = CallSession.objects.filter(Q(talker=user) | Q(listener=user)).count()

        rating = None
        earnings = Decimal('0.00')

        if user.user_type == 'listener':
            listener_profile = ListenerProfile.objects.filter(user=user).first()
            if listener_profile:
                rating = listener_profile.average_rating

            listener_balance = ListenerBalance.objects.filter(listener=user).first()
            if listener_balance:
                earnings = listener_balance.available_balance
        elif user.user_type == 'talker':
            talker_balance = TalkerBalance.objects.filter(talker=user).first()
            if talker_balance:
                earnings = talker_balance.available_balance

        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'phone_number': user.phone_number,
            'user_type': user.user_type,
            'language': user.language,
            'status': user.admin_status,
            'is_active': user.is_active,
            'is_verified': user.is_verified,
            'sessions': sessions_count,
            'earnings': str(earnings),
            'rating': rating,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
        }


class DashboardSessionsView(APIView):
    """Sessions list for superadmin (booking sessions + call sessions)."""
    permission_classes = [IsSuperAdmin]

    @swagger_auto_schema(
        operation_description="Get superadmin sessions list (booking + call sessions)",
        manual_parameters=[
            openapi.Parameter('source', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='all|booking|call (default: all)'),
            openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Optional status filter within selected source'),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page size, default 50'),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Pagination offset, default 0'),
        ],
        responses={200: openapi.Response('Sessions list')},
        tags=['SuperAdmin Dashboard']
    )
    def get(self, request):
        source = (request.query_params.get('source') or 'all').strip().lower()
        status_filter = (request.query_params.get('status') or '').strip().lower()
        limit = int(request.query_params.get('limit', 50) or 50)
        offset = int(request.query_params.get('offset', 0) or 0)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        if source not in ['all', 'booking', 'call']:
            return Response(
                {'error': 'source must be one of: all, booking, call'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = []
        booking_count = 0
        call_count = 0

        if source in ['all', 'booking']:
            from bokking.models import SessionBooking

            booking_qs = SessionBooking.objects.select_related('talker', 'listener').order_by('-created_at')
            if status_filter:
                booking_qs = booking_qs.filter(status=status_filter)

            booking_count = booking_qs.count()
            booking_items = [self._serialize_booking_session(obj) for obj in booking_qs[:500]]
            items.extend(booking_items)

        if source in ['all', 'call']:
            from chat.call_models import CallSession

            call_qs = CallSession.objects.select_related('talker', 'listener', 'call_package').order_by('-created_at')
            if status_filter:
                call_qs = call_qs.filter(status=status_filter)

            call_count = call_qs.count()
            call_items = [self._serialize_call_session(obj) for obj in call_qs[:500]]
            items.extend(call_items)

        items.sort(key=lambda row: row['created_at'], reverse=True)
        total_count = len(items)
        page_items = items[offset:offset + limit]

        return Response(
            {
                'summary': {
                    'booking_sessions': booking_count,
                    'call_sessions': call_count,
                    'total_sessions': booking_count + call_count,
                },
                'count': total_count,
                'limit': limit,
                'offset': offset,
                'results': page_items,
            },
            status=status.HTTP_200_OK,
        )

    def _serialize_booking_session(self, booking):
        created_at = booking.created_at.isoformat() if booking.created_at else None
        return {
            'source': 'booking',
            'session_id': str(booking.id),
            'talker': {
                'id': booking.talker_id,
                'email': booking.talker.email,
                'full_name': booking.talker.full_name,
            },
            'listener': {
                'id': booking.listener_id,
                'email': booking.listener.email,
                'full_name': booking.listener.full_name,
            },
            'status': booking.status,
            'amount': str(booking.listener_amount),
            'duration_minutes': booking.duration_minutes,
            'booking_date': booking.booking_date.isoformat(),
            'start_time': booking.start_time.strftime('%H:%M:%S'),
            'end_time': booking.end_time.strftime('%H:%M:%S'),
            'created_at': created_at,
            '_sort_ts': booking.created_at.timestamp() if booking.created_at else 0,
        }

    def _serialize_call_session(self, call_session):
        amount = Decimal('0.00')
        if call_session.call_package and call_session.call_package.listener_amount is not None:
            amount = call_session.call_package.listener_amount

        created_at = call_session.created_at.isoformat() if call_session.created_at else None
        return {
            'source': 'call',
            'session_id': str(call_session.id),
            'talker': {
                'id': call_session.talker_id,
                'email': call_session.talker.email,
                'full_name': call_session.talker.full_name,
            },
            'listener': {
                'id': call_session.listener_id,
                'email': call_session.listener.email,
                'full_name': call_session.listener.full_name,
            },
            'status': call_session.status,
            'amount': str(amount),
            'duration_minutes': call_session.total_minutes_purchased,
            'booking_date': call_session.started_at.date().isoformat() if call_session.started_at else None,
            'start_time': call_session.started_at.time().strftime('%H:%M:%S') if call_session.started_at else None,
            'end_time': call_session.ended_at.time().strftime('%H:%M:%S') if call_session.ended_at else None,
            'created_at': created_at,
            '_sort_ts': call_session.created_at.timestamp() if call_session.created_at else 0,
        }


class DashboardTransactionsView(APIView):
    """Transactions list for superadmin (talker/listener rows)."""
    permission_classes = [IsSuperAdmin]

    @swagger_auto_schema(
        operation_description='Get transaction list for superadmin dashboard',
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search by talker/listener name or email'),
            openapi.Parameter('source', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='all|revenue|booking|call_package (default: all)'),
            openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Optional status filter'),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page size, default 50'),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Pagination offset, default 0'),
        ],
        responses={200: openapi.Response('Transactions list')},
        tags=['SuperAdmin Dashboard']
    )
    def get(self, request):
        search = (request.query_params.get('search') or '').strip()
        source = (request.query_params.get('source') or 'all').strip().lower()
        status_filter = (request.query_params.get('status') or '').strip().lower()
        limit = int(request.query_params.get('limit', 50) or 50)
        offset = int(request.query_params.get('offset', 0) or 0)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        if source not in ['all', 'revenue', 'booking', 'call_package']:
            return Response(
                {'error': 'source must be one of: all, revenue, booking, call_package'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = []

        if source in ['all', 'revenue']:
            revenue_qs = RevenueTracking.objects.select_related('talker', 'listener').order_by('-created_at')
            if search:
                revenue_qs = revenue_qs.filter(
                    Q(talker__email__icontains=search) |
                    Q(talker__full_name__icontains=search) |
                    Q(listener__email__icontains=search) |
                    Q(listener__full_name__icontains=search)
                )

            for tx in revenue_qs[:500]:
                items.append({
                    'source': 'revenue',
                    'transaction_id': tx.id,
                    'external_id': tx.stripe_payment_intent_id,
                    'talker': {
                        'id': tx.talker_id,
                        'email': tx.talker.email,
                        'full_name': tx.talker.full_name,
                    },
                    'listener': {
                        'id': tx.listener_id,
                        'email': tx.listener.email,
                        'full_name': tx.listener.full_name,
                    },
                    'listener_earnings': str(tx.listener_portion),
                    'platform_commission': str(tx.admin_portion),
                    'platform_commission_percent': str(tx.admin_percentage),
                    'total': str(tx.total_amount),
                    'status': 'accepted',
                    'transaction_type': tx.transaction_type,
                    'created_at': tx.created_at.isoformat(),
                    '_sort_ts': tx.created_at.timestamp(),
                })

        if source in ['all', 'booking']:
            from bokking.models import SessionBooking

            booking_qs = SessionBooking.objects.select_related('talker', 'listener').order_by('-created_at')
            if search:
                booking_qs = booking_qs.filter(
                    Q(talker__email__icontains=search) |
                    Q(talker__full_name__icontains=search) |
                    Q(listener__email__icontains=search) |
                    Q(listener__full_name__icontains=search)
                )
            if status_filter:
                booking_qs = booking_qs.filter(status=status_filter)

            for tx in booking_qs[:500]:
                admin_percentage = Decimal('0.00')
                if tx.price and tx.price > 0:
                    admin_percentage = ((tx.app_fee / tx.price) * Decimal('100')).quantize(Decimal('0.01'))

                if tx.status == 'completed':
                    display_status = 'accepted'
                elif tx.status == 'refunded':
                    display_status = 'refunded'
                elif tx.status == 'cancelled':
                    display_status = 'rejected'
                else:
                    display_status = tx.status

                items.append({
                    'source': 'booking',
                    'transaction_id': str(tx.id),
                    'external_id': tx.transaction_id,
                    'talker': {
                        'id': tx.talker_id,
                        'email': tx.talker.email,
                        'full_name': tx.talker.full_name,
                    },
                    'listener': {
                        'id': tx.listener_id,
                        'email': tx.listener.email,
                        'full_name': tx.listener.full_name,
                    },
                    'listener_earnings': str(tx.listener_amount),
                    'platform_commission': str(tx.app_fee),
                    'platform_commission_percent': str(admin_percentage),
                    'total': str(tx.price),
                    'status': display_status,
                    'transaction_type': 'booking_refund' if tx.status == 'refunded' else 'booking',
                    'created_at': tx.created_at.isoformat(),
                    '_sort_ts': tx.created_at.timestamp(),
                })

        if source in ['all', 'call_package']:
            from chat.call_models import CallPackage

            call_package_qs = CallPackage.objects.select_related('talker', 'listener').order_by('-created_at')
            if search:
                call_package_qs = call_package_qs.filter(
                    Q(talker__email__icontains=search) |
                    Q(talker__full_name__icontains=search) |
                    Q(listener__email__icontains=search) |
                    Q(listener__full_name__icontains=search)
                )

            for tx in call_package_qs[:500]:
                admin_percentage = Decimal('0.00')
                if tx.total_amount and tx.total_amount > 0:
                    admin_percentage = ((tx.app_fee / tx.total_amount) * Decimal('100')).quantize(Decimal('0.01'))

                raw_status = (tx.status or '').lower()
                if raw_status in ['confirmed', 'completed', 'in_progress', 'active', 'used']:
                    display_status = 'accepted'
                elif raw_status in ['cancelled', 'failed', 'refunded']:
                    display_status = 'rejected'
                else:
                    display_status = raw_status or 'pending'

                items.append({
                    'source': 'call_package',
                    'transaction_id': tx.id,
                    'external_id': tx.stripe_payment_intent_id,
                    'talker': {
                        'id': tx.talker_id,
                        'email': tx.talker.email,
                        'full_name': tx.talker.full_name,
                    },
                    'listener': {
                        'id': tx.listener_id,
                        'email': tx.listener.email,
                        'full_name': tx.listener.full_name,
                    },
                    'listener_earnings': str(tx.listener_amount),
                    'platform_commission': str(tx.app_fee),
                    'platform_commission_percent': str(admin_percentage),
                    'total': str(tx.total_amount),
                    'status': display_status,
                    'transaction_type': 'extension' if tx.is_extension else 'call_purchase',
                    'created_at': tx.created_at.isoformat(),
                    '_sort_ts': tx.created_at.timestamp(),
                })

        if status_filter:
            items = [row for row in items if str(row.get('status', '')).lower() == status_filter]

        source_counts = {
            'revenue': 0,
            'booking': 0,
            'call_package': 0,
        }
        for row in items:
            row_source = row.get('source')
            if row_source in source_counts:
                source_counts[row_source] += 1

        items.sort(key=lambda row: row['_sort_ts'], reverse=True)
        total_count = len(items)
        page_items = items[offset:offset + limit]

        for row in page_items:
            row.pop('_sort_ts', None)

        return Response(
            {
                'count': total_count,
                'source_counts': source_counts,
                'limit': limit,
                'offset': offset,
                'results': page_items,
            },
            status=status.HTTP_200_OK,
        )


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
            
            # Get call package revenue with admin/listener breakdown
            call_packages = CallPackage.objects.filter(
                status__in=['completed', 'confirmed'],
                purchased_at__gte=start_date
            )
            total_call_revenue = call_packages.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            admin_revenue = call_packages.aggregate(Sum('admin_amount'))['admin_amount__sum'] or Decimal('0.00')
            listener_revenue = call_packages.aggregate(Sum('listener_amount'))['listener_amount__sum'] or Decimal('0.00')
            
            # Get revenue tracking data for enhanced analytics
            from payment.models import RevenueTracking
            revenue_tracking = RevenueTracking.objects.filter(
                created_at__gte=start_date
            )
            tracked_admin_revenue = revenue_tracking.aggregate(Sum('admin_portion'))['admin_portion__sum'] or Decimal('0.00')
            tracked_listener_revenue = revenue_tracking.aggregate(Sum('listener_portion'))['listener_portion__sum'] or Decimal('0.00')
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
