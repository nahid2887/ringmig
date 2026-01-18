from rest_framework import serializers
from .models import (
    BookingPackage,
    Booking,
    Payment,
    ListenerPayout,
    StripeCustomer,
    StripeListenerAccount
)
from users.serializers import UserSerializer
from listener.serializers import ListenerProfileSerializer


class BookingPackageSerializer(serializers.ModelSerializer):
    """Serializer for booking packages."""
    
    app_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    listener_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = BookingPackage
        fields = [
            'id',
            'name',
            'duration_minutes',
            'price',
            'app_fee_percentage',
            'app_fee',
            'listener_amount',
            'is_active',
            'description',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for bookings."""
    
    talker_details = UserSerializer(source='talker', read_only=True)
    listener_details = UserSerializer(source='listener', read_only=True)
    package_details = BookingPackageSerializer(source='package', read_only=True)
    payment_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id',
            'talker',
            'listener',
            'package',
            'status',
            'scheduled_at',
            'started_at',
            'ended_at',
            'actual_duration_minutes',
            'total_amount',
            'app_fee',
            'listener_amount',
            'notes',
            'cancellation_reason',
            'created_at',
            'updated_at',
            'talker_details',
            'listener_details',
            'package_details',
            'payment_status',
        ]
        read_only_fields = [
            'id',
            'status',
            'started_at',
            'ended_at',
            'actual_duration_minutes',
            'total_amount',
            'app_fee',
            'listener_amount',
            'created_at',
            'updated_at',
        ]
    
    def get_payment_status(self, obj):
        """Get payment status for the booking."""
        if hasattr(obj, 'payment'):
            return obj.payment.status
        return None
    
    def create(self, validated_data):
        """Create booking and calculate amounts."""
        package = validated_data['package']
        
        # Calculate amounts from package
        validated_data['total_amount'] = package.price
        validated_data['app_fee'] = package.app_fee
        validated_data['listener_amount'] = package.listener_amount
        
        return super().create(validated_data)


class CreateBookingSerializer(serializers.Serializer):
    """Serializer for creating a booking."""
    
    listener_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_listener_id(self, value):
        """Validate listener exists and is a listener."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=value, user_type='listener')
        except User.DoesNotExist:
            raise serializers.ValidationError("Listener not found.")
        
        return value
    
    def validate_package_id(self, value):
        """Validate package exists and is active."""
        try:
            package = BookingPackage.objects.get(id=value, is_active=True)
        except BookingPackage.DoesNotExist:
            raise serializers.ValidationError("Package not found or inactive.")
        
        return value


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payments."""
    
    booking_details = BookingSerializer(source='booking', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id',
            'booking',
            'stripe_payment_intent_id',
            'stripe_charge_id',
            'stripe_customer_id',
            'amount',
            'currency',
            'payment_method',
            'status',
            'failure_reason',
            'refund_reason',
            'refund_amount',
            'created_at',
            'updated_at',
            'paid_at',
            'refunded_at',
            'booking_details',
        ]
        read_only_fields = [
            'id',
            'stripe_payment_intent_id',
            'stripe_charge_id',
            'stripe_customer_id',
            'status',
            'created_at',
            'updated_at',
            'paid_at',
            'refunded_at',
        ]


class PaymentIntentSerializer(serializers.Serializer):
    """Serializer for creating payment intent."""
    
    client_secret = serializers.CharField(read_only=True)
    payment_intent_id = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)


class ListenerPayoutSerializer(serializers.ModelSerializer):
    """Serializer for listener payouts."""
    
    listener_details = UserSerializer(source='listener', read_only=True)
    booking_details = BookingSerializer(source='booking', read_only=True)
    
    class Meta:
        model = ListenerPayout
        fields = [
            'id',
            'listener',
            'booking',
            'amount',
            'currency',
            'status',
            'stripe_account_id',
            'stripe_transfer_id',
            'notes',
            'failure_reason',
            'created_at',
            'updated_at',
            'paid_at',
            'listener_details',
            'booking_details',
        ]
        read_only_fields = [
            'id',
            'status',
            'stripe_transfer_id',
            'created_at',
            'updated_at',
            'paid_at',
        ]


class StripeCustomerSerializer(serializers.ModelSerializer):
    """Serializer for Stripe customers."""
    
    class Meta:
        model = StripeCustomer
        fields = ['id', 'user', 'stripe_customer_id', 'created_at', 'updated_at']
        read_only_fields = ['id', 'stripe_customer_id', 'created_at', 'updated_at']


class StripeListenerAccountSerializer(serializers.ModelSerializer):
    """Serializer for Stripe listener accounts."""
    
    class Meta:
        model = StripeListenerAccount
        fields = [
            'id',
            'listener',
            'stripe_account_id',
            'is_verified',
            'is_enabled',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'stripe_account_id',
            'is_verified',
            'created_at',
            'updated_at'
        ]
