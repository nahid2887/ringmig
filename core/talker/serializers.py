from rest_framework import serializers
from .models import TalkerProfile, FavoriteListener, TalkerReport, TalkerSuspension
from listener.models import ListenerProfile


class TalkerReportSerializer(serializers.ModelSerializer):
    """Serializer for creating and viewing talker reports."""
    reporter_email = serializers.CharField(source='reporter.email', read_only=True)
    talker_email = serializers.CharField(source='talker.email', read_only=True)
    
    class Meta:
        model = TalkerReport
        fields = ['id', 'talker', 'talker_email', 'reporter', 'reporter_email', 'reason', 
                  'description', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'reporter', 'reporter_email', 'talker_email', 'status', 'created_at', 'updated_at']
    
    def validate_talker(self, value):
        """Ensure reported user is a talker."""
        if value.user_type != 'talker':
            raise serializers.ValidationError("Can only report talker accounts.")
        return value


class CreateTalkerReportSerializer(serializers.Serializer):
    """Serializer for creating a report against a talker."""
    talker_id = serializers.IntegerField(required=True, help_text='ID of the talker to report')
    reason = serializers.ChoiceField(
        choices=TalkerReport.REPORT_REASON_CHOICES,
        required=True,
        help_text='Reason for the report'
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        help_text='Detailed description of the issue'
    )
    
    def validate_talker_id(self, value):
        """Validate that the talker exists."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=value, user_type='talker')
        except User.DoesNotExist:
            raise serializers.ValidationError(f"Talker with ID {value} not found.")
        return value


class TalkerSuspensionSerializer(serializers.ModelSerializer):
    """Serializer for viewing talker suspension status."""
    talker_email = serializers.CharField(source='talker.email', read_only=True)
    remaining_days = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = TalkerSuspension
        fields = ['id', 'talker', 'talker_email', 'reason', 'suspended_at', 'resume_at', 
                  'is_active', 'days_suspended', 'remaining_days', 'created_at']
        read_only_fields = ['id', 'talker', 'talker_email', 'suspended_at', 'resume_at', 
                           'is_active', 'days_suspended', 'created_at']
    
    def get_remaining_days(self, obj):
        """Get remaining suspension days."""
        return obj.get_remaining_days()

class TalkerCallHistorySerializer(serializers.Serializer):
    """Serializer for talker call history (CallSession)."""
    id = serializers.IntegerField(read_only=True)
    listener_id = serializers.SerializerMethodField(read_only=True)
    listener_email = serializers.SerializerMethodField(read_only=True)
    listener_name = serializers.SerializerMethodField(read_only=True)
    status = serializers.CharField(read_only=True)
    call_type = serializers.CharField(read_only=True)
    total_minutes_purchased = serializers.IntegerField(read_only=True)
    minutes_used = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    started_at = serializers.DateTimeField(read_only=True)
    ended_at = serializers.DateTimeField(read_only=True)
    end_reason = serializers.CharField(read_only=True)
    duration_in_minutes = serializers.SerializerMethodField(read_only=True)
    amount_paid = serializers.SerializerMethodField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    
    def get_listener_id(self, obj):
        """Get listener ID from CallSession object."""
        return obj.listener.id if obj.listener else None
    
    def get_listener_email(self, obj):
        """Get listener email from CallSession object."""
        return obj.listener.email if obj.listener else None
    
    def get_listener_name(self, obj):
        """Get listener full name or email."""
        if obj.listener:
            return obj.listener.full_name or obj.listener.email
        return None
    
    def get_duration_in_minutes(self, obj):
        """Calculate actual call duration."""
        if obj.started_at and obj.ended_at:
            delta = obj.ended_at - obj.started_at
            return round(delta.total_seconds() / 60, 2)
        return 0
    
    def get_amount_paid(self, obj):
        """Get the amount paid for this call."""
        if obj.call_package:
            return str(obj.call_package.total_amount)
        return "0.00"


class TalkerCallHistoryDetailSerializer(serializers.Serializer):
    """Detailed serializer for a single talker call session."""
    id = serializers.IntegerField(read_only=True)
    listener_id = serializers.SerializerMethodField(read_only=True)
    listener_email = serializers.SerializerMethodField(read_only=True)
    listener_full_name = serializers.SerializerMethodField(read_only=True)
    listener_profile = serializers.SerializerMethodField(read_only=True)
    status = serializers.CharField(read_only=True)
    call_type = serializers.CharField(read_only=True)
    total_minutes_purchased = serializers.IntegerField(read_only=True)
    minutes_used = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    started_at = serializers.DateTimeField(read_only=True)
    ended_at = serializers.DateTimeField(read_only=True)
    end_reason = serializers.CharField(read_only=True)
    last_warning_sent = serializers.BooleanField(read_only=True)
    duration_in_minutes = serializers.SerializerMethodField(read_only=True)
    call_package_details = serializers.SerializerMethodField(read_only=True)
    transaction_details = serializers.SerializerMethodField(read_only=True)
    agora_channel_name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    def get_listener_id(self, obj):
        """Get listener ID from CallSession object."""
        return obj.listener.id if obj.listener else None
    
    def get_listener_email(self, obj):
        """Get listener email from CallSession object."""
        return obj.listener.email if obj.listener else None
    
    def get_listener_full_name(self, obj):
        """Get listener full name or email."""
        if obj.listener:
            return obj.listener.full_name or obj.listener.email
        return None
    
    def get_duration_in_minutes(self, obj):
        """Calculate actual call duration."""
        if obj.started_at and obj.ended_at:
            delta = obj.ended_at - obj.started_at
            return round(delta.total_seconds() / 60, 2)
        return 0
    
    def get_listener_profile(self, obj):
        """Get listener's profile information."""
        if obj.listener:
            return {
                'id': obj.listener.id,
                'email': obj.listener.email,
                'full_name': obj.listener.full_name,
                'user_type': obj.listener.user_type
            }
        return None
    
    def get_call_package_details(self, obj):
        """Get call package details."""
        if obj.call_package:
            try:
                return {
                    'id': obj.call_package.id,
                    'package_name': obj.call_package.package.name,
                    'duration_minutes': obj.call_package.package.duration_minutes,
                    'price': str(obj.call_package.total_amount),
                    'app_fee': str(obj.call_package.app_fee),
                    'listener_amount': str(obj.call_package.listener_amount),
                    'status': obj.call_package.status
                }
            except:
                return None
        return None
    
    def get_transaction_details(self, obj):
        """Get complete transaction details for this call."""
        if obj.call_package:
            try:
                pkg = obj.call_package
                return {
                    'transaction_id': pkg.id,
                    'talker_id': obj.talker.id,
                    'listener_id': obj.listener.id,
                    'amount_paid': str(pkg.total_amount),
                    'currency': 'USD',
                    'app_commission': str(pkg.app_fee),
                    'listener_payout': str(pkg.listener_amount),
                    'payment_status': pkg.status,
                    'minutes_purchased': pkg.package.duration_minutes,
                    'minutes_used': str(obj.minutes_used),
                    'created_at': pkg.created_at,
                    'payment_method': getattr(pkg, 'stripe_payment_method_id', ''),
                    'stripe_charge_id': getattr(pkg, 'stripe_charge_id', '')
                }
            except:
                return None
        return None

class TalkerProfileSerializer(serializers.ModelSerializer):
    """Serializer for talker profile personal information."""
    full_name = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = TalkerProfile
        fields = ['id', 'user', 'user_email', 'first_name', 'last_name', 'full_name', 'gender', 
                  'profile_image', 'profile_image_url', 'location', 'about_me', 'created_at', 'updated_at']
        read_only_fields = ['user', 'user_email', 'created_at', 'updated_at', 'id', 'profile_image_url']
        extra_kwargs = {
            'profile_image': {'allow_null': True, 'required': False}
        }

    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_profile_image_url(self, obj):
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None

class FavoriteListenerSerializer(serializers.ModelSerializer):
    """Serializer for favorite listener with listener details."""
    listener_id = serializers.IntegerField(source='listener.user_id', read_only=True)
    full_name = serializers.CharField(source='listener.get_full_name', read_only=True)
    email = serializers.CharField(source='listener.user.email', read_only=True)
    profile_image = serializers.SerializerMethodField()
    gender = serializers.CharField(source='listener.gender', read_only=True)
    location = serializers.CharField(source='listener.location', read_only=True)
    experience_level = serializers.CharField(source='listener.experience_level', read_only=True)
    bio = serializers.CharField(source='listener.bio', read_only=True)
    hourly_rate = serializers.CharField(source='listener.hourly_rate', read_only=True)
    average_rating = serializers.FloatField(source='listener.average_rating', read_only=True)
    total_hours = serializers.FloatField(source='listener.total_hours', read_only=True)
    
    class Meta:
        model = FavoriteListener
        fields = [
            'id', 'listener_id', 'full_name', 'email', 'profile_image', 'gender', 
            'location', 'experience_level', 'bio', 'hourly_rate', 'average_rating', 
            'total_hours', 'added_at'
        ]
        read_only_fields = ['id', 'added_at']
    
    def get_profile_image(self, obj):
        if obj.listener.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.listener.profile_image.url)
            return obj.listener.profile_image.url
        return None


class AddFavoriteListenerSerializer(serializers.Serializer):
    """Serializer for adding a listener to favorites."""
    listener_id = serializers.IntegerField(required=True)
    
    def validate_listener_id(self, value):
        """Validate that the listener exists."""
        try:
            ListenerProfile.objects.get(user_id=value)
        except ListenerProfile.DoesNotExist:
            raise serializers.ValidationError(f"Listener with ID {value} not found.")
        return value