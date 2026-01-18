from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.conf import settings
from django.utils import timezone
from django.db import transaction
import stripe
import logging

from .models import (
    BookingPackage,
    Booking,
    Payment,
    ListenerPayout,
    StripeCustomer,
    StripeListenerAccount
)
from .serializers import (
    BookingPackageSerializer,
    BookingSerializer,
    CreateBookingSerializer,
    PaymentSerializer,
    PaymentIntentSerializer,
    ListenerPayoutSerializer,
)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


class BookingPackageViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing booking packages."""
    
    queryset = BookingPackage.objects.filter(is_active=True)
    serializer_class = BookingPackageSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        """Filter active packages."""
        return BookingPackage.objects.filter(is_active=True).order_by('duration_minutes')


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet for managing bookings."""
    
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter bookings based on user type."""
        user = self.request.user
        
        if user.user_type == 'talker':
            return Booking.objects.filter(talker=user).select_related(
                'talker', 'listener', 'package'
            ).order_by('-created_at')
        elif user.user_type == 'listener':
            return Booking.objects.filter(listener=user).select_related(
                'talker', 'listener', 'package'
            ).order_by('-created_at')
        
        return Booking.objects.none()
    
    @action(detail=False, methods=['post'])
    def create_booking(self, request):
        """Create a new booking with payment intent."""
        # Validate input
        input_serializer = CreateBookingSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        
        listener_id = input_serializer.validated_data['listener_id']
        package_id = input_serializer.validated_data['package_id']
        scheduled_at = input_serializer.validated_data.get('scheduled_at')
        notes = input_serializer.validated_data.get('notes', '')
        
        talker = request.user
        
        # Get listener and package
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            listener = User.objects.get(id=listener_id, user_type='listener')
            package = BookingPackage.objects.get(id=package_id, is_active=True)
        except (User.DoesNotExist, BookingPackage.DoesNotExist) as e:
            return Response(
                {'error': 'Listener or package not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if listener is available
        if hasattr(listener, 'listener_profile') and not listener.listener_profile.is_available:
            return Response(
                {'error': 'Listener is not available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Create booking
                booking = Booking.objects.create(
                    talker=talker,
                    listener=listener,
                    package=package,
                    scheduled_at=scheduled_at,
                    notes=notes,
                    total_amount=package.price,
                    app_fee=package.app_fee,
                    listener_amount=package.listener_amount,
                    status='pending'
                )
                
                # Create or get Stripe customer
                stripe_customer = self._get_or_create_stripe_customer(talker)
                
                # Create Stripe Payment Intent
                amount_cents = int(package.price * 100)  # Convert to cents
                
                payment_intent = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency=settings.STRIPE_CURRENCY,
                    customer=stripe_customer.stripe_customer_id,
                    metadata={
                        'booking_id': booking.id,
                        'talker_id': talker.id,
                        'listener_id': listener.id,
                        'package_id': package.id,
                    },
                    description=f"Booking: {package.name} with {listener.email}"
                )
                
                # Create payment record
                payment = Payment.objects.create(
                    booking=booking,
                    stripe_payment_intent_id=payment_intent.id,
                    stripe_customer_id=stripe_customer.stripe_customer_id,
                    amount=package.price,
                    currency=settings.STRIPE_CURRENCY,
                    status='pending'
                )
                
                # Prepare response
                booking_serializer = BookingSerializer(booking)
                
                return Response({
                    'booking': booking_serializer.data,
                    'payment': {
                        'client_secret': payment_intent.client_secret,
                        'payment_intent_id': payment_intent.id,
                        'amount': package.price,
                        'currency': settings.STRIPE_CURRENCY,
                    }
                }, status=status.HTTP_201_CREATED)
                
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return Response(
                {'error': 'Payment processing error', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Booking creation error: {str(e)}")
            return Response(
                {'error': 'Failed to create booking', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_or_create_stripe_customer(self, user):
        """Get or create Stripe customer for user."""
        try:
            return StripeCustomer.objects.get(user=user)
        except StripeCustomer.DoesNotExist:
            # Create new Stripe customer
            stripe_customer = stripe.Customer.create(
                email=user.email,
                metadata={'user_id': user.id}
            )
            
            return StripeCustomer.objects.create(
                user=user,
                stripe_customer_id=stripe_customer.id
            )
    
    @action(detail=True, methods=['post'])
    def start_session(self, request, pk=None):
        """Start a booking session."""
        booking = self.get_object()
        
        # Verify user is part of this booking
        if request.user not in [booking.talker, booking.listener]:
            return Response(
                {'error': 'Not authorized'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check booking status
        if booking.status != 'confirmed':
            return Response(
                {'error': 'Booking must be confirmed to start'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.start_session()
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def complete_session(self, request, pk=None):
        """Complete a booking session."""
        booking = self.get_object()
        
        # Verify user is part of this booking
        if request.user not in [booking.talker, booking.listener]:
            return Response(
                {'error': 'Not authorized'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check booking status
        if booking.status != 'in_progress':
            return Response(
                {'error': 'Session must be in progress to complete'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.complete_session()
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a booking."""
        booking = self.get_object()
        
        # Only talker can cancel
        if request.user != booking.talker:
            return Response(
                {'error': 'Only talker can cancel booking'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Can only cancel if pending or confirmed
        if booking.status not in ['pending', 'confirmed']:
            return Response(
                {'error': f'Cannot cancel booking with status: {booking.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('reason', '')
        booking.cancel(reason=reason)
        
        # TODO: Implement refund logic if payment was made
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing payments."""
    
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter payments based on user."""
        user = self.request.user
        
        if user.user_type == 'talker':
            return Payment.objects.filter(
                booking__talker=user
            ).select_related('booking').order_by('-created_at')
        elif user.user_type == 'listener':
            return Payment.objects.filter(
                booking__listener=user
            ).select_related('booking').order_by('-created_at')
        
        return Payment.objects.none()


class ListenerPayoutViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing listener payouts."""
    
    serializer_class = ListenerPayoutSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Only listeners can view their payouts."""
        user = self.request.user
        
        if user.user_type == 'listener':
            return ListenerPayout.objects.filter(
                listener=user
            ).select_related('booking', 'listener').order_by('-created_at')
        
        return ListenerPayout.objects.none()
    
    @action(detail=False, methods=['get'])
    def pending_earnings(self, request):
        """Get pending earnings for listener."""
        if request.user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view earnings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from django.db.models import Sum
        
        pending = ListenerPayout.objects.filter(
            listener=request.user,
            status='pending'
        ).aggregate(total=Sum('amount'))
        
        completed = ListenerPayout.objects.filter(
            listener=request.user,
            status='completed'
        ).aggregate(total=Sum('amount'))
        
        return Response({
            'pending_earnings': pending['total'] or 0,
            'total_earned': completed['total'] or 0,
        })


class StripeWebhookView(APIView):
    """Handle Stripe webhook events."""
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Process Stripe webhook."""
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {e}")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        # Handle the event
        if event['type'] == 'payment_intent.succeeded':
            self._handle_payment_succeeded(event['data']['object'])
        elif event['type'] == 'payment_intent.payment_failed':
            self._handle_payment_failed(event['data']['object'])
        elif event['type'] == 'charge.refunded':
            self._handle_charge_refunded(event['data']['object'])
        
        return Response(status=status.HTTP_200_OK)
    
    def _handle_payment_succeeded(self, payment_intent):
        """Handle successful payment."""
        try:
            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent['id']
            )
            payment.status = 'succeeded'
            payment.stripe_charge_id = payment_intent.get('latest_charge', '')
            payment.paid_at = timezone.now()
            payment.save()
            
            logger.info(f"Payment succeeded for booking {payment.booking.id}")
            
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for intent: {payment_intent['id']}")
    
    def _handle_payment_failed(self, payment_intent):
        """Handle failed payment."""
        try:
            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent['id']
            )
            payment.status = 'failed'
            payment.failure_reason = payment_intent.get('last_payment_error', {}).get('message', '')
            payment.save()
            
            # Cancel the booking
            payment.booking.cancel(reason='Payment failed')
            
            logger.warning(f"Payment failed for booking {payment.booking.id}")
            
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for intent: {payment_intent['id']}")
    
    def _handle_charge_refunded(self, charge):
        """Handle refunded charge."""
        try:
            payment = Payment.objects.get(stripe_charge_id=charge['id'])
            payment.status = 'refunded'
            payment.refund_amount = charge['amount_refunded'] / 100  # Convert from cents
            payment.refunded_at = timezone.now()
            payment.save()
            
            # Update booking status
            payment.booking.status = 'refunded'
            payment.booking.save()
            
            logger.info(f"Payment refunded for booking {payment.booking.id}")
            
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for charge: {charge['id']}")


class StripePublishableKeyView(APIView):
    """Return Stripe publishable key for frontend."""
    
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Get Stripe publishable key."""
        return Response({
            'publishable_key': settings.STRIPE_PUBLISHABLE_KEY
        })


class ListenerConnectAccountView(APIView):
    """Create Stripe Connect account for listener to receive payouts."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Create Stripe Connect account link for listener."""
        user = request.user
        
        # Only listeners can create connect accounts
        if user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can create payout accounts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Check if listener already has a Stripe account
            try:
                listener_account = StripeListenerAccount.objects.get(listener=user)
                account_id = listener_account.stripe_account_id
            except StripeListenerAccount.DoesNotExist:
                # Create new Stripe Connect Express account
                account = stripe.Account.create(
                    type='express',
                    country='US',  # Change based on your needs
                    email=user.email,
                    capabilities={
                        'transfers': {'requested': True},
                    },
                    business_type='individual',
                    metadata={'user_id': user.id}
                )
                
                # Save account ID
                listener_account = StripeListenerAccount.objects.create(
                    listener=user,
                    stripe_account_id=account.id,
                    is_verified=False
                )
                account_id = account.id
            
            # Create account link for onboarding
            account_link = stripe.AccountLink.create(
                account=account_id,
                refresh_url=request.build_absolute_uri('/api/payment/listener/connect/refresh/'),
                return_url=request.build_absolute_uri('/api/payment/listener/connect/return/'),
                type='account_onboarding',
            )
            
            return Response({
                'url': account_link.url,
                'account_id': account_id
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe Connect error: {str(e)}")
            return Response(
                {'error': 'Failed to create payout account', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def get(self, request):
        """Get listener's Stripe Connect account status."""
        user = request.user
        
        if user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view payout accounts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            listener_account = StripeListenerAccount.objects.get(listener=user)
            
            # Get account details from Stripe
            account = stripe.Account.retrieve(listener_account.stripe_account_id)
            
            return Response({
                'has_account': True,
                'account_id': listener_account.stripe_account_id,
                'is_verified': account.charges_enabled and account.payouts_enabled,
                'details_submitted': account.details_submitted,
                'payouts_enabled': account.payouts_enabled,
                'charges_enabled': account.charges_enabled,
            })
            
        except StripeListenerAccount.DoesNotExist:
            return Response({
                'has_account': False,
                'message': 'No payout account created yet'
            })
        except stripe.error.StripeError as e:
            return Response(
                {'error': 'Failed to retrieve account status', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ListenerConnectRefreshView(APIView):
    """Handle refresh when listener needs to complete onboarding."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Redirect back to create new account link."""
        return Response({
            'message': 'Please complete the onboarding process',
            'action': 'refresh_onboarding'
        })


class ListenerConnectReturnView(APIView):
    """Handle return after successful Stripe Connect onboarding."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Verify account setup completion."""
        user = request.user
        
        try:
            listener_account = StripeListenerAccount.objects.get(listener=user)
            account = stripe.Account.retrieve(listener_account.stripe_account_id)
            
            # Update verification status
            if account.charges_enabled and account.payouts_enabled:
                listener_account.is_verified = True
                listener_account.save()
            
            return Response({
                'success': True,
                'message': 'Payout account setup completed!',
                'is_verified': listener_account.is_verified,
                'can_receive_payouts': account.payouts_enabled
            })
            
        except StripeListenerAccount.DoesNotExist:
            return Response(
                {'error': 'No payout account found'},
                status=status.HTTP_404_NOT_FOUND
            )


class ProcessListenerPayoutView(APIView):
    """Process payout to listener (admin only)."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, payout_id):
        """Process a pending payout."""
        # Check if user is admin/staff
        if not request.user.is_staff:
            return Response(
                {'error': 'Only administrators can process payouts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            payout = ListenerPayout.objects.get(id=payout_id)
            
            # Verify payout is pending
            if payout.status != 'pending':
                return Response(
                    {'error': f'Payout status is {payout.status}, cannot process'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify booking is completed
            if payout.booking.status != 'completed':
                return Response(
                    {'error': 'Booking must be completed before processing payout'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get listener's Stripe account
            try:
                listener_account = StripeListenerAccount.objects.get(
                    listener=payout.listener,
                    is_verified=True
                )
            except StripeListenerAccount.DoesNotExist:
                return Response(
                    {'error': 'Listener does not have a verified payout account'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create transfer to listener's account
            amount_cents = int(payout.amount * 100)
            
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency=payout.currency.lower(),
                destination=listener_account.stripe_account_id,
                description=f"Payout for booking #{payout.booking.id}",
                metadata={
                    'payout_id': payout.id,
                    'booking_id': payout.booking.id,
                    'listener_id': payout.listener.id
                }
            )
            
            # Update payout record
            payout.status = 'completed'
            payout.stripe_transfer_id = transfer.id
            payout.paid_at = timezone.now()
            payout.save()
            
            serializer = ListenerPayoutSerializer(payout)
            return Response({
                'success': True,
                'message': 'Payout processed successfully',
                'payout': serializer.data
            })
            
        except ListenerPayout.DoesNotExist:
            return Response(
                {'error': 'Payout not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except stripe.error.StripeError as e:
            logger.error(f"Payout transfer error: {str(e)}")
            payout.status = 'failed'
            payout.failure_reason = str(e)
            payout.save()
            
            return Response(
                {'error': 'Failed to process payout', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
