from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
import stripe
import logging
import os

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
        """Create a new booking with payment intent.
        
        Payload:
        {
            "listener_id": 1,
            "package_id": 1,
            "scheduled_at": "2026-01-25T10:00:00Z",  (optional)
            "notes": "Some notes"  (optional)
        }
        
        Note: talker_id is automatically set from the authenticated user.
        """
        # Validate input
        input_serializer = CreateBookingSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        
        listener_id = input_serializer.validated_data['listener_id']
        package_id = input_serializer.validated_data['package_id']
        scheduled_at = input_serializer.validated_data.get('scheduled_at')
        notes = input_serializer.validated_data.get('notes', '')
        
        # Automatically set talker from authenticated user
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
                
                # Create Stripe Checkout Session (hosted payment page)
                amount_cents = int(package.price * 100)  # Convert to cents
                
                # Get frontend URLs (adjust based on your frontend URL)
                frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
                
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card', 'link'],  # Allow card and Link payment
                    line_items=[
                        {
                            'price_data': {
                                'currency': settings.STRIPE_CURRENCY,
                                'product_data': {
                                    'name': f"{package.name.capitalize()} Session with {listener.full_name}",
                                    'description': f"Duration: {package.duration_minutes} minutes",
                                    'images': [],
                                },
                                'unit_amount': amount_cents,
                            },
                            'quantity': 1,
                        }
                    ],
                    customer_email=talker.email,
                    mode='payment',
                    success_url=f"{frontend_url}/payment/success?booking_id={booking.id}&session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{frontend_url}/payment/cancel?booking_id={booking.id}",
                    metadata={
                        'booking_id': booking.id,
                        'talker_id': talker.id,
                        'listener_id': listener.id,
                        'package_id': package.id,
                    },
                )
                
                # Create payment record with checkout session
                # Note: stripe_payment_intent_id will be set by webhook after payment succeeds
                payment = Payment.objects.create(
                    booking=booking,
                    stripe_payment_intent_id=None,  # Will be set by webhook
                    stripe_customer_id=stripe_customer.stripe_customer_id,
                    amount=package.price,
                    currency=settings.STRIPE_CURRENCY,
                    status='pending'
                )
                
                # Store checkout session ID for webhook verification
                booking.notes = f"checkout_session_id:{checkout_session.id}|{booking.notes}"
                booking.save()
                
                # Prepare response
                booking_serializer = BookingSerializer(booking)
                
                return Response({
                    'booking': booking_serializer.data,
                    'payment': {
                        'checkout_url': checkout_session.url,
                        'checkout_session_id': checkout_session.id,
                        'amount': float(package.price),
                        'currency': settings.STRIPE_CURRENCY,
                        'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
                        'status': 'pending',
                        'message': 'Redirect user to checkout_url to complete payment'
                    },
                    'next_steps': [
                        'Redirect user to checkout_url for Stripe hosted payment page',
                        'User will see the payment form with card and Link payment options',
                        'On success, user redirected to success_url and booking confirmed',
                        'Poll the booking status endpoint to check payment status'
                    ]
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
    
    @action(detail=False, methods=['post'])
    def confirm_payment(self, request):
        """Confirm payment and update booking status.
        
        Payload:
        {
            "payment_intent_id": "pi_3SsLIRGNuHFmwqJX0CQXNMqQ",
            "booking_id": 1
        }
        
        This endpoint is called after successful payment.
        It updates the booking status to 'confirmed' if payment succeeded.
        """
        payment_intent_id = request.data.get('payment_intent_id')
        booking_id = request.data.get('booking_id')
        
        if not payment_intent_id or not booking_id:
            return Response(
                {'error': 'payment_intent_id and booking_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the payment
            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent_id,
                booking_id=booking_id
            )
            
            # Get Stripe payment intent status
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            if payment_intent.status == 'succeeded':
                # Update payment status
                payment.status = 'succeeded'
                payment.paid_at = timezone.now()
                payment.save()
                
                # Update booking status
                booking = payment.booking
                booking.status = 'confirmed'
                booking.save()
                
                booking_serializer = BookingSerializer(booking)
                
                return Response({
                    'booking': booking_serializer.data,
                    'payment': {
                        'status': 'succeeded',
                        'amount': float(payment.amount),
                        'currency': payment.currency,
                        'paid_at': payment.paid_at.isoformat(),
                        'message': 'Payment successful! Booking confirmed.'
                    }
                }, status=status.HTTP_200_OK)
                
            elif payment_intent.status == 'processing':
                return Response({
                    'status': 'processing',
                    'message': 'Payment is still processing. Please wait.'
                }, status=status.HTTP_200_OK)
                
            elif payment_intent.status == 'requires_payment_method':
                return Response({
                    'status': 'requires_payment_method',
                    'message': 'Payment method is required. Please provide payment details.',
                    'client_secret': payment_intent.client_secret
                }, status=status.HTTP_400_BAD_REQUEST)
                
            else:
                # Payment failed or cancelled
                payment.status = 'failed'
                payment.failure_reason = f"Payment status: {payment_intent.status}"
                payment.save()
                
                booking = payment.booking
                booking.status = 'cancelled'
                booking.save()
                
                return Response({
                    'status': 'failed',
                    'message': f'Payment failed with status: {payment_intent.status}'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Payment not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error in confirm_payment: {str(e)}")
            return Response(
                {'error': 'Payment verification failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in confirm_payment: {str(e)}")
            return Response(
                {'error': 'Failed to confirm payment', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def check_payment_status(self, request):
        """Check the payment status of a booking.
        
        Query params:
        - booking_id: The booking ID
        - payment_intent_id: The payment intent ID (optional)
        
        Returns the current payment and booking status.
        """
        booking_id = request.query_params.get('booking_id')
        payment_intent_id = request.query_params.get('payment_intent_id')
        
        if not booking_id:
            return Response(
                {'error': 'booking_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            booking = Booking.objects.get(id=booking_id)
            
            # Verify user has access
            if request.user not in [booking.talker, booking.listener]:
                return Response(
                    {'error': 'Not authorized'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            payment = Payment.objects.get(booking=booking)
            
            # Get latest status from Stripe
            if payment_intent_id or payment.stripe_payment_intent_id:
                intent_id = payment_intent_id or payment.stripe_payment_intent_id
                payment_intent = stripe.PaymentIntent.retrieve(intent_id)
                stripe_status = payment_intent.status
            else:
                stripe_status = payment.status
            
            booking_serializer = BookingSerializer(booking)
            
            return Response({
                'booking': booking_serializer.data,
                'payment': {
                    'status': payment.status,
                    'stripe_status': stripe_status,
                    'amount': float(payment.amount),
                    'currency': payment.currency,
                    'paid_at': payment.paid_at.isoformat() if payment.paid_at else None,
                    'payment_intent_id': payment.stripe_payment_intent_id
                }
            }, status=status.HTTP_200_OK)
            
        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Payment not found for this booking'},
                status=status.HTTP_404_NOT_FOUND
            )
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error in check_payment_status: {str(e)}")
            return Response(
                {'error': 'Failed to check payment status', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
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


class StripeWebhookView(APIView):
    """Handle Stripe webhook events.
    
    This endpoint listens for Stripe events like successful payments,
    failed payments, etc. and automatically updates booking status.
    """
    permission_classes = [AllowAny]
    
    @csrf_exempt
    def post(self, request):
        """Handle Stripe webhook events."""
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        
        if not webhook_secret:
            logger.warning("STRIPE_WEBHOOK_SECRET not configured")
            return Response(
                {'error': 'Webhook not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            logger.error("Invalid webhook payload")
            return Response(
                {'error': 'Invalid payload'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid webhook signature")
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle different event types
        if event['type'] == 'checkout.session.completed':
            return self._handle_checkout_completed(event['data']['object'])
        
        elif event['type'] == 'payment_intent.succeeded':
            return self._handle_payment_succeeded(event['data']['object'])
        
        elif event['type'] == 'payment_intent.payment_failed':
            return self._handle_payment_failed(event['data']['object'])
        
        elif event['type'] == 'charge.dispute.created':
            return self._handle_dispute(event['data']['object'])
        
        return Response({'status': 'received'})
    
    def _handle_checkout_completed(self, session):
        """Auto-confirm booking/call package when checkout/payment succeeds."""
        try:
            booking_id = session['metadata'].get('booking_id')
            call_package_id = session['metadata'].get('call_package_id')
            call_session_id = session['metadata'].get('call_session_id')
            is_extension = session['metadata'].get('is_extension') == 'true'
            payment_intent_id = session.get('payment_intent')
            session_type = session['metadata'].get('type')
            
            # Handle payout collection (listener completing payout checkout)
            if session_type == 'payout_collection':
                listener_id = session['metadata'].get('listener_id')
                payout_amount = session['metadata'].get('payout_amount')
                
                logger.info(f"Processing payout_collection: listener={listener_id}, amount={payout_amount}, session_id={session['id']}")
                
                if listener_id and payout_amount:
                    from chat.call_models import ListenerPayout
                    from users.models import CustomUser
                    from decimal import Decimal
                    
                    listener = CustomUser.objects.get(id=listener_id)
                    payout_amount = Decimal(payout_amount)
                    
                    # Update pending payouts to completed
                    # Match by session ID that was stored when creating the payout link
                    pending_payouts = ListenerPayout.objects.filter(
                        listener=listener,
                        status='pending',
                        stripe_payout_id=session['id']
                    )
                    
                    updated_count = 0
                    for payout in pending_payouts:
                        payout.status = 'completed'
                        payout.payout_completed_at = timezone.now()
                        payout.notes = f'Payout completed via Stripe checkout'
                        payout.save(update_fields=['status', 'payout_completed_at', 'notes', 'updated_at'])
                        updated_count += 1
                    
                    logger.info(f"✓ Payout completed for listener {listener.email}: ${payout_amount}, updated {updated_count} records")
                    
                    return Response({
                        'success': True,
                        'message': f'Payout of ${payout_amount} completed for {listener.email}',
                        'listener_id': listener_id,
                        'amount': str(payout_amount),
                        'updated_records': updated_count
                    })
                
                logger.warning(f"Payout collection missing listener_id or amount")
                return Response({'status': 'processed'})
            
            # Handle call extension (add minutes to active call)
            if is_extension and call_package_id and call_session_id:
                from chat.call_models import CallPackage, CallSession, ListenerPayout
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                
                try:
                    with transaction.atomic():
                        # Fetch with select_for_update to lock rows
                        call_package = CallPackage.objects.select_related('package', 'listener').select_for_update().get(id=call_package_id)
                        call_session = CallSession.objects.select_for_update().get(id=call_session_id)
                        
                        logger.info(f"🔄 Extension webhook: call_package_id={call_package_id}, call_session_id={call_session_id}, current_minutes={call_session.total_minutes_purchased}")
                        
                        # Confirm package payment
                        call_package.stripe_payment_intent_id = payment_intent_id
                        call_package.status = 'confirmed'
                        call_package.save(update_fields=['stripe_payment_intent_id', 'status', 'updated_at'])
                        
                        logger.info(f"✓ Package {call_package_id} status set to confirmed")
                        
                        # Add minutes to active call
                        added_minutes = call_package.package.duration_minutes
                        old_minutes = call_session.total_minutes_purchased
                        call_session.total_minutes_purchased += added_minutes
                        call_session.save(update_fields=['total_minutes_purchased', 'updated_at'])
                        
                        logger.info(f"✓ Call session {call_session_id}: minutes updated from {old_minutes} to {call_session.total_minutes_purchased} (+{added_minutes})")
                        
                        # Create ListenerPayout record for listener's earnings (in processing - waiting for call to end)
                        payout = ListenerPayout.objects.create(
                            listener=call_package.listener,
                            call_package=call_package,
                            amount=call_package.listener_amount,
                            status='processing',  # Will become 'earned' when call ends
                            notes=f'Extension package #{call_package.id} - waiting for call to complete'
                        )
                        
                        logger.info(f"✓ ListenerPayout created: payout_id={payout.id}, amount=${call_package.listener_amount}, listener={call_package.listener.email}")
                        
                        # Mark package as used
                        call_package.status = 'used'
                        call_package.used_at = timezone.now()
                        call_package.save(update_fields=['status', 'used_at', 'updated_at'])
                        
                        logger.info(f"✓ Package {call_package_id} status set to used")
                        
                        # Refresh from DB to get latest values
                        call_session.refresh_from_db()
                        
                        # Send WebSocket event to notify both users
                        channel_layer = get_channel_layer()
                        group_name = f'call_{call_session_id}'
                        
                        remaining_minutes = call_session.get_remaining_minutes()
                        logger.info(f"📡 Broadcasting minutes_extended: added={added_minutes}, new_total={call_session.total_minutes_purchased}, remaining={remaining_minutes}")
                        
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            {
                                'type': 'minutes_extended',
                                'added_minutes': added_minutes,
                                'new_total_minutes': call_session.total_minutes_purchased,
                                'remaining_minutes': remaining_minutes,
                                'extend_package_id': call_package.id,
                                'listener_earnings': str(call_package.listener_amount),
                                'timestamp': timezone.now().isoformat()
                            }
                        )
                        
                        logger.info(f"✓ Call extended successfully: {added_minutes} min added to session {call_session_id}")
                        
                        return Response({
                            'success': True,
                            'message': f'{added_minutes} minutes added to call',
                            'call_session_id': call_session_id,
                            'added_minutes': added_minutes,
                            'new_total_minutes': call_session.total_minutes_purchased,
                            'listener_earnings': str(call_package.listener_amount)
                        })
                
                except CallPackage.DoesNotExist:
                    logger.error(f"❌ Extension webhook: CallPackage {call_package_id} not found")
                    return Response({
                        'error': f'Call package {call_package_id} not found',
                        'success': False
                    }, status=status.HTTP_404_NOT_FOUND)
                
                except CallSession.DoesNotExist:
                    logger.error(f"❌ Extension webhook: CallSession {call_session_id} not found")
                    return Response({
                        'error': f'Call session {call_session_id} not found',
                        'success': False
                    }, status=status.HTTP_404_NOT_FOUND)
                
                except Exception as e:
                    logger.error(f"❌ Extension webhook error: {str(e)}", exc_info=True)
                    return Response({
                        'error': f'Failed to extend call: {str(e)}',
                        'success': False
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Handle call package checkout (initial purchase)
            if call_package_id:
                from chat.call_models import CallPackage
                
                call_package = CallPackage.objects.get(id=call_package_id)
                call_package.stripe_payment_intent_id = payment_intent_id
                call_package.status = 'confirmed'
                call_package.save()
                
                logger.info(f"✓ Call package {call_package_id} confirmed via checkout.session.completed")
                return Response({
                    'success': True,
                    'message': f'Call package {call_package_id} confirmed',
                    'call_package_id': call_package_id
                })
            
            # Handle booking checkout
            if not booking_id:
                logger.warning(f"No booking_id or call_package_id in metadata for session {session['id']}")
                return Response({'status': 'processed'})
            
            # Get booking and payment
            booking = Booking.objects.get(id=booking_id)
            payment = Payment.objects.get(booking=booking)
            
            # Update payment status
            payment.stripe_payment_intent_id = payment_intent_id
            payment.status = 'succeeded'
            payment.paid_at = timezone.now()
            payment.save()
            
            # Update booking status to confirmed
            booking.status = 'confirmed'
            booking.updated_at = timezone.now()
            booking.save()
            
            logger.info(f"✓ Booking {booking_id} auto-confirmed on successful payment")
            
            return Response({
                'success': True,
                'message': f'Booking {booking_id} confirmed',
                'booking_id': booking_id
            })
        
        except Booking.DoesNotExist:
            logger.error(f"Booking not found for checkout session")
            return Response({'error': 'Booking not found'})
        except Exception as e:
            logger.error(f"Webhook error: {str(e)}")
            return Response({'error': str(e)})
    
    def _handle_payment_succeeded(self, payment_intent):
        """Handle payment intent succeeded event."""
        try:
            booking_id = payment_intent['metadata'].get('booking_id')
            call_package_id = payment_intent['metadata'].get('call_package_id')
            
            # Handle call package payment
            if call_package_id:
                from chat.call_models import CallPackage
                
                call_package = CallPackage.objects.get(id=call_package_id)
                call_package.stripe_payment_intent_id = payment_intent['id']
                call_package.stripe_charge_id = payment_intent.get('latest_charge', '')
                call_package.status = 'confirmed'
                call_package.save()
                
                logger.info(f"✓ Payment succeeded for call package {call_package_id}")
                return Response({'status': 'processed'})
            
            # Handle booking payment
            if not booking_id:
                return Response({'status': 'processed'})
            
            booking = Booking.objects.get(id=booking_id)
            payment = Payment.objects.get(booking=booking)
            
            # Update payment
            payment.stripe_payment_intent_id = payment_intent['id']
            payment.status = 'succeeded'
            payment.paid_at = timezone.now()
            payment.save()
            
            # Update booking if not already confirmed
            if booking.status == 'pending':
                booking.status = 'confirmed'
                booking.updated_at = timezone.now()
                booking.save()
            
            logger.info(f"✓ Payment succeeded for booking {booking_id}")
            return Response({'status': 'processed'})
        
        except Exception as e:
            logger.error(f"Payment succeeded handler error: {str(e)}")
            return Response({'status': 'error'})
    
    def _handle_payment_failed(self, payment_intent):
        """Handle payment intent failed event."""
        try:
            booking_id = payment_intent['metadata'].get('booking_id')
            call_package_id = payment_intent['metadata'].get('call_package_id')
            
            # Handle call package payment failure
            if call_package_id:
                from chat.call_models import CallPackage
                
                call_package = CallPackage.objects.get(id=call_package_id)
                call_package.status = 'cancelled'
                call_package.cancellation_reason = payment_intent.get('last_payment_error', {}).get('message', 'Payment failed')
                call_package.save()
                
                logger.error(f"✗ Payment failed for call package {call_package_id}")
                return Response({'status': 'processed'})
            
            # Handle booking payment failure
            if not booking_id:
                return Response({'status': 'processed'})
            
            booking = Booking.objects.get(id=booking_id)
            payment = Payment.objects.get(booking=booking)
            
            # Update payment
            payment.status = 'failed'
            payment.failure_reason = payment_intent.get('last_payment_error', {}).get('message', 'Unknown error')
            payment.save()
            
            # Update booking status to cancelled
            booking.status = 'cancelled'
            booking.cancellation_reason = 'Payment failed'
            booking.updated_at = timezone.now()
            booking.save()
            
            logger.error(f"✗ Payment failed for booking {booking_id}")
            return Response({'status': 'processed'})
        
        except Exception as e:
            logger.error(f"Payment failed handler error: {str(e)}")
            return Response({'status': 'error'})
    
    def _handle_dispute(self, dispute):
        """Handle payment dispute/chargeback."""
        logger.warning(f"Payment dispute created: {dispute['id']}")
        return Response({'status': 'processed'})
