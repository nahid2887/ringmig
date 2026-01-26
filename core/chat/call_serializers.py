from rest_framework import serializers
from django.contrib.auth import get_user_model
from .call_models import CallPackage, CallSession, UniversalCallPackage
from decimal import Decimal

User = get_user_model()


class UniversalCallPackageSerializer(serializers.ModelSerializer):
    """Serializer for universal call packages (admin-created)."""
    
    app_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    listener_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = UniversalCallPackage
        fields = [
            'id', 'name', 'package_type', 'duration_minutes', 'price',
            'app_fee_percentage', 'app_fee', 'listener_amount',
            'is_active', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CallPackageSerializer(serializers.ModelSerializer):
    """Serializer for purchased call packages."""
    
    talker_email = serializers.EmailField(source='talker.email', read_only=True)
    listener_email = serializers.EmailField(source='listener.email', read_only=True)
    listener_name = serializers.SerializerMethodField()
    package_details = UniversalCallPackageSerializer(source='package', read_only=True)
    payment_status = serializers.CharField(read_only=True)
    
    class Meta:
        model = CallPackage
        fields = [
            'id', 'talker', 'talker_email', 'listener', 'listener_email',
            'listener_name', 'package', 'package_details', 'status',
            'total_amount', 'app_fee', 'listener_amount',
            'purchased_at', 'started_at', 'ended_at', 'actual_duration_minutes',
            'stripe_payment_intent_id', 'payment_status',
            'notes', 'cancellation_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'purchased_at', 'started_at', 'ended_at',
            'actual_duration_minutes', 'created_at', 'updated_at',
            'stripe_payment_intent_id', 'payment_status'
        ]
    
    def get_listener_name(self, obj):
        """Get listener full name."""
        if hasattr(obj.listener, 'listener_profile'):
            return obj.listener.listener_profile.get_full_name()
        return obj.listener.email


class PurchaseCallPackageSerializer(serializers.Serializer):
    """Serializer for purchasing a call package."""
    
    listener_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    payment_method_id = serializers.CharField(required=False, allow_blank=True)
    is_extension = serializers.BooleanField(default=False, required=False)
    
    def validate_listener_id(self, value):
        """Validate that listener exists and is a listener."""
        try:
            listener = User.objects.get(id=value, user_type='listener')
        except User.DoesNotExist:
            raise serializers.ValidationError("Listener not found")
        return value
    
    def validate_package_id(self, value):
        """Validate that package exists and is active."""
        try:
            package = UniversalCallPackage.objects.get(id=value, is_active=True)
        except UniversalCallPackage.DoesNotExist:
            raise serializers.ValidationError("Package not found or not active")
        return value
    
    def validate(self, data):
        """Validate the purchase request."""
        listener = User.objects.get(id=data['listener_id'])
        package = UniversalCallPackage.objects.get(id=data['package_id'])
        talker = self.context['request'].user
        
        # Check if this is an extension for an existing call
        if data.get('is_extension', False):
            # Must have an active call session
            active_session = CallSession.objects.filter(
                talker=talker,
                listener=listener,
                status='active'
            ).first()
            
            if not active_session:
                raise serializers.ValidationError(
                    "No active call session found to extend"
                )
            
            data['active_session'] = active_session
        else:
            # New call - check if listener is available
            if not CallSession.is_listener_available(listener):
                raise serializers.ValidationError(
                    f"{listener.email} is busy now. Please try again later."
                )
        
        data['package'] = package
        return data


class CallSessionSerializer(serializers.ModelSerializer):
    """Serializer for call sessions."""
    
    talker_email = serializers.EmailField(source='talker.email', read_only=True)
    listener_email = serializers.EmailField(source='listener.email', read_only=True)
    listener_name = serializers.SerializerMethodField()
    remaining_minutes = serializers.SerializerMethodField()
    elapsed_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = CallSession
        fields = [
            'id', 'talker', 'talker_email', 'listener', 'listener_email',
            'listener_name', 'status', 'total_minutes_purchased', 
            'minutes_used', 'remaining_minutes', 'elapsed_minutes',
            'started_at', 'ended_at', 'last_warning_sent',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'minutes_used', 'started_at', 
            'ended_at', 'last_warning_sent', 'created_at', 'updated_at'
        ]
    
    def get_listener_name(self, obj):
        """Get listener full name."""
        if hasattr(obj.listener, 'listener_profile'):
            return obj.listener.listener_profile.get_full_name()
        return obj.listener.email
    
    def get_remaining_minutes(self, obj):
        """Get remaining minutes."""
        return round(obj.get_remaining_minutes(), 2)
    
    def get_elapsed_minutes(self, obj):
        """Get elapsed minutes."""
        if obj.started_at and obj.status in ['active', 'connecting']:
            from django.utils import timezone
            elapsed = (timezone.now() - obj.started_at).total_seconds() / 60
            return round(elapsed, 2)
        return 0
